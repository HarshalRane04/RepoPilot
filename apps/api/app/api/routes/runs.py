from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from repopilot_contracts import (
    AgentRunDetailResponse,
    AgentRunListItem,
    AgentRunState,
    DraftPullRequestRequest,
    ImplementationRunRequest,
    RunTraceResponse,
    SandboxCommandRequest,
    SecurityScanRequest,
    ToolCallRequest,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentRun, AgentStep, Plan, ValidationResult as DbValidationResult
from app.db.session import get_db
from app.services.artifacts import ArtifactStore
from app.services.draft_pr import DraftPullRequestService
from app.services.auth import CurrentUser, get_current_user
from app.services.authorization import require_role, require_run_access
from app.services.implementation_agent import ImplementationAgent
from app.services.observability import ObservabilityService
from app.services.planning import approved_plan_hash_matches
from app.services.sandbox import SandboxRunner
from app.services.security_envelope import rate_limit, redact_text, stable_json_hash
from app.services.security_scanner import SecurityScanner
from app.services.state_machine import InvalidStateTransition, next_states, transition_run
from app.services.tools import ToolExecutor

router = APIRouter()


class RunToolCallBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class RunToolCallBatchBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_calls: list[RunToolCallBody] = Field(min_length=1, max_length=20)


@router.get("", response_model=list[AgentRunListItem])
async def list_runs(
    limit: int = 50,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, object]]:
    require_role(current_user, "viewer")
    result = await db.execute(select(AgentRun).order_by(AgentRun.started_at.desc()).limit(min(max(limit, 1), 200)))
    runs = result.scalars().all()
    response: list[dict[str, object]] = []
    for run in runs:
        latest_step = await db.execute(
            select(AgentStep).where(AgentStep.run_id == run.id).order_by(AgentStep.created_at.desc()).limit(1)
        )
        step = latest_step.scalars().first()
        validations = await db.execute(select(DbValidationResult).where(DbValidationResult.run_id == run.id))
        validation_list = validations.scalars().all()
        response.append(
            {
                "id": str(run.id),
                "issue_id": str(run.issue_id) if run.issue_id else None,
                "plan_id": str(run.plan_id) if run.plan_id else None,
                "state": run.state,
                "model_used": run.model_used,
                "total_tokens": run.total_tokens,
                "total_cost": run.total_cost,
                "started_at": run.started_at,
                "completed_at": run.completed_at,
                "latest_step": step.step_name if step else None,
                "latest_step_status": step.status if step else None,
                "validation_statuses": [validation.status for validation in validation_list],
            }
        )
    return response


