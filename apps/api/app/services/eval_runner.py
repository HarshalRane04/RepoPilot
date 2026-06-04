from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from repopilot_contracts import EvalRunRequest, EvalRunResult, EvalTaskFixture, EvalTaskOutcome
from repopilot_evals import (
    FixtureVerifier,
    PatchQualityEvidence,
    PatchQualityScorer,
    PlanQualityEvidence,
    PlanQualityScorer,
    ProviderComparisonScorer,
    ProviderEvalEvidence,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentRun, EvalRun, Plan, PullRequest, SecurityFinding, ValidationResult
from app.services.ci_metrics import CIMetricsService


class EvalRunner:
    def __init__(self, *, benchmark_path: Path | None = None) -> None:
        self.benchmark_path = benchmark_path or Path(__file__).resolve().parents[4] / "packages" / "evals" / "benchmark_tasks.json"
        self.fixture_verifier = FixtureVerifier(fixture_root=self.benchmark_path.parent)

    async def run(self, db: AsyncSession, *, request: EvalRunRequest) -> EvalRunResult:
        benchmark = self.load_benchmark()
        tasks = benchmark["tasks"][: request.task_count]
        outcomes = [self.evaluate_fixture(task) for task in tasks]
        plan_quality_results = self.evaluate_observed_plan_quality(
            tasks=tasks,
            observed_plan_results=request.model_settings.get("observed_plan_results"),
        )
        patch_quality_results = self.evaluate_observed_patch_quality(
            tasks=tasks,
            observed_task_results=request.model_settings.get("observed_task_results"),
        )
        provider_comparison_results = self.evaluate_provider_comparisons(
            provider_eval_results=request.model_settings.get("provider_eval_results"),
        )
        metrics = await self.metrics(
            db,
            task_count=len(tasks),
            outcomes=outcomes,
            benchmark=benchmark,
            plan_quality_results=plan_quality_results,
            patch_quality_results=patch_quality_results,
            provider_comparison_results=provider_comparison_results,
        )
        eval_run = EvalRun(
            benchmark_version=request.benchmark_version,
            model_config=request.model_settings,
            metrics_json=metrics,
            report_uri="pending",
        )
        db.add(eval_run)
        await db.flush()
        eval_run.report_uri = f"local://evals/{eval_run.id}"
        await db.commit()
        await db.refresh(eval_run)
        return EvalRunResult(
            eval_run_id=str(eval_run.id),
            benchmark_version=eval_run.benchmark_version,
            metrics=eval_run.metrics_json,
            report_uri=eval_run.report_uri or f"local://evals/{eval_run.id}",
            task_outcomes=outcomes,
        )

    def load_benchmark(self) -> dict[str, Any]:
        payload = json.loads(self.benchmark_path.read_text(encoding="utf-8"))
        raw_tasks = payload.get("tasks")
        if not isinstance(raw_tasks, list):
            raise ValueError("Benchmark file must contain a tasks list.")
        tasks: list[EvalTaskFixture] = []
        errors: list[str] = []
        seen_ids: set[str] = set()
        for index, raw_task in enumerate(raw_tasks, start=1):
            try:
                task = EvalTaskFixture.model_validate(raw_task)
            except ValidationError as exc:
                errors.append(f"task[{index}]: {exc.errors()}")
                continue
            if task.id in seen_ids:
                errors.append(f"task[{index}]: duplicate id {task.id}")
                continue
            seen_ids.add(task.id)
            tasks.append(task)
        if errors:
            raise ValueError("; ".join(errors))
        return {
            "version": str(payload.get("version") or "unknown"),
            "description": str(payload.get("description") or ""),
            "quality_gates": payload.get("quality_gates") if isinstance(payload.get("quality_gates"), dict) else {},
            "tasks": tasks,
        }

    def evaluate_fixture(self, task: EvalTaskFixture) -> EvalTaskOutcome:
        failure_reasons: list[str] = []
        if not task.expected_changed_files and task.expected_security_result == "pass":
            failure_reasons.append("Expected changed files are required for non-security-block tasks.")
        if not task.acceptance_criteria:
            failure_reasons.append("Acceptance criteria are required.")
        if not task.expected_tests:
            failure_reasons.append("Expected validation evidence is required.")
        if any(path in task.disallowed_changes for path in task.expected_changed_files):
            failure_reasons.append("Expected changed files overlap with disallowed changes.")
        if task.expected_security_result in {"block", "escalate"} and not task.category.startswith("security"):
            failure_reasons.append("Only security tasks should expect block/escalate security outcomes.")
        failure_reasons.extend(self.fixture_verifier.evaluate_task(task))
        score = 1.0 if not failure_reasons else 0.0
        return EvalTaskOutcome(
            task_id=task.id,
            category=task.category,
            status="passed" if score == 1.0 else "failed",
            score=score,
            failure_reasons=failure_reasons,
        )

    def evaluate_observed_patch_quality(
        self,
        *,
        tasks: list[EvalTaskFixture],
        observed_task_results: Any,
    ) -> list[dict[str, object]]:
        if not isinstance(observed_task_results, list):
            return []
        task_by_id = {task.id: task for task in tasks}
        scorer = PatchQualityScorer()
        results: list[dict[str, object]] = []
        for raw_result in observed_task_results:
            if not isinstance(raw_result, dict):
                results.append(
                    {
                        "task_id": "",
                        "category": "unknown",
                        "status": "failed",
                        "score": 0.0,
                        "failure_reasons": ["Observed patch-quality result must be an object."],
                    }
                )
                continue
            evidence = PatchQualityEvidence.from_mapping(raw_result)
            task = task_by_id.get(evidence.task_id)
            if task is None:
                results.append(
                    {
                        "task_id": evidence.task_id,
                        "category": "unknown",
                        "status": "failed",
                        "score": 0.0,
                        "failure_reasons": [f"Observed patch-quality result references unknown task: {evidence.task_id}."],
                    }
                )
                continue
            results.append(scorer.score(task, evidence).as_dict())
        return results

    def evaluate_observed_plan_quality(
        self,
        *,
        tasks: list[EvalTaskFixture],
        observed_plan_results: Any,
    ) -> list[dict[str, object]]:
        if not isinstance(observed_plan_results, list):
            return []
        task_by_id = {task.id: task for task in tasks}
        scorer = PlanQualityScorer()
        results: list[dict[str, object]] = []
        for raw_result in observed_plan_results:
            if not isinstance(raw_result, dict):
                results.append(
                    {
                        "task_id": "",
                        "category": "unknown",
                        "status": "failed",
                        "score": 0.0,
                        "context_precision": 0.0,
                        "failure_reasons": ["Observed plan-quality result must be an object."],
                    }
                )
                continue
            evidence = PlanQualityEvidence.from_mapping(raw_result)
            task = task_by_id.get(evidence.task_id)
            if task is None:
                results.append(
                    {
                        "task_id": evidence.task_id,
                        "category": "unknown",
                        "status": "failed",
                        "score": 0.0,
                        "context_precision": 0.0,
                        "failure_reasons": [f"Observed plan-quality result references unknown task: {evidence.task_id}."],
                    }
                )
                continue
            results.append(scorer.score(task, evidence).as_dict())
        return results

    def evaluate_provider_comparisons(self, *, provider_eval_results: Any) -> list[dict[str, object]]:
        if not isinstance(provider_eval_results, list):
            return []
        evidence_items = [
            ProviderEvalEvidence.from_mapping(raw_result)
            for raw_result in provider_eval_results
            if isinstance(raw_result, dict)
        ]
        return [result.as_dict() for result in ProviderComparisonScorer().score_all(evidence_items)]

    async def metrics(
        self,
        db: AsyncSession,
        *,
        task_count: int,
        outcomes: list[EvalTaskOutcome] | None = None,
        benchmark: dict[str, Any] | None = None,
        plan_quality_results: list[dict[str, object]] | None = None,
        patch_quality_results: list[dict[str, object]] | None = None,
        provider_comparison_results: list[dict[str, object]] | None = None,
    ) -> dict[str, object]:
        outcomes = outcomes or []
        plan_quality_results = plan_quality_results or []
        patch_quality_results = patch_quality_results or []
        provider_comparison_results = provider_comparison_results or []
        run_count = await db.scalar(select(func.count()).select_from(AgentRun)) or 0
        approved_plans = await db.scalar(select(func.count()).select_from(Plan).where(Plan.approval_status == "approved")) or 0
        total_plans = await db.scalar(select(func.count()).select_from(Plan)) or 0
        passed_validations = (
            await db.scalar(select(func.count()).select_from(ValidationResult).where(ValidationResult.status == "passed")) or 0
        )
        ready_prs = (
            await db.scalar(select(func.count()).select_from(PullRequest).where(PullRequest.status == "ready_for_review")) or 0
        )
        ci_metrics = await CIMetricsService().overview(db)
        blocking_findings = (
            await db.scalar(
                select(func.count())
                .select_from(SecurityFinding)
                .where(SecurityFinding.severity.in_(["high", "critical"]), SecurityFinding.status == "open")
            )
            or 0
        )
        total_findings = await db.scalar(select(func.count()).select_from(SecurityFinding)) or 0

        passed_tasks = sum(1 for outcome in outcomes if outcome.status == "passed")
        category_counts = Counter(outcome.category for outcome in outcomes)
        category_passed: dict[str, int] = defaultdict(int)
        for outcome in outcomes:
            if outcome.status == "passed":
                category_passed[outcome.category] += 1

        quality_gates = (benchmark or {}).get("quality_gates") if isinstance(benchmark, dict) else {}
        task_outcomes = [outcome.model_dump(mode="json") for outcome in outcomes]
        security_expected = sum(1 for outcome in outcomes if outcome.category == "security")
        benchmark_tasks = (benchmark or {}).get("tasks") if isinstance(benchmark, dict) else []
        fixture_repositories = sorted({task.fixture_repository for task in benchmark_tasks}) if benchmark_tasks else []
        executable_repositories = [
            repo
            for repo in fixture_repositories
            if self.fixture_verifier.repository_is_executable(self.benchmark_path.parent / repo)
        ]
        fixture_file_checks = self.fixture_verifier.file_check_summary(benchmark_tasks if benchmark_tasks else [])
        passed_plan_quality = sum(1 for result in plan_quality_results if result.get("status") == "passed")
        context_precision_values = [
            float(result.get("context_precision") or 0.0)
            for result in plan_quality_results
            if isinstance(result.get("context_precision"), (int, float))
        ]
        context_precision = round(sum(context_precision_values) / len(context_precision_values), 4) if context_precision_values else 0.0
        passed_patch_quality = sum(1 for result in patch_quality_results if result.get("status") == "passed")
        human_edit_distance_values = [
            float(result.get("human_edit_distance"))
            for result in patch_quality_results
            if isinstance(result.get("human_edit_distance"), (int, float))
        ]
        human_edit_distance = (
            round(sum(human_edit_distance_values) / len(human_edit_distance_values), 4)
            if human_edit_distance_values
            else None
        )

        return {
            "benchmark_task_count": task_count,
            "task_pass_rate": self._ratio(passed_tasks, len(outcomes)),
            "fixture_schema_pass_rate": 1.0 if outcomes else 0.0,
            "fixture_repository_count": len(fixture_repositories),
            "executable_fixture_repositories": executable_repositories,
            "fixture_repository_pass_rate": self._ratio(len(executable_repositories), len(fixture_repositories)),
            "fixture_file_coverage_rate": self._ratio(fixture_file_checks.present, fixture_file_checks.required),
            "category_pass_rates": {
                category: self._ratio(category_passed[category], count)
                for category, count in sorted(category_counts.items())
            },
            "task_outcomes": task_outcomes,
            "failed_tasks": [outcome.model_dump(mode="json") for outcome in outcomes if outcome.status == "failed"],
            "patch_quality_observed_count": len(patch_quality_results),
            "patch_quality_pass_rate": self._ratio(passed_patch_quality, len(patch_quality_results)),
            "human_edit_distance": human_edit_distance,
            "patch_quality_results": patch_quality_results,
            "failed_patch_quality_results": [
                result for result in patch_quality_results if result.get("status") == "failed"
            ],
            "provider_comparison_count": len(provider_comparison_results),
            "provider_comparison_results": provider_comparison_results,
            "best_provider_by_quality": provider_comparison_results[0] if provider_comparison_results else None,
            "quality_gates": quality_gates or {},
            "plan_quality_observed_count": len(plan_quality_results),
            "plan_quality_pass_rate": self._ratio(passed_plan_quality, len(plan_quality_results)),
            "context_precision": context_precision,
            "plan_quality_results": plan_quality_results,
            "failed_plan_quality_results": [
                result for result in plan_quality_results if result.get("status") == "failed"
            ],
            "quality_gate_results": self._quality_gate_results(
                quality_gates=quality_gates if isinstance(quality_gates, dict) else {},
                task_count=task_count,
                task_pass_rate=self._ratio(passed_tasks, len(outcomes)),
                security_task_count=security_expected,
                fixture_repository_pass_rate=self._ratio(len(executable_repositories), len(fixture_repositories)),
                fixture_file_coverage_rate=self._ratio(fixture_file_checks.present, fixture_file_checks.required),
                plan_quality_observed_count=len(plan_quality_results),
                plan_quality_pass_rate=self._ratio(passed_plan_quality, len(plan_quality_results)),
                context_precision=context_precision,
                patch_quality_observed_count=len(patch_quality_results),
                patch_quality_pass_rate=self._ratio(passed_patch_quality, len(patch_quality_results)),
                human_edit_distance=human_edit_distance,
                provider_comparison_count=len(provider_comparison_results),
            ),
            "observed_agent_runs": run_count,
            "plan_approval_rate": self._ratio(approved_plans, total_plans),
            "patch_success_rate": self._ratio(passed_validations, run_count),
            "first_run_ci_pass_rate": ci_metrics.ci_first_run_ci_pass_rate,
            "ci_total_prs": ci_metrics.ci_total_prs,
            "ci_successful_prs": ci_metrics.ci_successful_prs,
            "ci_failed_prs": ci_metrics.ci_failed_prs,
            "ci_pass_rate": ci_metrics.ci_pass_rate,
            "ci_first_run_pass_count": ci_metrics.ci_first_run_pass_count,
            "ci_revision_fixup_attempts": ci_metrics.ci_revision_fixup_attempts,
            "ci_revised_pr_count": ci_metrics.ci_revised_pr_count,
            "ci_pass_after_revision_count": ci_metrics.ci_pass_after_revision_count,
            "ci_pass_after_revision_rate": ci_metrics.ci_pass_after_revision_rate,
            "ci_average_fixup_attempts_per_revised_pr": ci_metrics.ci_average_fixup_attempts_per_revised_pr,
            "security_block_rate": self._ratio(blocking_findings, max(total_findings, 1)),
            "ready_for_review_prs": ready_prs,
            "blocking_security_findings": blocking_findings,
            "cost_per_run": 0.0,
            "latency_per_stage_ms": {},
        }

    def _quality_gate_results(
        self,
        *,
        quality_gates: dict[str, Any],
        task_count: int,
        task_pass_rate: float,
        security_task_count: int,
        fixture_repository_pass_rate: float = 0.0,
        fixture_file_coverage_rate: float = 0.0,
        plan_quality_observed_count: int = 0,
        plan_quality_pass_rate: float = 0.0,
        context_precision: float = 0.0,
        patch_quality_observed_count: int = 0,
        patch_quality_pass_rate: float = 0.0,
        human_edit_distance: float | None = None,
        provider_comparison_count: int = 0,
    ) -> dict[str, bool]:
        return {
            "minimum_task_pass_rate_for_v1": task_pass_rate >= float(quality_gates.get("minimum_task_pass_rate_for_v1", 0.0)),
            "minimum_fixture_count_for_v1": task_count >= int(quality_gates.get("minimum_fixture_count_for_v1", 0)),
            "security_block_tasks_required": security_task_count >= int(quality_gates.get("security_block_tasks_required", 0)),
            "executable_fixture_repositories_required": fixture_repository_pass_rate >= float(quality_gates.get("minimum_fixture_repository_pass_rate_for_v1", 1.0)),
            "fixture_file_coverage_required": fixture_file_coverage_rate >= float(quality_gates.get("minimum_fixture_file_coverage_for_v1", 1.0)),
            "plan_quality_observations_required": plan_quality_observed_count >= int(quality_gates.get("minimum_plan_quality_observations_for_v1", 0)),
            "plan_quality_pass_rate_required": plan_quality_pass_rate >= float(quality_gates.get("minimum_plan_quality_pass_rate_for_v1", 0.0)),
            "context_precision_required": context_precision >= float(quality_gates.get("minimum_context_precision_for_v1", 0.0)),
            "patch_quality_observations_required": patch_quality_observed_count >= int(quality_gates.get("minimum_patch_quality_observations_for_v1", 0)),
            "patch_quality_pass_rate_required": patch_quality_pass_rate >= float(quality_gates.get("minimum_patch_quality_pass_rate_for_v1", 0.0)),
            "human_edit_distance_required": (
                human_edit_distance is not None
                and human_edit_distance <= float(quality_gates.get("maximum_human_edit_distance_for_v1", 1.0))
            ),
            "provider_comparisons_required": provider_comparison_count >= int(quality_gates.get("minimum_provider_comparisons_for_v1", 0)),
        }

    def _ratio(self, numerator: int, denominator: int) -> float:
        if denominator <= 0:
            return 0.0
        return round(numerator / denominator, 4)
