from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from repopilot_contracts import AgentRunState
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentRun, AgentStep, Plan, PullRequest

SUCCESS_CI_STATUSES = {"success", "passed", "pass", "succeeded"}
FAILURE_CI_STATUSES = {"failure", "failed", "error", "cancelled", "timed_out", "timed-out", "action_required"}


@dataclass(frozen=True)
class CIMetrics:
    ci_total_prs: int = 0
    ci_successful_prs: int = 0
    ci_failed_prs: int = 0
    ci_pass_rate: float = 0.0
    ci_first_run_pass_count: int = 0
    ci_first_run_ci_pass_rate: float = 0.0
    ci_revision_fixup_attempts: int = 0
    ci_revised_pr_count: int = 0
    ci_pass_after_revision_count: int = 0
    ci_pass_after_revision_rate: float = 0.0
    ci_average_fixup_attempts_per_revised_pr: float = 0.0

    def as_dict(self) -> dict[str, int | float]:
        return {
            "ci_total_prs": self.ci_total_prs,
            "ci_successful_prs": self.ci_successful_prs,
            "ci_failed_prs": self.ci_failed_prs,
            "ci_pass_rate": self.ci_pass_rate,
            "ci_first_run_pass_count": self.ci_first_run_pass_count,
            "ci_first_run_ci_pass_rate": self.ci_first_run_ci_pass_rate,
            "ci_revision_fixup_attempts": self.ci_revision_fixup_attempts,
            "ci_revised_pr_count": self.ci_revised_pr_count,
            "ci_pass_after_revision_count": self.ci_pass_after_revision_count,
            "ci_pass_after_revision_rate": self.ci_pass_after_revision_rate,
            "ci_average_fixup_attempts_per_revised_pr": self.ci_average_fixup_attempts_per_revised_pr,
        }


class CIMetricsCalculator:
    def calculate(
        self,
        *,
        pull_requests: list[PullRequest],
        runs: list[AgentRun],
        plans: list[Plan],
        steps: list[AgentStep],
    ) -> CIMetrics:
        runs_by_id = {run.id: run for run in runs}
        ci_steps_by_run = self._ci_steps_by_run(steps)
        revision_counts_by_issue = self._revision_counts_by_issue(plans)
        revision_plan_ids = {plan.id for plan in plans if self._is_revision_plan(plan)}

        ci_total = 0
        ci_success = 0
        ci_failed = 0
        first_run_passes = 0
        revised_prs = 0
        pass_after_revision = 0

        for pr in pull_requests:
            run = runs_by_id.get(pr.run_id)
            run_ci_steps = ci_steps_by_run.get(pr.run_id, [])
            latest_status = self._latest_ci_status(pr, run_ci_steps)
            first_status = self._first_ci_status(pr, run_ci_steps)
            if latest_status is None and first_status is None:
                continue

            ci_total += 1
            if is_success_ci_status(latest_status):
                ci_success += 1
            elif is_failure_ci_status(latest_status):
                ci_failed += 1

            if is_success_ci_status(first_status):
                first_run_passes += 1

            fixup_attempts = self._run_fixup_attempts(
                run=run,
                revision_counts_by_issue=revision_counts_by_issue,
                revision_plan_ids=revision_plan_ids,
            )
            if fixup_attempts > 0:
                revised_prs += 1
                if is_success_ci_status(latest_status):
                    pass_after_revision += 1

        total_fixups = sum(revision_counts_by_issue.values())
        return CIMetrics(
            ci_total_prs=ci_total,
            ci_successful_prs=ci_success,
            ci_failed_prs=ci_failed,
            ci_pass_rate=ratio(ci_success, ci_total),
            ci_first_run_pass_count=first_run_passes,
            ci_first_run_ci_pass_rate=ratio(first_run_passes, ci_total),
            ci_revision_fixup_attempts=total_fixups,
            ci_revised_pr_count=revised_prs,
            ci_pass_after_revision_count=pass_after_revision,
            ci_pass_after_revision_rate=ratio(pass_after_revision, revised_prs),
            ci_average_fixup_attempts_per_revised_pr=ratio(total_fixups, revised_prs),
        )

    def _ci_steps_by_run(self, steps: list[AgentStep]) -> dict[UUID, list[AgentStep]]:
        grouped: dict[UUID, list[AgentStep]] = {}
        for step in steps:
            if step.step_name != AgentRunState.WAIT_FOR_CI.value:
                continue
            grouped.setdefault(step.run_id, []).append(step)
        for run_steps in grouped.values():
            run_steps.sort(key=lambda step: step.created_at or datetime.min.replace(tzinfo=UTC))
        return grouped

    def _latest_ci_status(self, pr: PullRequest, steps: list[AgentStep]) -> str | None:
        if pr.ci_status:
            return normalize_ci_status(pr.ci_status)
        for step in reversed(steps):
            status = self._step_ci_status(step)
            if status:
                return status
        return None

    def _first_ci_status(self, pr: PullRequest, steps: list[AgentStep]) -> str | None:
        for step in steps:
            status = self._step_ci_status(step)
            if status:
                return status
        return normalize_ci_status(pr.ci_status)

    def _step_ci_status(self, step: AgentStep) -> str | None:
        output = step.output_json if isinstance(step.output_json, dict) else {}
        status = output.get("conclusion") or output.get("ci_status") or output.get("status")
        return normalize_ci_status(status) if isinstance(status, str) else None

    def _revision_counts_by_issue(self, plans: list[Plan]) -> dict[UUID, int]:
        counts: dict[UUID, int] = {}
        for plan in plans:
            if self._is_revision_plan(plan):
                counts[plan.issue_id] = counts.get(plan.issue_id, 0) + 1
        return counts

    def _is_revision_plan(self, plan: Plan) -> bool:
        payload = plan.plan_json if isinstance(plan.plan_json, dict) else {}
        return bool(payload.get("revision_parent_plan_id"))

    def _run_fixup_attempts(
        self,
        *,
        run: AgentRun | None,
        revision_counts_by_issue: dict[UUID, int],
        revision_plan_ids: set[UUID],
    ) -> int:
        if run is None:
            return 0
        attempts = revision_counts_by_issue.get(run.issue_id, 0) if run.issue_id is not None else 0
        if attempts == 0 and run.plan_id in revision_plan_ids:
            return 1
        return attempts


class CIMetricsService:
    def __init__(self, *, calculator: CIMetricsCalculator | None = None) -> None:
        self.calculator = calculator or CIMetricsCalculator()

    async def overview(self, db: AsyncSession) -> CIMetrics:
        pull_requests = (await db.execute(select(PullRequest))).scalars().all()
        runs = (await db.execute(select(AgentRun))).scalars().all()
        plans = (await db.execute(select(Plan))).scalars().all()
        steps = (
            await db.execute(select(AgentStep).where(AgentStep.step_name == AgentRunState.WAIT_FOR_CI.value))
        ).scalars().all()
        return self.calculator.calculate(
            pull_requests=list(pull_requests),
            runs=list(runs),
            plans=list(plans),
            steps=list(steps),
        )


def normalize_ci_status(status: str | None) -> str | None:
    if not status:
        return None
    return status.strip().lower().replace(" ", "_")


def is_success_ci_status(status: str | None) -> bool:
    return normalize_ci_status(status) in SUCCESS_CI_STATUSES


def is_failure_ci_status(status: str | None) -> bool:
    return normalize_ci_status(status) in FAILURE_CI_STATUSES


def ratio(numerator: int | float, denominator: int | float) -> float:
    if denominator == 0:
        return 0.0
    return round(float(numerator) / float(denominator), 4)
