from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from repopilot_contracts import (
    AgentRunState,
    GeneratedPatch,
    ImplementationPlan,
    ImplementationRunRequest,
    ImplementationRunResult,
    PatchFileChange,
    PlanApprovalStatus,
    PolicyDecisionType,
    SandboxCommandResult,
    ToolCallRequest,
    ToolCallResult,
    ToolCallStatus,
    ValidationStatus,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import AgentRun, AgentStep, Issue, Plan
from app.services.artifacts import ArtifactStore
from app.services.audit import record_audit
from app.services.model_gateway import ModelGateway
from app.services.planning import approved_plan_hash_matches, implementation_plan_from_db
from app.services.policy import PolicyEngine
from app.services.state_machine import transition_run
from app.services.validation import ValidationPlanner


IGNORED_WORKSPACE_DIRS = {
    ".git",
    ".mypy_cache",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "htmlcov",
    "node_modules",
    "venv",
    ".venv",
}

WRITE_TOOLS = {"workspace.apply_patch", "workspace.replace_text", "workspace.write_file"}


class ProposedImplementationToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: Literal["workspace.apply_patch", "workspace.replace_text", "workspace.write_file"]
    arguments: dict[str, Any] = Field(default_factory=dict)


class ImplementationToolPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str
    tool_calls: list[ProposedImplementationToolCall] = Field(default_factory=list, max_length=8)
    stop_reason: str | None = None


class ImplementationAgent:
    def __init__(
        self,
        *,
        workspace_root: Path | None = None,
        model_gateway: ModelGateway | None = None,
        tool_executor: Any | None = None,
    ) -> None:
        self.workspace_root = workspace_root or Path("/tmp/repopilot-agent-workspaces")
        self.model_gateway = model_gateway or ModelGateway()
        self.policy_engine = PolicyEngine()
        self.validation_planner = ValidationPlanner(policy_engine=self.policy_engine)
        if tool_executor is None:
            from app.services.tools import ToolExecutor

            tool_executor = ToolExecutor()
        self.tool_executor = tool_executor

    async def execute(
        self,
        db: AsyncSession,
        *,
        run_id: UUID,
        request: ImplementationRunRequest,
    ) -> ImplementationRunResult:
        run = await db.get(AgentRun, run_id)
        if run is None:
            raise ValueError(f"Agent run not found: {run_id}")
        if run.plan_id is None:
            return await self._blocked(db, run=run, reason="Run has no plan.")

        plan = await db.get(Plan, run.plan_id)
        if plan is None:
            return await self._blocked(db, run=run, reason="Run plan was not found.")
        if plan.approval_status != PlanApprovalStatus.APPROVED.value:
            return await self._blocked(db, run=run, reason="Run plan is not approved.")
        if not approved_plan_hash_matches(plan):
            return await self._blocked(db, run=run, reason="Approved plan hash no longer matches the current plan.")

        implementation_plan = implementation_plan_from_db(plan)
        policy = self.policy_engine.evaluate_plan(implementation_plan)
        if policy.decision != PolicyDecisionType.ALLOW:
            return await self._blocked(db, run=run, reason=f"Plan policy is {policy.decision}: {policy.reason}")

        source_workspace = Path(request.workspace_path).expanduser().resolve()
        issue = await db.get(Issue, plan.issue_id)

        if run.state == AgentRunState.WAIT_FOR_APPROVAL.value:
            await transition_run(
                db,
                run=run,
                next_state=AgentRunState.CREATE_BRANCH,
                actor_type="agent",
                reason="Preparing isolated run workspace for approved implementation.",
                metadata={"source_workspace": str(source_workspace)},
            )

        copy_result = await self._execute_tool(
            db,
            run=run,
            state=AgentRunState.CREATE_BRANCH,
            tool_name="workspace.create_run_copy",
            arguments={"run_id": str(run.id), "source_workspace": str(source_workspace)},
        )
        if copy_result.status != ToolCallStatus.SUCCEEDED:
            return await self._blocked(db, run=run, reason=copy_result.blocked_reason or "Workspace copy failed.")
        workspace_path = str(copy_result.output["working_workspace_path"])

        await transition_run(
            db,
            run=run,
            next_state=AgentRunState.IMPLEMENT_PATCH,
            actor_type="agent",
            reason="Requesting bounded implementation tool calls from the model.",
            metadata={"workspace_path": workspace_path},
        )

        last_validation: SandboxCommandResult | None = None
        patch: GeneratedPatch | None = None
        max_attempts = max(1, min(settings.max_agent_retries, 3))

        for attempt in range(1, max_attempts + 1):
            snippets = await self._read_context_snippets(
                db,
                run=run,
                workspace_path=workspace_path,
                implementation_plan=implementation_plan,
            )
            workspace_state = await self._retry_workspace_state(
                db,
                run=run,
                workspace_path=workspace_path,
                attempt=attempt,
            )
            tool_plan = await self._propose_tool_plan(
                db,
                run=run,
                issue=issue,
                implementation_plan=implementation_plan,
                workspace_path=workspace_path,
                snippets=snippets,
                workspace_state=workspace_state,
                attempt=attempt,
                previous_validation=last_validation,
            )
            if not tool_plan.tool_calls:
                return await self._blocked(
                    db,
                    run=run,
                    reason=tool_plan.stop_reason or "Model did not propose implementation tool calls.",
                )

            write_results = await self._execute_write_tool_calls(
                db,
                run=run,
                workspace_path=workspace_path,
                tool_plan=tool_plan,
                max_changed_files=request.max_changed_files,
            )
            blocked_result = next((result for result in write_results if result.status != ToolCallStatus.SUCCEEDED), None)
            if blocked_result is not None:
                return await self._blocked(
                    db,
                    run=run,
                    reason=blocked_result.blocked_reason or f"{blocked_result.tool_name} failed.",
                )

            patch = await self._capture_patch(
                db,
                run=run,
                workspace_path=workspace_path,
                source_workspace=source_workspace,
                summary=tool_plan.summary,
                max_changed_files=request.max_changed_files,
            )
            if not patch.changed_files:
                return await self._blocked(db, run=run, reason="Implementation tool calls produced no workspace diff.")

            db.add(
                AgentStep(
                    run_id=run.id,
                    step_name=AgentRunState.IMPLEMENT_PATCH.value,
                    output_json=patch.model_dump(mode="json"),
                    status="succeeded",
                )
            )
            if run.state == AgentRunState.IMPLEMENT_PATCH.value:
                await transition_run(
                    db,
                    run=run,
                    next_state=AgentRunState.GENERATE_TESTS,
                    actor_type="agent",
                    reason="Captured implementation diff and generated/updated tests through approved tools.",
                    metadata={"changed_files": [change.path for change in patch.changed_files]},
                )
                await transition_run(
                    db,
                    run=run,
                    next_state=AgentRunState.RUN_LOCAL_VALIDATION,
                    actor_type="agent",
                    reason="Running sandbox validation for the generated patch.",
                    metadata={"patch_hash": patch.patch_hash},
                )

            last_validation = await self._run_validation(
                db,
                run=run,
                workspace_path=workspace_path,
                request=request,
                implementation_plan=implementation_plan,
            )
            if last_validation.status == ValidationStatus.PASSED:
                await self._record_success(db, run=run, patch=patch, validation=last_validation, attempt=attempt)
                return ImplementationRunResult(
                    run_id=str(run.id),
                    status=last_validation.status,
                    patch=patch,
                    validation=last_validation,
                    blocked_reason=last_validation.blocked_reason,
                )
            if last_validation.status == ValidationStatus.BLOCKED:
                await record_audit(
                    db,
                    actor_type="agent",
                    action="implementation.validation_blocked",
                    entity_type="agent_run",
                    entity_id=str(run.id),
                    metadata={"reason": last_validation.blocked_reason, "attempt": attempt},
                )
                await db.commit()
                return ImplementationRunResult(
                    run_id=str(run.id),
                    status=last_validation.status,
                    patch=patch,
                    validation=last_validation,
                    blocked_reason=last_validation.blocked_reason or "Validation was blocked.",
                )

        if run.state == AgentRunState.RUN_LOCAL_VALIDATION.value:
            await transition_run(
                db,
                run=run,
                next_state=AgentRunState.FAILED,
                actor_type="agent",
                reason="Validation failed after bounded implementation attempts.",
                metadata={"attempts": max_attempts, "status": last_validation.status.value if last_validation else None},
            )
        await db.commit()
        return ImplementationRunResult(
            run_id=str(run.id),
            status=last_validation.status if last_validation else ValidationStatus.FAILED,
            patch=patch,
            validation=last_validation,
            blocked_reason=(last_validation.blocked_reason if last_validation else None) or "Validation failed after bounded implementation attempts.",
        )

    async def _execute_tool(
        self,
        db: AsyncSession,
        *,
        run: AgentRun,
        state: AgentRunState,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> ToolCallResult:
        return await self.tool_executor.execute(
            db,
            request=ToolCallRequest(
                run_id=run.id,
                state=state,
                tool_name=tool_name,
                actor="agent",
                arguments=arguments,
            ),
        )

    async def _read_context_snippets(
        self,
        db: AsyncSession,
        *,
        run: AgentRun,
        workspace_path: str,
        implementation_plan: ImplementationPlan,
    ) -> list[dict[str, Any]]:
        snippets: list[dict[str, Any]] = []
        paths = self._unique_paths(implementation_plan.files_to_inspect + implementation_plan.files_to_modify)
        if not paths:
            return snippets
        result = await self._execute_tool(
            db,
            run=run,
            state=AgentRunState.IMPLEMENT_PATCH,
            tool_name="repo.read_files",
            arguments={
                "workspace_path": workspace_path,
                "files": [{"path": path, "start_line": 1, "end_line": 220} for path in paths[:8]],
            },
        )
        if result.status == ToolCallStatus.SUCCEEDED:
            snippets.extend(item for item in result.output.get("files", []) if isinstance(item, dict))
        return snippets

    async def _retry_workspace_state(
        self,
        db: AsyncSession,
        *,
        run: AgentRun,
        workspace_path: str,
        attempt: int,
    ) -> dict[str, Any] | None:
        if attempt <= 1:
            return None
        result = await self._execute_tool(
            db,
            run=run,
            state=AgentRunState(run.state),
            tool_name="workspace.diff",
            arguments={"workspace_path": workspace_path},
        )
        if result.status != ToolCallStatus.SUCCEEDED:
            return {"diff_available": False, "blocked_reason": result.blocked_reason}
        changed_files = [
            change
            for change in result.output.get("changed_files", [])
            if isinstance(change, dict)
        ]
        diff = str(result.output.get("diff") or "")
        return {
            "diff_available": True,
            "changed_files": changed_files[:20],
            "changed_file_count": len(changed_files),
            "diff_excerpt": diff[:8_000],
            "diff_truncated": bool(result.output.get("truncated")) or len(diff) > 8_000,
        }

    async def _propose_tool_plan(
        self,
        db: AsyncSession,
        *,
        run: AgentRun,
        issue: Issue | None,
        implementation_plan: ImplementationPlan,
        workspace_path: str,
        snippets: list[dict[str, Any]],
        workspace_state: dict[str, Any] | None,
        attempt: int,
        previous_validation: SandboxCommandResult | None,
    ) -> ImplementationToolPlan:
        prompt = {
            "issue": {
                "title": issue.title if issue else "RepoPilot implementation task",
                "number": issue.number if issue else None,
            },
            "approved_plan": implementation_plan.model_dump(mode="json"),
            "workspace_path": workspace_path,
            "attempt": attempt,
            "previous_validation": previous_validation.model_dump(mode="json") if previous_validation else None,
            "file_snippets": snippets,
            "workspace_state": workspace_state,
            "allowed_tools": sorted(WRITE_TOOLS),
            "rules": [
                "Return only JSON matching the schema.",
                "Use only workspace.apply_patch, workspace.replace_text, or workspace.write_file.",
                "Every write path must already be approved in files_to_modify or tests_to_add.",
                "Do not claim validation, security, CI, or PR status.",
            ],
        }
        return await self.model_gateway.complete_json(
            db,
            run_id=run.id,
            agent_name="implementation_agent",
            system_prompt=(
                "You are RepoPilot's implementation agent. Propose the smallest safe tool calls "
                "needed to implement the approved plan. You do not execute shell commands or write "
                "files directly; RepoPilot will execute accepted tools through policy gates."
            ),
            user_prompt=json.dumps(prompt, sort_keys=True),
            response_model=ImplementationToolPlan,
            fallback=lambda: ImplementationToolPlan(
                summary="No implementation tool calls were produced by the configured model.",
                tool_calls=[],
                stop_reason="Configure a live model provider or revise the plan with explicit patch instructions.",
            ),
            context_citations=implementation_plan.context_citations,
        )

    async def _execute_write_tool_calls(
        self,
        db: AsyncSession,
        *,
        run: AgentRun,
        workspace_path: str,
        tool_plan: ImplementationToolPlan,
        max_changed_files: int,
    ) -> list[ToolCallResult]:
        results: list[ToolCallResult] = []
        for proposed in tool_plan.tool_calls:
            if proposed.tool_name not in WRITE_TOOLS:
                results.append(
                    ToolCallResult(
                        tool_name=proposed.tool_name,
                        status=ToolCallStatus.BLOCKED,
                        blocked_reason="Implementation agent may only request approved workspace write tools.",
                    )
                )
                continue
            arguments = dict(proposed.arguments)
            arguments["workspace_path"] = workspace_path
            if proposed.tool_name == "workspace.apply_patch":
                arguments.setdefault("max_changed_files", max_changed_files)
                arguments.setdefault("return_diff", False)
            results.append(
                await self._execute_tool(
                    db,
                    run=run,
                    state=AgentRunState(run.state),
                    tool_name=proposed.tool_name,
                    arguments=arguments,
                )
            )
        return results

    async def _capture_patch(
        self,
        db: AsyncSession,
        *,
        run: AgentRun,
        workspace_path: str,
        source_workspace: Path,
        summary: str,
        max_changed_files: int,
    ) -> GeneratedPatch:
        diff_result = await self._execute_tool(
            db,
            run=run,
            state=AgentRunState(run.state),
            tool_name="workspace.diff",
            arguments={"workspace_path": workspace_path},
        )
        if diff_result.status != ToolCallStatus.SUCCEEDED:
            raise ValueError(diff_result.blocked_reason or "Workspace diff failed.")
        changed_files = [
            PatchFileChange.model_validate(change)
            for change in diff_result.output.get("changed_files", [])
            if isinstance(change, dict)
        ]
        if len(changed_files) > max_changed_files:
            raise ValueError("Generated patch changes more files than the request allows.")
        diff = str(diff_result.output.get("diff") or "")
        artifact = ArtifactStore().write_text(
            db,
            run_id=run.id,
            artifact_type="patch.diff",
            text=diff,
            content_type="text/x-diff; charset=utf-8",
            metadata={
                "changed_files": [change.path for change in changed_files],
                "source_workspace_path": str(source_workspace),
                "working_workspace_path": workspace_path,
            },
            extension=".diff",
        )
        return GeneratedPatch(
            run_id=str(run.id),
            source_workspace_path=str(source_workspace),
            working_workspace_path=workspace_path,
            patch_hash=self._diff_hash(diff),
            diff=diff,
            diff_uri=artifact.uri,
            diff_artifact=artifact.reference(),
            changed_files=changed_files,
            summary=summary,
        )

    async def _run_validation(
        self,
        db: AsyncSession,
        *,
        run: AgentRun,
        workspace_path: str,
        request: ImplementationRunRequest,
        implementation_plan: ImplementationPlan,
    ) -> SandboxCommandResult:
        command = self._validation_command(
            implementation_plan=implementation_plan,
            workspace_path=workspace_path,
            override=request.validation_command,
        )
        result = await self._execute_tool(
            db,
            run=run,
            state=AgentRunState(run.state),
            tool_name="validation.run_tests",
            arguments={"run_id": str(run.id), "workspace_path": workspace_path, "command": command, "timeout_seconds": request.timeout_seconds},
        )
        if result.status != ToolCallStatus.SUCCEEDED:
            return SandboxCommandResult(
                command=command,
                status=ValidationStatus.BLOCKED,
                duration_ms=result.duration_ms,
                blocked_reason=result.blocked_reason or "Validation tool did not complete.",
            )
        return SandboxCommandResult.model_validate(result.output)

    async def _record_success(
        self,
        db: AsyncSession,
        *,
        run: AgentRun,
        patch: GeneratedPatch,
        validation: SandboxCommandResult,
        attempt: int,
    ) -> None:
        await record_audit(
            db,
            actor_type="agent",
            action="implementation.executed",
            entity_type="agent_run",
            entity_id=str(run.id),
            metadata={
                "patch_hash": patch.patch_hash,
                "changed_files": [change.path for change in patch.changed_files],
                "validation_status": validation.status.value,
                "attempt": attempt,
            },
        )
        await db.commit()

    async def _blocked(self, db: AsyncSession, *, run: AgentRun, reason: str) -> ImplementationRunResult:
        db.add(
            AgentStep(
                run_id=run.id,
                step_name=AgentRunState.IMPLEMENT_PATCH.value,
                output_json={"blocked_reason": reason},
                status="blocked",
            )
        )
        await record_audit(
            db,
            actor_type="agent",
            action="implementation.blocked",
            entity_type="agent_run",
            entity_id=str(run.id),
            metadata={"reason": reason},
        )
        await db.commit()
        return ImplementationRunResult(run_id=str(run.id), status=ValidationStatus.BLOCKED, blocked_reason=reason)

    def _unique_paths(self, paths: list[str]) -> list[str]:
        normalized: list[str] = []
        for path in paths:
            relative = self._workspace_relative_path(path)
            if relative and relative not in normalized:
                normalized.append(relative)
        return normalized

    def _workspace_relative_path(self, path: str) -> str | None:
        normalized = PurePosixPath(path.replace("\\", "/"))
        parts = normalized.parts
        if not parts:
            return None
        if len(parts) >= 3 and parts[0] == "apps" and parts[1] == "api":
            return PurePosixPath(*parts[2:]).as_posix()
        return normalized.as_posix()

    def _validation_command(
        self,
        *,
        implementation_plan: ImplementationPlan,
        workspace_path: str,
        override: str | None = None,
    ) -> str:
        if override:
            return self._normalize_validation_command(override)
        return self.validation_planner.commands_for(
            workspace_path=workspace_path,
            plan_commands=implementation_plan.commands_to_run,
        )[0]

    def _normalize_validation_command(self, command: str) -> str:
        normalized = " ".join(command.split())
        if normalized == "pytest" or normalized.startswith("pytest "):
            return f"python -m {normalized}"
        if normalized == "python3 -m pytest" or normalized.startswith("python3 -m pytest "):
            return f"python{normalized.removeprefix('python3')}"
        return normalized

    def _diff_hash(self, diff: str) -> str:
        from app.services.security_envelope import stable_json_hash

        return stable_json_hash({"diff": diff})
