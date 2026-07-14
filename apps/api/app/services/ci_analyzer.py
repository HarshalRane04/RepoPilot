from __future__ import annotations

import json
import re
from uuid import UUID

from repopilot_contracts import AgentRunState, CIAnalysisRequest, CIAnalysisResult, SecuritySeverity
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentRun, AgentStep, PullRequest, SecurityFinding, ValidationResult
from app.services.audit import record_audit
from app.services.evidence_state import security_scan_evidence_summary, validation_evidence_summary
from app.services.model_gateway import ModelGateway
from app.services.security_envelope import redact_text
from app.services.state_machine import TERMINAL_STATES, transition_run


class CISummarySuggestion(BaseModel):
    summary: str
    failure_reasons: list[str] = Field(default_factory=list)
    failed_job: str | None = None
    failing_command: str | None = None
    root_cause: str | None = None
    proposed_fix_path: str | None = None


class CIAnalyzer:
    def __init__(self, *, model_gateway: ModelGateway | None = None) -> None:
        self.model_gateway = model_gateway or ModelGateway()

    async def analyze_pr(
        self,
        db: AsyncSession,
        *,
        pr_id: UUID,
        request: CIAnalysisRequest,
        trusted_evidence: bool = True,
        actor_id: str | None = None,
    ) -> CIAnalysisResult:
        pr = await db.get(PullRequest, pr_id)
        if pr is None:
            raise ValueError(f"Pull request not found: {pr_id}")
        run = await db.get(AgentRun, pr.run_id)
        if run is None:
            raise ValueError(f"Agent run not found for pull request: {pr_id}")

        failure_reasons = self.failure_reasons(request.log_text)
        failed_job = self.failed_job(workflow_name=request.workflow_name, log_text=request.log_text)
        failing_command = self.failing_command(request.log_text)
        proposed_fix_path = self.proposed_fix_path(request.log_text)
        root_cause = failure_reasons[0] if failure_reasons else None
        summary = self.summary(conclusion=request.conclusion, failure_reasons=failure_reasons)
        model_summary = await self.summary_with_model(
            db,
            run_id=run.id,
            workflow_name=request.workflow_name,
            conclusion=request.conclusion,
            log_text=request.log_text,
            deterministic_summary=CISummarySuggestion(
                summary=summary,
                failure_reasons=failure_reasons,
                failed_job=failed_job,
                failing_command=failing_command,
                root_cause=root_cause,
                proposed_fix_path=proposed_fix_path,
            ),
        )
        if model_summary.failure_reasons == failure_reasons:
            summary = model_summary.summary
            failed_job = model_summary.failed_job or failed_job
            failing_command = model_summary.failing_command or failing_command
            root_cause = model_summary.root_cause or root_cause
            proposed_fix_path = model_summary.proposed_fix_path or proposed_fix_path
        ready_for_review = False
        state_before = run.state
        state_change_applied = False
        if trusted_evidence:
            pr.ci_status = request.conclusion
            evidence_is_ready = (
                run.state not in TERMINAL_STATES
                and request.conclusion == "success"
                and await self._can_mark_ready(db, run_id=run.id)
            )
            if evidence_is_ready and run.state == AgentRunState.WAIT_FOR_CI.value:
                pr.status = "ready_for_review"
                await transition_run(
                    db,
                    run=run,
                    next_state=AgentRunState.READY_FOR_REVIEW,
                    actor_type="github",
                    reason="CI succeeded and validation/security evidence is clean.",
                    metadata={"pr_id": str(pr.id), "workflow_name": request.workflow_name},
                )
                state_change_applied = True
            elif evidence_is_ready and run.state == AgentRunState.READY_FOR_REVIEW.value:
                pr.status = "ready_for_review"
            elif request.conclusion in {"failure", "cancelled"} and run.state not in TERMINAL_STATES:
                pr.status = "blocked"
                if run.state == AgentRunState.READY_FOR_REVIEW.value:
                    await transition_run(
                        db,
                        run=run,
                        next_state=AgentRunState.WAIT_FOR_CI,
                        actor_type="github",
                        reason="A later trusted CI result invalidated review readiness.",
                        metadata={"pr_id": str(pr.id), "workflow_name": request.workflow_name},
                    )
                    state_change_applied = True
            ready_for_review = evidence_is_ready and run.state == AgentRunState.READY_FOR_REVIEW.value

        db.add(
            AgentStep(
                run_id=run.id,
                step_name=AgentRunState.WAIT_FOR_CI.value if trusted_evidence else "CI_SIMULATION",
                output_json={
                    "workflow_name": request.workflow_name,
                    "conclusion": request.conclusion,
                    "trusted_evidence": trusted_evidence,
                    "summary": summary,
                    "failure_reasons": failure_reasons,
                    "failed_job": failed_job,
                    "failing_command": failing_command,
                    "root_cause": root_cause,
                    "proposed_fix_path": proposed_fix_path,
                    "run_state_before": state_before,
                    "run_state_after": run.state,
                    "state_change_applied": state_change_applied,
                },
                status=(
                    "succeeded"
                    if request.conclusion == "success"
                    else "failed"
                    if request.conclusion in {"failure", "cancelled"}
                    else "pending"
                ),
            )
        )
        if trusted_evidence and ready_for_review:
            db.add(
                AgentStep(
                    run_id=run.id,
                    step_name=AgentRunState.READY_FOR_REVIEW.value,
                    output_json={"pr_id": str(pr.id), "ci_status": pr.ci_status},
                    status="succeeded",
                )
            )
        await record_audit(
            db,
            actor_type="github" if trusted_evidence else "user",
            actor_id=actor_id,
            action="ci.analyzed" if trusted_evidence else "ci.simulated",
            entity_type="pull_request",
            entity_id=str(pr.id),
            metadata={
                "conclusion": request.conclusion,
                "ready_for_review": ready_for_review,
                "trusted_evidence": trusted_evidence,
                "run_state_before": state_before,
                "run_state_after": run.state,
                "state_change_applied": state_change_applied,
            },
        )
        await db.commit()

        return CIAnalysisResult(
            pr_id=str(pr.id),
            run_id=str(run.id),
            ci_status=(pr.ci_status or request.conclusion) if trusted_evidence else request.conclusion,
            summary=summary,
            failure_reasons=failure_reasons,
            ready_for_review=ready_for_review,
            failed_job=failed_job,
            failing_command=failing_command,
            root_cause=root_cause,
            proposed_fix_path=proposed_fix_path,
        )

    def failure_reasons(self, log_text: str) -> list[str]:
        reasons: list[str] = []
        for raw_line in log_text.splitlines():
            line = redact_text(raw_line.strip())
            lowered = line.lower()
            if not line:
                continue
            if any(marker in lowered for marker in ("error", "failed", "failure", "traceback", "exception")):
                reasons.append(line[:240])
            if len(reasons) >= 5:
                break
        return reasons

    def failed_job(self, *, workflow_name: str, log_text: str) -> str | None:
        for raw_line in log_text.splitlines():
            match = re.search(r"(?i)(job|check)\s*[:=]\s*([A-Za-z0-9_. -]{2,80})", raw_line)
            if match:
                return redact_text(match.group(2).strip())
        return workflow_name or None

    def failing_command(self, log_text: str) -> str | None:
        for raw_line in log_text.splitlines():
            line = raw_line.strip()
            if line.startswith("Run "):
                return redact_text(line.removeprefix("Run ").strip())
            if line.startswith("$ "):
                return redact_text(line[2:].strip())
        return None

    def proposed_fix_path(self, log_text: str) -> str | None:
        for raw_line in log_text.splitlines():
            for token in raw_line[:1000].split():
                candidate = token.strip("`'\"()[]{}<>:,;")
                if "::" in candidate:
                    candidate = candidate.split("::", 1)[0]
                if _looks_like_source_path(candidate):
                    return candidate
        return None

    def summary(self, *, conclusion: str, failure_reasons: list[str]) -> str:
        if conclusion == "success":
            return "CI completed successfully."
        if failure_reasons:
            return f"CI concluded {conclusion}; first failure signal: {failure_reasons[0]}"
        return f"CI concluded {conclusion}; no failure log signal was provided."

    async def summary_with_model(
        self,
        db: AsyncSession,
        *,
        run_id: UUID,
        workflow_name: str,
        conclusion: str,
        log_text: str,
        deterministic_summary: CISummarySuggestion,
    ) -> CISummarySuggestion:
        log_excerpt = "\n".join(redact_text(line) for line in log_text.splitlines()[:120])
        prompt = {
            "workflow_name": workflow_name,
            "conclusion": conclusion,
            "redacted_log_excerpt": log_excerpt[:8000],
            "deterministic_summary": deterministic_summary.model_dump(mode="json"),
            "rules": [
                "Use only the deterministic failure_reasons and redacted log excerpt.",
                "Do not invent validation, security, CI, or file evidence.",
                "If uncertain, return the deterministic summary unchanged.",
            ],
        }
        suggestion = await self.model_gateway.complete_json(
            db,
            run_id=run_id,
            agent_name="ci_analyzer",
            system_prompt="Return only JSON matching CISummarySuggestion.",
            user_prompt=json.dumps(prompt, sort_keys=True),
            response_model=CISummarySuggestion,
            fallback=lambda: deterministic_summary,
        )
        if suggestion.failure_reasons != deterministic_summary.failure_reasons:
            return deterministic_summary
        return suggestion

    async def _can_mark_ready(self, db: AsyncSession, *, run_id: UUID) -> bool:
        patch_hash = await self._latest_patch_hash(db, run_id=run_id)
        if not patch_hash:
            return False
        validations = (
            await db.execute(select(ValidationResult).where(ValidationResult.run_id == run_id))
        ).scalars().all()
        if validation_evidence_summary(validations, patch_hash=patch_hash)["status"] != "passed":
            return False
        security_steps = (
            await db.execute(
                select(AgentStep)
                .where(
                    AgentStep.run_id == run_id,
                    AgentStep.step_name.in_(["RUN_SECURITY_CHECKS", "CODEQL_INGEST"]),
                )
                .order_by(AgentStep.created_at.desc())
            )
        ).scalars().all()
        findings = (
            await db.execute(
                select(SecurityFinding).where(
                    SecurityFinding.run_id == run_id,
                    SecurityFinding.patch_hash == patch_hash,
                )
            )
        ).scalars().all()
        if security_scan_evidence_summary(
            security_steps,
            patch_hash=patch_hash,
            findings=findings,
        )["status"] != "passed":
            return False
        blocking_findings = await db.execute(
            select(SecurityFinding).where(
                SecurityFinding.run_id == run_id,
                SecurityFinding.patch_hash == patch_hash,
                SecurityFinding.status == "open",
                SecurityFinding.severity.in_([SecuritySeverity.HIGH.value, SecuritySeverity.CRITICAL.value]),
            )
        )
        return blocking_findings.scalars().first() is None

    async def _latest_patch_hash(self, db: AsyncSession, *, run_id: UUID) -> str | None:
        result = await db.execute(
            select(AgentStep)
            .where(AgentStep.run_id == run_id, AgentStep.step_name == AgentRunState.IMPLEMENT_PATCH.value)
            .order_by(AgentStep.created_at.desc())
        )
        step = result.scalars().first()
        if not step or not isinstance(step.output_json, dict):
            return None
        value = step.output_json.get("patch_hash")
        return str(value) if value else None


_SOURCE_EXTENSIONS = (".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".md", ".yml", ".yaml")
_SOURCE_PATH_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_./-")


def _looks_like_source_path(value: str) -> bool:
    if not value or value.startswith(("/", "../", "./../")) or ".." in value.split("/"):
        return False
    if not value.endswith(_SOURCE_EXTENSIONS):
        return False
    return all(char in _SOURCE_PATH_CHARS for char in value)
