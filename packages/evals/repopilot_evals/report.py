from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from repopilot_contracts import EvalTaskFixture, EvalTaskOutcome

from .fixtures import FixtureVerifier
from .patch_quality import PatchQualityEvidence, PatchQualityScorer
from .plan_quality import PlanQualityEvidence, PlanQualityScorer
from .provider_comparison import ProviderComparisonScorer, ProviderEvalEvidence


@dataclass(frozen=True)
class BenchmarkReport:
    benchmark_version: str
    description: str
    metrics: dict[str, object]
    task_outcomes: list[EvalTaskOutcome]

    def as_dict(self) -> dict[str, object]:
        return {
            "benchmark_version": self.benchmark_version,
            "description": self.description,
            "metrics": self.metrics,
            "task_outcomes": [outcome.model_dump(mode="json") for outcome in self.task_outcomes],
        }


class BenchmarkReportBuilder:
    def __init__(self, *, benchmark_path: Path | None = None) -> None:
        self.benchmark_path = benchmark_path or Path(__file__).resolve().parents[1] / "benchmark_tasks.json"
        self.fixture_verifier = FixtureVerifier(fixture_root=self.benchmark_path.parent)

    def build(
        self,
        *,
        task_count: int | None = None,
        observed_evidence: dict[str, Any] | None = None,
    ) -> BenchmarkReport:
        benchmark = self.load_benchmark()
        tasks = benchmark["tasks"][:task_count] if task_count is not None else benchmark["tasks"]
        evidence = observed_evidence or {}
        model_config = evidence.get("model_config") if isinstance(evidence.get("model_config"), dict) else evidence

        task_outcomes = [self.evaluate_fixture(task) for task in tasks]
        plan_quality_results = self.evaluate_observed_plan_quality(
            tasks=tasks,
            observed_plan_results=model_config.get("observed_plan_results"),
        )
        patch_quality_results = self.evaluate_observed_patch_quality(
            tasks=tasks,
            observed_task_results=model_config.get("observed_task_results"),
        )
        provider_comparison_results = self.evaluate_provider_comparisons(
            provider_eval_results=model_config.get("provider_eval_results"),
        )
        metrics = self.metrics(
            task_outcomes=task_outcomes,
            tasks=tasks,
            quality_gates=benchmark["quality_gates"],
            plan_quality_results=plan_quality_results,
            patch_quality_results=patch_quality_results,
            provider_comparison_results=provider_comparison_results,
        )
        return BenchmarkReport(
            benchmark_version=benchmark["version"],
            description=benchmark["description"],
            metrics=metrics,
            task_outcomes=task_outcomes,
        )

    def write(
        self,
        *,
        output_dir: Path,
        report_name: str = "v1-local-eval-report",
        task_count: int | None = None,
        observed_evidence: dict[str, Any] | None = None,
    ) -> tuple[Path, Path, BenchmarkReport]:
        report = self.build(task_count=task_count, observed_evidence=observed_evidence)
        output_dir.mkdir(parents=True, exist_ok=True)
        json_path = output_dir / f"{report_name}.json"
        markdown_path = output_dir / f"{report_name}.md"
        json_path.write_text(json.dumps(report.as_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        markdown_path.write_text(self.render_markdown(report), encoding="utf-8")
        return markdown_path, json_path, report

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
                results.append(self._invalid_result("Observed plan-quality result must be an object."))
                continue
            evidence = PlanQualityEvidence.from_mapping(raw_result)
            task = task_by_id.get(evidence.task_id)
            if task is None:
                results.append(
                    self._invalid_result(f"Observed plan-quality result references unknown task: {evidence.task_id}.")
                )
                continue
            results.append(scorer.score(task, evidence).as_dict())
        return results

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
                results.append(self._invalid_result("Observed patch-quality result must be an object."))
                continue
            evidence = PatchQualityEvidence.from_mapping(raw_result)
            task = task_by_id.get(evidence.task_id)
            if task is None:
                results.append(
                    self._invalid_result(f"Observed patch-quality result references unknown task: {evidence.task_id}.")
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

    def metrics(
        self,
        *,
        task_outcomes: list[EvalTaskOutcome],
        tasks: list[EvalTaskFixture],
        quality_gates: dict[str, Any],
        plan_quality_results: list[dict[str, object]],
        patch_quality_results: list[dict[str, object]],
        provider_comparison_results: list[dict[str, object]],
    ) -> dict[str, object]:
        passed_tasks = sum(1 for outcome in task_outcomes if outcome.status == "passed")
        category_counts = Counter(outcome.category for outcome in task_outcomes)
        category_passed: dict[str, int] = defaultdict(int)
        for outcome in task_outcomes:
            if outcome.status == "passed":
                category_passed[outcome.category] += 1

        fixture_repositories = sorted({task.fixture_repository for task in tasks})
        executable_repositories = [
            repo
            for repo in fixture_repositories
            if self.fixture_verifier.repository_is_executable(self.benchmark_path.parent / repo)
        ]
        fixture_file_checks = self.fixture_verifier.file_check_summary(tasks)
        passed_plan_quality = sum(1 for result in plan_quality_results if result.get("status") == "passed")
        passed_patch_quality = sum(1 for result in patch_quality_results if result.get("status") == "passed")
        context_precision_values = [
            float(result.get("context_precision") or 0.0)
            for result in plan_quality_results
            if isinstance(result.get("context_precision"), (int, float))
        ]
        human_edit_distance_values = [
            float(result.get("human_edit_distance"))
            for result in patch_quality_results
            if isinstance(result.get("human_edit_distance"), (int, float))
        ]
        context_precision = round(sum(context_precision_values) / len(context_precision_values), 4) if context_precision_values else 0.0
        human_edit_distance = (
            round(sum(human_edit_distance_values) / len(human_edit_distance_values), 4)
            if human_edit_distance_values
            else None
        )
        metrics: dict[str, object] = {
            "benchmark_task_count": len(task_outcomes),
            "task_pass_rate": self._ratio(passed_tasks, len(task_outcomes)),
            "fixture_schema_pass_rate": 1.0 if task_outcomes else 0.0,
            "fixture_repository_count": len(fixture_repositories),
            "executable_fixture_repositories": executable_repositories,
            "fixture_repository_pass_rate": self._ratio(len(executable_repositories), len(fixture_repositories)),
            "fixture_file_coverage_rate": self._ratio(fixture_file_checks.present, fixture_file_checks.required),
            "category_pass_rates": {
                category: self._ratio(category_passed[category], count)
                for category, count in sorted(category_counts.items())
            },
            "task_outcomes": [outcome.model_dump(mode="json") for outcome in task_outcomes],
            "failed_tasks": [outcome.model_dump(mode="json") for outcome in task_outcomes if outcome.status == "failed"],
            "plan_quality_observed_count": len(plan_quality_results),
            "plan_quality_pass_rate": self._ratio(passed_plan_quality, len(plan_quality_results)),
            "context_precision": context_precision,
            "plan_quality_results": plan_quality_results,
            "failed_plan_quality_results": [result for result in plan_quality_results if result.get("status") == "failed"],
            "patch_quality_observed_count": len(patch_quality_results),
            "patch_quality_pass_rate": self._ratio(passed_patch_quality, len(patch_quality_results)),
            "human_edit_distance": human_edit_distance,
            "patch_quality_results": patch_quality_results,
            "failed_patch_quality_results": [result for result in patch_quality_results if result.get("status") == "failed"],
            "provider_comparison_count": len(provider_comparison_results),
            "provider_comparison_results": provider_comparison_results,
            "best_provider_by_quality": provider_comparison_results[0] if provider_comparison_results else None,
            "quality_gates": quality_gates,
        }
        metrics["quality_gate_results"] = self.quality_gate_results(metrics=metrics, quality_gates=quality_gates)
        return metrics

    def quality_gate_results(self, *, metrics: dict[str, object], quality_gates: dict[str, Any]) -> dict[str, bool]:
        human_edit_distance = metrics.get("human_edit_distance")
        return {
            "minimum_task_pass_rate_for_v1": float(metrics["task_pass_rate"]) >= float(quality_gates.get("minimum_task_pass_rate_for_v1", 0.0)),
            "minimum_fixture_count_for_v1": int(metrics["benchmark_task_count"]) >= int(quality_gates.get("minimum_fixture_count_for_v1", 0)),
            "security_block_tasks_required": self.security_task_count(metrics) >= int(quality_gates.get("security_block_tasks_required", 0)),
            "executable_fixture_repositories_required": float(metrics["fixture_repository_pass_rate"]) >= float(quality_gates.get("minimum_fixture_repository_pass_rate_for_v1", 1.0)),
            "fixture_file_coverage_required": float(metrics["fixture_file_coverage_rate"]) >= float(quality_gates.get("minimum_fixture_file_coverage_for_v1", 1.0)),
            "plan_quality_observations_required": int(metrics["plan_quality_observed_count"]) >= int(quality_gates.get("minimum_plan_quality_observations_for_v1", 0)),
            "plan_quality_pass_rate_required": float(metrics["plan_quality_pass_rate"]) >= float(quality_gates.get("minimum_plan_quality_pass_rate_for_v1", 0.0)),
            "context_precision_required": float(metrics["context_precision"]) >= float(quality_gates.get("minimum_context_precision_for_v1", 0.0)),
            "patch_quality_observations_required": int(metrics["patch_quality_observed_count"]) >= int(quality_gates.get("minimum_patch_quality_observations_for_v1", 0)),
            "patch_quality_pass_rate_required": float(metrics["patch_quality_pass_rate"]) >= float(quality_gates.get("minimum_patch_quality_pass_rate_for_v1", 0.0)),
            "human_edit_distance_required": human_edit_distance is not None
            and float(human_edit_distance) <= float(quality_gates.get("maximum_human_edit_distance_for_v1", 1.0)),
            "provider_comparisons_required": int(metrics["provider_comparison_count"]) >= int(quality_gates.get("minimum_provider_comparisons_for_v1", 0)),
        }

    def security_task_count(self, metrics: dict[str, object]) -> int:
        task_outcomes = metrics.get("task_outcomes")
        if not isinstance(task_outcomes, list):
            return 0
        return sum(
            1
            for outcome in task_outcomes
            if isinstance(outcome, dict) and str(outcome.get("category") or "").startswith("security")
        )

    def render_markdown(self, report: BenchmarkReport) -> str:
        metrics = report.metrics
        gates = metrics.get("quality_gate_results")
        gate_items = gates.items() if isinstance(gates, dict) else []
        category_rates = metrics.get("category_pass_rates")
        category_items = category_rates.items() if isinstance(category_rates, dict) else []
        providers = metrics.get("provider_comparison_results")
        provider_items = providers if isinstance(providers, list) else []

        lines = [
            "# RepoPilot Eval Report",
            "",
            f"- Benchmark version: `{report.benchmark_version}`",
            f"- Task count: `{metrics['benchmark_task_count']}`",
            f"- Task pass rate: `{metrics['task_pass_rate']}`",
            f"- Fixture repository pass rate: `{metrics['fixture_repository_pass_rate']}`",
            f"- Fixture file coverage rate: `{metrics['fixture_file_coverage_rate']}`",
            f"- Plan quality pass rate: `{metrics['plan_quality_pass_rate']}` from `{metrics['plan_quality_observed_count']}` observations",
            f"- Context precision: `{metrics['context_precision']}`",
            f"- Patch quality pass rate: `{metrics['patch_quality_pass_rate']}` from `{metrics['patch_quality_observed_count']}` observations",
            f"- Human edit distance: `{self._display_optional(metrics['human_edit_distance'])}`",
            f"- Provider comparisons: `{metrics['provider_comparison_count']}`",
            "",
            "## Quality Gates",
            "",
        ]
        lines.extend(f"- `{name}`: `{passed}`" for name, passed in gate_items)
        lines.extend(["", "## Category Pass Rates", ""])
        lines.extend(f"- `{category}`: `{rate}`" for category, rate in category_items)
        lines.extend(["", "## Provider Comparison", ""])
        if provider_items:
            lines.extend(
                [
                    "| Rank | Provider | Model | Quality | Cost/Run | Latency ms |",
                    "|---|---|---|---|---|---|",
                ]
            )
            for index, provider in enumerate(provider_items, start=1):
                if not isinstance(provider, dict):
                    continue
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            str(index),
                            str(provider.get("provider")),
                            str(provider.get("model")),
                            str(provider.get("quality_score")),
                            str(provider.get("cost_per_run")),
                            str(provider.get("latency_ms")),
                        ]
                    )
                    + " |"
                )
        else:
            lines.append("No provider comparison evidence supplied.")
        lines.extend(["", "## Failed Tasks", ""])
        failed_tasks = metrics.get("failed_tasks")
        if isinstance(failed_tasks, list) and failed_tasks:
            for task in failed_tasks:
                if isinstance(task, dict):
                    lines.append(f"- `{task.get('task_id')}`: {', '.join(task.get('failure_reasons') or [])}")
        else:
            lines.append("No fixture tasks failed.")
        lines.extend(
            [
                "",
                "## Evidence Limitations",
                "",
                "- This report proves local fixture metadata and any supplied observed evidence only.",
                "- Credentialed GitHub writes, provider-backed model attempts, live CI archives, and deployment proof require separate smoke evidence.",
                "",
            ]
        )
        return "\n".join(lines)

    def _invalid_result(self, reason: str) -> dict[str, object]:
        return {
            "task_id": "",
            "category": "unknown",
            "status": "failed",
            "score": 0.0,
            "failure_reasons": [reason],
        }

    def _ratio(self, numerator: int, denominator: int) -> float:
        if denominator <= 0:
            return 0.0
        return round(numerator / denominator, 4)

    def _display_optional(self, value: object) -> object:
        return "not supplied" if value is None else value


def load_observed_evidence(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Observed evidence JSON must be an object.")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a RepoPilot local benchmark report.")
    parser.add_argument("--benchmark", type=Path, default=Path(__file__).resolve().parents[1] / "benchmark_tasks.json")
    parser.add_argument("--observed-evidence", type=Path, default=None)
    parser.add_argument("--out-dir", type=Path, default=Path("Docs/eval-reports"))
    parser.add_argument("--report-name", default="v1-local-eval-report")
    parser.add_argument("--task-count", type=int, default=None)
    parser.add_argument(
        "--allow-failed-gates",
        action="store_true",
        help="Write the report and exit 0 even when release quality gates are false.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    builder = BenchmarkReportBuilder(benchmark_path=args.benchmark)
    markdown_path, json_path, report = builder.write(
        output_dir=args.out_dir,
        report_name=args.report_name,
        task_count=args.task_count,
        observed_evidence=load_observed_evidence(args.observed_evidence),
    )
    print(f"Wrote {markdown_path}")
    print(f"Wrote {json_path}")
    gates = report.metrics.get("quality_gate_results")
    if isinstance(gates, dict) and not all(bool(value) for value in gates.values()) and not args.allow_failed_gates:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
