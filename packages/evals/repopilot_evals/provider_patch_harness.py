from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from repopilot_contracts import EvalTaskFixture

from .provider_harness import (
    ChatCompletionClient,
    ProviderChatClient,
    default_provider_api_key_env,
)
from .provider_credentials import redact_for_output, resolve_provider_credentials
from .report import BenchmarkReport, BenchmarkReportBuilder


@dataclass(frozen=True)
class ProviderPatchEvalResult:
    markdown_path: Path
    json_path: Path
    observed_evidence_path: Path
    report: BenchmarkReport


class ProviderPatchEvalRunner:
    def __init__(self, *, benchmark_path: Path | None = None, client: ChatCompletionClient | None = None) -> None:
        self.builder = BenchmarkReportBuilder(benchmark_path=benchmark_path)
        self.client = client

    def run(
        self,
        *,
        provider: str,
        model: str,
        output_dir: Path,
        report_name: str,
        task_count: int,
        timeout_seconds: int = 60,
        allow_failed_gates: bool = False,
    ) -> ProviderPatchEvalResult:
        if self.client is None:
            raise ValueError("ProviderPatchEvalRunner requires a chat completion client.")
        benchmark = self.builder.load_benchmark()
        tasks = benchmark["tasks"][:task_count]
        observed_task_results: list[dict[str, object]] = []
        errors: list[dict[str, str]] = []
        latencies: list[int] = []

        for task in tasks:
            started = time.monotonic()
            try:
                provider_payload = self.client.complete_json(
                    model=model,
                    messages=self.messages_for_task(task),
                    timeout_seconds=timeout_seconds,
                )
                observed_task_results.append(self.normalize_provider_patch(task=task, payload=provider_payload))
            except Exception as exc:  # noqa: BLE001 - provider failures should become eval evidence.
                observed_task_results.append(self.empty_failed_patch(task=task))
                errors.append({"task_id": task.id, "error": redact_for_output(exc, limit=500)})
            finally:
                latencies.append(int((time.monotonic() - started) * 1000))

        preliminary_evidence = {"observed_task_results": observed_task_results}
        preliminary_report = self.builder.build(task_count=task_count, observed_evidence=preliminary_evidence)
        metrics = preliminary_report.metrics
        provider_summary = {
            "provider": provider,
            "model": model,
            "task_count": task_count,
            "plan_quality_pass_rate": 0.0,
            "patch_quality_pass_rate": metrics["patch_quality_pass_rate"],
            "context_precision": 0.0,
            "human_edit_distance": metrics["human_edit_distance"],
            "cost_per_run": 0.0,
            "latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0.0,
        }
        observed_evidence = {
            "observed_task_results": observed_task_results,
            "provider_eval_results": [provider_summary],
            "provider_errors": errors,
            "validation_note": (
                "Provider patch eval records model-proposed patch evidence only. "
                "It does not mutate fixture repositories or mark validation passed unless supplied evidence explicitly does so."
            ),
        }

        output_dir.mkdir(parents=True, exist_ok=True)
        observed_evidence_path = output_dir / f"{report_name}.observed-evidence.json"
        observed_evidence_path.write_text(json.dumps(observed_evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        markdown_path, json_path, report = self.builder.write(
            output_dir=output_dir,
            report_name=report_name,
            task_count=task_count,
            observed_evidence=observed_evidence,
        )
        gates = report.metrics.get("quality_gate_results")
        if isinstance(gates, dict) and not all(bool(value) for value in gates.values()) and not allow_failed_gates:
            failed = ", ".join(sorted(name for name, passed in gates.items() if not passed))
            raise RuntimeError(f"Provider patch eval report has failed quality gates: {failed}")
        return ProviderPatchEvalResult(
            markdown_path=markdown_path,
            json_path=json_path,
            observed_evidence_path=observed_evidence_path,
            report=report,
        )

    def messages_for_task(self, task: EvalTaskFixture) -> list[dict[str, str]]:
        fixture_path = self.builder.fixture_verifier.fixture_path(task)
        file_inventory = "\n".join(self.fixture_file_inventory(fixture_path))
        excerpts = "\n\n".join(self.fixture_file_excerpts(fixture_path=fixture_path, task=task))
        return [
            {
                "role": "system",
                "content": (
                    "You are evaluating RepoPilot patch quality. Return only a JSON object with keys: "
                    "changed_files, diff_summary, generated_diff, validation_commands, validation_status, "
                    "security_result, ci_status. Do not include secrets. Do not claim tests passed unless the prompt "
                    "includes explicit validation output proving it."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Task ID: {task.id}\n"
                    f"Issue title: {task.issue_title}\n"
                    f"Issue body: {task.issue_body}\n"
                    "Available repository files:\n"
                    f"{file_inventory}\n\n"
                    "Relevant file excerpts:\n"
                    f"{excerpts}\n\n"
                    "Return the patch evidence you would attempt for this issue. Use repository paths from the "
                    "inventory and a concise unified-diff style generated_diff when possible."
                ),
            },
        ]

    def fixture_file_inventory(self, fixture_path: Path, *, max_files: int = 80) -> list[str]:
        if not fixture_path.is_dir():
            return []
        ignored_parts = {".git", ".pytest_cache", "__pycache__", "node_modules", ".next"}
        paths: list[str] = []
        for path in sorted(fixture_path.rglob("*")):
            if len(paths) >= max_files:
                break
            if path.is_dir() or any(part in ignored_parts for part in path.parts):
                continue
            relative = path.relative_to(fixture_path).as_posix()
            if relative.startswith("."):
                continue
            paths.append(relative)
        return paths

    def fixture_file_excerpts(self, *, fixture_path: Path, task: EvalTaskFixture, max_files: int = 6, max_chars: int = 1200) -> list[str]:
        excerpts: list[str] = []
        candidate_paths = list(dict.fromkeys([*task.expected_changed_files, *task.disallowed_changes]))
        for relative in candidate_paths:
            if relative == "*" or len(excerpts) >= max_files:
                continue
            path = (fixture_path / relative).resolve()
            try:
                path.relative_to(fixture_path.resolve())
            except ValueError:
                continue
            if not path.is_file():
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="replace")[:max_chars]
            except OSError:
                continue
            excerpts.append(f"### {relative}\n{content}")
        return excerpts

    def normalize_provider_patch(self, *, task: EvalTaskFixture, payload: dict[str, Any]) -> dict[str, object]:
        security_result = str(payload.get("security_result") or "unknown")
        if security_result not in {"pass", "block", "escalate", "unknown"}:
            security_result = "unknown"
        validation_status = str(payload.get("validation_status") or "not_run")
        if validation_status not in {"passed", "failed", "blocked", "not_run", "unknown"}:
            validation_status = "unknown"
        return {
            "task_id": task.id,
            "changed_files": self._string_list(payload.get("changed_files")),
            "diff_summary": str(payload.get("diff_summary") or ""),
            "generated_diff": str(payload.get("generated_diff") or ""),
            "validation_commands": self._string_list(payload.get("validation_commands")),
            "validation_status": validation_status,
            "security_result": security_result,
            "ci_status": str(payload.get("ci_status")) if payload.get("ci_status") is not None else None,
        }

    def empty_failed_patch(self, *, task: EvalTaskFixture) -> dict[str, object]:
        return {
            "task_id": task.id,
            "changed_files": [],
            "diff_summary": "",
            "generated_diff": "",
            "validation_commands": [],
            "validation_status": "failed",
            "security_result": "unknown",
            "ci_status": None,
        }

    def _string_list(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if item]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run provider-backed RepoPilot patch-attempt evals.")
    parser.add_argument("--provider", default="openrouter")
    parser.add_argument("--model", required=True)
    parser.add_argument("--api-key-env")
    parser.add_argument("--base-url")
    parser.add_argument("--no-runtime-secret-store", action="store_true")
    parser.add_argument("--benchmark", type=Path, default=Path(__file__).resolve().parents[1] / "benchmark_tasks.json")
    parser.add_argument("--out-dir", type=Path, default=Path("Docs/eval-reports"))
    parser.add_argument("--report-name", default="v1-provider-patch")
    parser.add_argument("--task-count", type=int, default=5)
    parser.add_argument("--timeout-seconds", type=int, default=60)
    parser.add_argument("--allow-failed-gates", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    api_key_env = args.api_key_env or default_provider_api_key_env(args.provider)
    credentials = resolve_provider_credentials(
        provider=args.provider,
        api_key_env=api_key_env,
        base_url=args.base_url,
        allow_runtime_store=not args.no_runtime_secret_store,
    )
    if not credentials.api_key:
        print(
            "Missing provider API key. "
            f"Set {api_key_env} in the environment or save MODEL_API_KEY in RepoPilot's local runtime secret store."
        )
        return 2
    runner = ProviderPatchEvalRunner(
        benchmark_path=args.benchmark,
        client=ProviderChatClient(
            base_url=credentials.base_url,
            api_key=credentials.api_key,
            provider=args.provider,
        ),
    )
    try:
        result = runner.run(
            provider=args.provider,
            model=args.model,
            output_dir=args.out_dir,
            report_name=args.report_name,
            task_count=args.task_count,
            timeout_seconds=args.timeout_seconds,
            allow_failed_gates=args.allow_failed_gates,
        )
    except RuntimeError as exc:
        print(redact_for_output(exc))
        return 2
    print(f"Wrote {result.markdown_path}")
    print(f"Wrote {result.json_path}")
    print(f"Wrote {result.observed_evidence_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
