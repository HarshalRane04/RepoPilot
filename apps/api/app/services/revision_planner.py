from __future__ import annotations

from uuid import UUID

from repopilot_contracts import PlanApprovalStatus
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentRun, AgentStep, Plan, PullRequest
from app.services.audit import record_audit
from app.services.planning import implementation_plan_from_db


class RevisionPlanner:
    async def create_revision_plan(
        self,
        db: AsyncSession,
        *,
        pr_id: UUID,
        instructions: str = "",
        actor_id: str | None = None,
    ) -> Plan:
        pr = await db.get(PullRequest, pr_id)
        if pr is None:
            raise ValueError(f"Pull request not found: {pr_id}")
        run = await db.get(AgentRun, pr.run_id)
        if run is None or run.plan_id is None:
            raise ValueError("Revision planning requires a run with an approved plan.")
        parent = await db.get(Plan, run.plan_id)
        if parent is None:
            raise ValueError("Parent plan not found.")

        ci_step = await self._latest_ci_step(db, run_id=run.id)
        ci_output = ci_step.output_json if ci_step and isinstance(ci_step.output_json, dict) else {}
        parent_plan = implementation_plan_from_db(parent)
        proposed_path = str(ci_output.get("proposed_fix_path") or "")
        files_to_modify = parent_plan.files_to_modify
        if proposed_path and proposed_path in parent_plan.files_to_modify + parent_plan.tests_to_add:
            files_to_modify = [proposed_path]

        revision_payload = {
            **parent_plan.model_dump(mode="json"),
            "plan_id": "pending",
            "summary": f"Revision plan for CI failure: {ci_output.get('root_cause') or 'CI did not pass.'}",
            "files_to_modify": files_to_modify,
            "risk_notes": [
                *parent_plan.risk_notes,
                "CI revision requires fresh human approval before any fixup commit.",
            ],
            "revision_parent_plan_id": str(parent.id),
            "revision_instructions": instructions,
            "ci_failure_evidence": ci_output,
        }
        revision = Plan(
            issue_id=parent.issue_id,
            approval_status=PlanApprovalStatus.WAITING.value,
            version=parent.version + 1,
            plan_json=revision_payload,
        )
        db.add(revision)
        await db.flush()
        revision.plan_json = {**revision.plan_json, "plan_id": str(revision.id)}
        run.plan_id = revision.id
        await record_audit(
            db,
            actor_type="user" if actor_id else "system",
            actor_id=actor_id,
            action="plan.revision_created_from_ci",
            entity_type="plan",
            entity_id=str(revision.id),
            metadata={"parent_plan_id": str(parent.id), "pr_id": str(pr.id), "instructions": instructions},
        )
        await db.commit()
        return revision

    async def _latest_ci_step(self, db: AsyncSession, *, run_id: UUID) -> AgentStep | None:
        result = await db.execute(
            select(AgentStep)
            .where(AgentStep.run_id == run_id, AgentStep.step_name == "WAIT_FOR_CI")
            .order_by(AgentStep.created_at.desc())
        )
        return result.scalars().first()
