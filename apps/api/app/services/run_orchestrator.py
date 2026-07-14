from __future__ import annotations

from uuid import UUID

from repopilot_contracts import ImplementationRunRequest, ValidationStatus
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import AgentRun, AgentStep, Issue, Plan, RepositoryIndex
from app.services.artifacts import maybe_externalize_json
from app.services.audit import record_audit
from app.services.draft_pr import DraftPullRequestService
from app.services.implementation_agent import ImplementationAgent
from app.services.planning import approved_plan_hash_matches
from app.services.runtime_secrets import effective_settings
from app.services.security_scanner import SecurityScanner
from app.services.state_machine import TERMINAL_STATES, transition_run


class RunOrchestrationError(RuntimeError):
    pass


class RunOrchestrator:
    """Execute an approved run until a human or external CI boundary is reached."""

    async def execute(self, db: AsyncSession, *, run_id: UUID, actor_id: str | None = None) -> dict[str, object]:
        run = await db.scalar(select(AgentRun).where(AgentRun.id == run_id).with_for_update())
        if run is None:
            raise RunOrchestrationError(f"Agent run not found: {run_id}")
        active_step = await db.scalar(
            select(AgentStep)
            .where(
                AgentStep.run_id == run.id,
                AgentStep.step_name == "ORCHESTRATE_RUN",
            )
            .order_by(AgentStep.created_at.desc())
            .limit(1)
        )
        if active_step is not None and active_step.status == "running":
            return {"run_id": str(run.id), "status": "already_running", "boundary": run.state}
        if run.state not in {"WAIT_FOR_APPROVAL", "CREATE_BRANCH"}:
            raise RunOrchestrationError(
                f"Run orchestration can start only from WAIT_FOR_APPROVAL or CREATE_BRANCH; current state is {run.state}."
            )
        plan = await db.get(Plan, run.plan_id) if run.plan_id else None
        if plan is None or plan.approval_status != "approved" or not approved_plan_hash_matches(plan):
            raise RunOrchestrationError("Run requires a current approved plan before execution.")
        source_path = await self._source_path(db, run=run)

        db.add(
            AgentStep(
                run_id=run.id,
                step_name="ORCHESTRATE_RUN",
                output_json={"phase": "started", "target_boundary": "WAIT_FOR_CI"},
                status="running",
            )
        )
        await record_audit(
            db,
            actor_type="user" if actor_id else "system",
            actor_id=actor_id,
            action="run.orchestration_started",
            entity_type="agent_run",
            entity_id=str(run.id),
            metadata={"target_boundary": "WAIT_FOR_CI"},
        )
        await db.commit()

        implementation = await ImplementationAgent().execute(
            db,
            run_id=run.id,
            request=ImplementationRunRequest(workspace_path=source_path),
        )
        if implementation.status != ValidationStatus.PASSED:
            return await self._finish(
                db,
                run=run,
                status=implementation.status.value,
                boundary=run.state,
                detail={"implementation": implementation.model_dump(mode="json")},
            )

        security = await SecurityScanner().scan_run(db, run_id=run.id)
        if security.status != ValidationStatus.PASSED:
            return await self._finish(
                db,
                run=run,
                status=security.status.value,
                boundary=run.state,
                detail={"security": security.model_dump(mode="json")},
            )

        pull_request = await DraftPullRequestService().open_draft_pr(db, run_id=run.id)
        return await self._finish(
            db,
            run=run,
            status="succeeded",
            boundary=run.state,
            detail={
                "patch_hash": implementation.patch.patch_hash if implementation.patch else None,
                "pull_request": pull_request.model_dump(mode="json"),
            },
        )

    async def create_retry_run(self, db: AsyncSession, *, run_id: UUID, actor_id: str) -> AgentRun:
        run = await db.scalar(select(AgentRun).where(AgentRun.id == run_id).with_for_update())
        if run is None:
            raise RunOrchestrationError(f"Agent run not found: {run_id}")
        latest_orchestration = await db.scalar(
            select(AgentStep)
            .where(AgentStep.run_id == run.id, AgentStep.step_name == "ORCHESTRATE_RUN")
            .order_by(AgentStep.created_at.desc())
            .limit(1)
        )
        if latest_orchestration is None or latest_orchestration.status not in {"blocked", "failed"}:
            raise RunOrchestrationError("Only a blocked or failed orchestration attempt can be retried.")
        plan = await db.get(Plan, run.plan_id) if run.plan_id else None
        if plan is None or plan.approval_status != "approved" or not approved_plan_hash_matches(plan):
            raise RunOrchestrationError("Retry requires the same current approved plan.")
        recoverable_states = {
            "CREATE_BRANCH",
            "IMPLEMENT_PATCH",
            "GENERATE_TESTS",
            "RUN_LOCAL_VALIDATION",
            "RUN_SECURITY_CHECKS",
            "OPEN_DRAFT_PR",
            "FAILED",
        }
        if run.state not in recoverable_states:
            raise RunOrchestrationError(f"Run cannot be retried from state {run.state}.")
        if run.state not in TERMINAL_STATES:
            await transition_run(
                db,
                run=run,
                next_state="FAILED",
                actor_type="user",
                actor_id=actor_id,
                reason="Blocked orchestration attempt was superseded by a fresh retry run.",
                metadata={"retry_requested": True},
            )
        retry_run = AgentRun(
            issue_id=run.issue_id,
            plan_id=run.plan_id,
            state="CREATE_BRANCH",
            model_used=effective_settings(settings).model_name,
        )
        db.add(retry_run)
        await db.flush()
        db.add(
            AgentStep(
                run_id=retry_run.id,
                step_name="RETRY_CREATED",
                output_json={"retry_of_run_id": str(run.id), "approved_plan_id": str(run.plan_id)},
                status="succeeded",
            )
        )
        await record_audit(
            db,
            actor_type="user",
            actor_id=actor_id,
            action="run.retry_created",
            entity_type="agent_run",
            entity_id=str(retry_run.id),
            metadata={"retry_of_run_id": str(run.id), "plan_id": str(run.plan_id)},
        )
        await db.commit()
        return retry_run

    async def _source_path(self, db: AsyncSession, *, run: AgentRun) -> str:
        if run.issue_id is None:
            raise RunOrchestrationError("Run has no issue and cannot resolve repository source.")
        issue = await db.get(Issue, run.issue_id)
        if issue is None:
            raise RunOrchestrationError("Run issue was not found.")
        index = await db.scalar(
            select(RepositoryIndex)
            .where(RepositoryIndex.repository_id == issue.repository_id, RepositoryIndex.status == "ready")
            .order_by(RepositoryIndex.created_at.desc())
            .limit(1)
        )
        if index is None:
            raise RunOrchestrationError("Repository has no ready index. Acquire and index it before execution.")
        return index.source_path

    async def _finish(
        self,
        db: AsyncSession,
        *,
        run: AgentRun,
        status: str,
        boundary: str,
        detail: dict[str, object],
    ) -> dict[str, object]:
        bounded_detail = maybe_externalize_json(
            db,
            run_id=run.id,
            artifact_type="orchestration.result",
            payload=detail,
            metadata={"status": status, "boundary": boundary},
        )
        db.add(
            AgentStep(
                run_id=run.id,
                step_name="ORCHESTRATE_RUN",
                output_json={"phase": "completed", "status": status, "boundary": boundary, "detail": bounded_detail},
                status="succeeded" if status == "succeeded" else "blocked" if status == "blocked" else "failed",
            )
        )
        await record_audit(
            db,
            actor_type="agent",
            action="run.orchestration_completed",
            entity_type="agent_run",
            entity_id=str(run.id),
            metadata={"status": status, "boundary": boundary},
        )
        await db.commit()
        return {"run_id": str(run.id), "status": status, "boundary": boundary, "detail": bounded_detail}