@router.post("/{run_id}/start", status_code=202)
async def start_run(
    run_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    run = await require_run_access(db, run_id=run_id, current_user=current_user, action="write")
    await _require_approved_plan(db, run)
    try:
        await transition_run(
            db,
            run=run,
            next_state="CREATE_BRANCH",
            actor_type="user",
            reason="Approved implementation run was started.",
        )
    except InvalidStateTransition as exc:
        raise HTTPException(status_code=409, detail={"error": str(exc), "next_states": next_states(run.state)}) from exc
    await db.commit()
    return {
        "status": "accepted",
        "run_id": str(run_id),
        "message": "Run moved to CREATE_BRANCH and is ready for implementation, generated tests, and sandbox validation.",
    }


@router.post("/{run_id}/stop", status_code=202)
async def stop_run(
    run_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    run = await require_run_access(db, run_id=run_id, current_user=current_user, action="write")
    try:
        await transition_run(
            db,
            run=run,
            next_state="CANCELLED",
            actor_type="user",
            reason="User requested run stop.",
        )
    except InvalidStateTransition as exc:
        raise HTTPException(status_code=409, detail={"error": str(exc), "next_states": next_states(run.state)}) from exc
    await db.commit()
    return {"status": "accepted", "run_id": str(run_id), "message": "Run was cancelled."}


@router.get("/{run_id}", response_model=AgentRunDetailResponse)
async def get_run(
    run_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    run = await require_run_access(db, run_id=run_id, current_user=current_user, action="read")
    steps = await db.execute(select(AgentStep).where(AgentStep.run_id == run.id).order_by(AgentStep.created_at.asc()))
    validations = await db.execute(select(DbValidationResult).where(DbValidationResult.run_id == run.id))
    return {
        "id": str(run.id),
        "issue_id": str(run.issue_id) if run.issue_id else None,
        "plan_id": str(run.plan_id) if run.plan_id else None,
        "state": run.state,
        "model_used": run.model_used,
        "total_tokens": run.total_tokens,
        "total_cost": run.total_cost,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "steps": [
            {
                "id": str(step.id),
                "step_name": step.step_name,
                "status": step.status,
                "output_json": step.output_json,
                "error": step.error,
                "created_at": step.created_at,
            }
            for step in steps.scalars().all()
        ],
        "validation_results": [
            {
                "id": str(result.id),
                "command": result.command,
                "status": result.status,
                "duration_ms": result.duration_ms,
                "parsed_summary": result.parsed_summary,
                "log_uri": result.log_uri,
                "evidence_hash": result.evidence_hash,
            }
            for result in validations.scalars().all()
        ],
    }


@router.post("/{run_id}/sandbox")
async def run_sandbox_command(
    run_id: UUID,
    request: SandboxCommandRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    run = await require_run_access(db, run_id=run_id, current_user=current_user, action="write")
    await _require_approved_plan(db, run)

    result = SandboxRunner().run_command(request, run_id=run.id)
    parsed_summary = redact_text(result.blocked_reason or f"exit_code={result.exit_code}")
    redacted_stdout = redact_text(result.stdout)
    redacted_stderr = redact_text(result.stderr)
    evidence_hash = stable_json_hash(
        {
            "command": result.command,
            "status": result.status.value,
            "summary": parsed_summary,
            "stdout": redacted_stdout,
            "stderr": redacted_stderr,
        }
    )
    artifact = ArtifactStore().write_json(
        db,
        run_id=run.id,
        artifact_type="validation.log",
        payload={
            "command": result.command,
            "status": result.status.value,
            "summary": parsed_summary,
            "stdout": redacted_stdout,
            "stderr": redacted_stderr,
            "exit_code": result.exit_code,
            "duration_ms": result.duration_ms,
            "evidence_hash": evidence_hash,
        },
        metadata={"route": "runs.sandbox"},
    )
    db.add(
        DbValidationResult(
            run_id=run.id,
            command=result.command,
            status=result.status.value,
            duration_ms=result.duration_ms,
            parsed_summary=parsed_summary,
            log_uri=artifact.uri,
            evidence_hash=evidence_hash,
        )
    )
    step_output = result.model_dump(mode="json")
    step_output.update(
        {
            "stdout": "",
            "stderr": "",
            "log_uri": artifact.uri,
            "log_artifact": artifact.reference(),
            "evidence_hash": evidence_hash,
        }
    )
    db.add(
        AgentStep(
            run_id=run.id,
            step_name="SANDBOX_COMMAND",
            output_json=step_output,
            status="succeeded" if result.status.value == "passed" else "blocked" if result.status.value == "blocked" else "failed",
        )
    )
    await db.commit()
    return result.model_dump(mode="json")


@router.post("/{run_id}/implement")
async def run_implementation_agent(
    run_id: UUID,
    request: ImplementationRunRequest,
    _rate_limit: None = Depends(rate_limit("run-implementation", limit_attr="rate_limit_expensive_per_minute")),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    await require_run_access(db, run_id=run_id, current_user=current_user, action="write")
    try:
        result = await ImplementationAgent().execute(db, run_id=run_id, request=request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result.model_dump(mode="json")


@router.post("/{run_id}/security-scan")
async def run_security_scan(
    run_id: UUID,
    request: SecurityScanRequest | None = None,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    await require_run_access(db, run_id=run_id, current_user=current_user, action="write")
    try:
        result = await SecurityScanner().scan_run(db, run_id=run_id, request=request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result.model_dump(mode="json")


@router.post("/{run_id}/open-draft-pr", status_code=202)
async def open_draft_pr(
    run_id: UUID,
    request: DraftPullRequestRequest | None = None,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    await require_run_access(db, run_id=run_id, current_user=current_user, action="write")
    try:
        result = await DraftPullRequestService().open_draft_pr(db, run_id=run_id, request=request)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return result.model_dump(mode="json")


@router.get("/{run_id}/trace", response_model=RunTraceResponse)
async def get_run_trace(
    run_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    await require_run_access(db, run_id=run_id, current_user=current_user, action="read")
    try:
        return await ObservabilityService().run_trace(db, run_id=run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{run_id}/tools/call")
async def call_run_tool(
    run_id: UUID,
    request: RunToolCallBody,
    _rate_limit: None = Depends(rate_limit("tool-call")),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, object]:
    run = await require_run_access(db, run_id=run_id, current_user=current_user, action="write")
    executor = ToolExecutor()
    tool_request = _server_tool_request(executor=executor, run=run, body=request, current_user=current_user)
    result = await executor.execute(db, request=tool_request)
    return result.model_dump(mode="json")


@router.post("/{run_id}/tools/batch")
async def call_run_tools_batch(
    run_id: UUID,
    request: RunToolCallBatchBody,
    _rate_limit: None = Depends(rate_limit("tool-call")),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, object]:
    run = await require_run_access(db, run_id=run_id, current_user=current_user, action="write")
    executor = ToolExecutor()
    tool_requests = [
        _server_tool_request(executor=executor, run=run, body=tool_call, current_user=current_user)
        for tool_call in request.tool_calls
    ]
    results = await executor.execute_batch(db, requests=tool_requests)
    return {"results": [result.model_dump(mode="json") for result in results]}


async def _require_approved_plan(db: AsyncSession, run: AgentRun) -> None:
    if run.plan_id is None:
        raise HTTPException(status_code=409, detail="Run has no approved plan")
    plan = await db.get(Plan, run.plan_id)
    if plan is None or plan.approval_status != "approved":
        raise HTTPException(status_code=409, detail="Run cannot start until its plan is approved")
    if not approved_plan_hash_matches(plan):
        raise HTTPException(status_code=409, detail="Approved plan hash no longer matches the current plan")


def _server_tool_request(
    *,
    executor: ToolExecutor,
    run: AgentRun,
    body: RunToolCallBody,
    current_user: CurrentUser,
) -> ToolCallRequest:
    del current_user
    try:
        state = AgentRunState(run.state)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=f"Agent run has invalid state: {run.state}") from exc
    arguments = _bind_tool_arguments_to_run(executor=executor, tool_name=body.tool_name, arguments=body.arguments, run_id=run.id)
    return ToolCallRequest(
        run_id=run.id,
        state=state,
        tool_name=body.tool_name,
        actor="user",
        arguments=arguments,
    )


def _bind_tool_arguments_to_run(
    *,
    executor: ToolExecutor,
    tool_name: str,
    arguments: dict[str, Any],
    run_id: UUID,
) -> dict[str, Any]:
    bound = dict(arguments)
    spec = executor.registry.get(tool_name)
    if (spec is not None and "run_id" in spec.input_model.model_fields) or "run_id" in bound:
        bound["run_id"] = str(run_id)
    return bound
