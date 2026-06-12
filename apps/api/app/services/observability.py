from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentRun, AgentStep, AuditLog, LLMTrace, PullRequest, SecurityFinding, ValidationResult


class ObservabilityService:
    async def run_trace(self, db: AsyncSession, *, run_id: UUID) -> dict[str, object]:
        run = await db.get(AgentRun, run_id)
        if run is None:
            raise ValueError(f"Agent run not found: {run_id}")

        steps = (
            await db.execute(select(AgentStep).where(AgentStep.run_id == run.id).order_by(AgentStep.created_at.asc()))
        ).scalars().all()
        validations = (await db.execute(select(ValidationResult).where(ValidationResult.run_id == run.id))).scalars().all()
        findings = (await db.execute(select(SecurityFinding).where(SecurityFinding.run_id == run.id))).scalars().all()
        prs = (await db.execute(select(PullRequest).where(PullRequest.run_id == run.id))).scalars().all()
        audits = (
            await db.execute(
                select(AuditLog)
                .where(AuditLog.entity_id == str(run.id))
                .order_by(AuditLog.created_at.asc())
            )
        ).scalars().all()
        llm_traces = (await db.execute(select(LLMTrace).where(LLMTrace.agent_run_id == run.id))).scalars().all()
        pr_modes = self._pr_modes_from_steps(steps)

        return {
            "run": {
                "id": str(run.id),
                "state": run.state,
                "model_used": run.model_used,
                "total_tokens": run.total_tokens,
                "total_cost": run.total_cost,
                "started_at": run.started_at,
                "completed_at": run.completed_at,
            },
            "steps": [
                {
                    "step_name": step.step_name,
                    "status": step.status,
                    "latency_ms": step.latency_ms,
                    "created_at": step.created_at,
                    "output_json": step.output_json,
                }
                for step in steps
            ],
            "validation_results": [
                {
                    "command": validation.command,
                    "status": validation.status,
                    "duration_ms": validation.duration_ms,
                    "parsed_summary": validation.parsed_summary,
                }
                for validation in validations
            ],
            "security_findings": [
                {
                    "tool": finding.tool,
                    "severity": finding.severity,
                    "file_path": finding.file_path,
                    "description": finding.description,
                    "status": finding.status,
                }
                for finding in findings
            ],
            "pull_requests": [
                {
                    "id": str(pr.id),
                    "number": pr.pr_number,
                    "url": pr.url,
                    "pr_mode": pr_modes.get(str(pr.id), pr_modes.get(str(pr.pr_number), "local_record")),
                    "is_local_record": pr_modes.get(str(pr.id), pr_modes.get(str(pr.pr_number), "local_record")) == "local_record",
                    "github_url": pr.url
                    if pr_modes.get(str(pr.id), pr_modes.get(str(pr.pr_number), "local_record")) == "real_github"
                    and pr.url.startswith(("https://", "http://"))
                    else None,
                    "status": pr.status,
                    "ci_status": pr.ci_status,
                }
                for pr in prs
            ],
            "audit_events": [
                {
                    "action": audit.action,
                    "actor_type": audit.actor_type,
                    "created_at": audit.created_at,
                    "metadata": audit.metadata_json,
                }
                for audit in audits
            ],
            "llm_traces": [
                {
                    "agent_name": trace.agent_name,
                    "prompt_hash": trace.prompt_hash,
                    "response_hash": trace.response_hash,
                    "provider": trace.provider,
                    "model": trace.model,
                    "mode": trace.mode,
                    "tokens": trace.tokens,
                    "cost": trace.cost,
                    "latency_ms": trace.latency_ms,
                    "metadata": trace.metadata_json,
                }
                for trace in llm_traces
            ],
        }

    def _pr_modes_from_steps(self, steps: list[AgentStep]) -> dict[str, str]:
        modes: dict[str, str] = {}
        for step in steps:
            if step.step_name != "OPEN_DRAFT_PR" or not isinstance(step.output_json, dict):
                continue
            mode = "real_github" if step.output_json.get("mode") == "real_github_write" else "local_record"
            pr_id = step.output_json.get("pr_id")
            pr_number = step.output_json.get("pr_number")
            if pr_id is not None:
                modes[str(pr_id)] = mode
            if pr_number is not None:
                modes[str(pr_number)] = mode
        return modes
