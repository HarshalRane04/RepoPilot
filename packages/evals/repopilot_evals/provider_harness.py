from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from repopilot_contracts import EvalTaskFixture

from .report import BenchmarkReport, BenchmarkReportBuilder


class ChatCompletionClient(Protocol):
    def complete_json(self, *, model: str, messages: list[dict[str, str]], timeout_seconds: int) -> dict[str, Any]:
        ...


class OpenAICompatibleChatClient:
    def __init__(self, *, base_url: str, api_key: str, provider: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.provider = provider

    def complete_json(self, *, model: str, messages: list[dict[str, str]], timeout_seconds: int) -> dict[str, Any]:
        request = urllib.request.Request(
            url=f"{self.base_url}/chat/completions",
            data=json.dumps(
                {
                    "model": model,
                    "messages": messages,
                    "temperature": 0.1,
                    "response_format": {"type": "json_object"},
                }
            ).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "X-Title": "RepoPilot Eval Harness",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{self.provider} returned HTTP {exc.code}: {body[:500]}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"{self.provider} request failed: {exc.reason}") from exc
        content = payload.get("choices", [{}])[0].get("message", {}).get("content")
        if not isinstance(content, str):
            raise RuntimeError(f"{self.provider} response did not include a message content string.")
        return parse_json_object(content)


@dataclass(frozen=True)
class ProviderPlanningEvalResult:
    markdown_path: Path
    json_path: Path
    observed_evidence_path: Path
    report: BenchmarkReport


class ProviderPlanningEvalRunner:
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
    ) -> ProviderPlanningEvalResult:
        if self.client is None:
            raise ValueError("ProviderPlanningEvalRunner requires a chat completion client.")
        benchmark = self.builder.load_benchmark()
        tasks = benchmark["tasks"][:task_count]
        observed_plan_results: list[dict[str, object]] = []
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
                observed_plan_results.append(self.normalize_provider_plan(task=task, payload=provider_payload))
            except Exception as exc:  # noqa: BLE001 - provider failures should become eval evidence.
                observed_plan_results.append(self.empty_failed_plan(task=task))
                errors.append({"task_id": task.id, "error": str(exc)[:500]})
            finally:
                latencies.append(int((time.monotonic() - started) * 1000))

        preliminary_evidence = {"observed_plan_results": observed_plan_results}
        preliminary_report = self.builder.build(task_count=task_count, observed_evidence=preliminary_evidence)
        metrics = preliminary_report.metrics
        provider_summary = {
            "provider": provider,
            "model": model,
            "task_count": task_count,
            "plan_quality_pass_rate": metrics["plan_quality_pass_rate"],
            "patch_quality_pass_rate": 0.0,
            "context_precision": metrics["context_precision"],
            "human_edit_distance": None,
            "cost_per_run": 0.0,
            "latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0.0,
        }
        observed_evidence = {
            "observed_plan_results": observed_plan_results,
            "provider_eval_results": [provider_summary],
            "provider_errors": errors,
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
            raise RuntimeError(f"Provider planning eval report has failed quality gates: {failed}")
        return ProviderPlanningEvalResult(
            markdown_path=markdown_path,
            json_path=json_path,
            observed_evidence_path=observed_evidence_path,
            report=report,
        )

    def messages_for_task(self, task: EvalTaskFixture) -> list[dict[str, str]]:
        fixture_path = self.builder.fixture_verifier.fixture_path(task)
        file_inventory = "\n".join(self.fixture_file_inventory(fixture_path))
        return [
            {
                "role": "system",
                "content": (
                    "You are evaluating RepoPilot planning quality. Return only a JSON object with keys: "
                    "summary, files_to_modify, tests_to_add, commands_to_run, context_citations, "
                    "requires_human_approval. Do not write code. Do not include secrets."
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
                    "Return a concise implementation plan. Context citations must use repository paths from "
                    "the inventory, optionally with a line suffix like path:1-20."
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

    def normalize_provider_plan(self, *, task: EvalTaskFixture, payload: dict[str, Any]) -> dict[str, object]:
        return {
            "task_id": task.id,
            "summary": str(payload.get("summary") or ""),
            "files_to_modify": self._string_list(payload.get("files_to_modify")),
            "tests_to_add": self._string_list(payload.get("tests_to_add")),
            "commands_to_run": self._string_list(payload.get("commands_to_run")),
            "context_citations": self._string_list(payload.get("context_citations")),
            "requires_human_approval": bool(payload.get("requires_human_approval", True)),
        }

    def empty_failed_plan(self, *, task: EvalTaskFixture) -> dict[str, object]:
        return {
            "task_id": task.id,
            "summary": "",
            "files_to_modify": [],
            "tests_to_add": [],
            "commands_to_run": [],
            "context_citations": [],
            "requires_human_approval": True,
        }

    def _string_list(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if item]


def parse_json_object(content: str) -> dict[str, Any]:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped, flags=re.IGNORECASE).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    payload = json.loads(stripped)
    if not isinstance(payload, dict):
        raise ValueError("Provider content must parse to a JSON object.")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run provider-backed RepoPilot planning evals.")
    parser.add_argument("--provider", default="openrouter")
    parser.add_argument("--model", required=True)
    parser.add_argument("--api-key-env", default="OPENROUTER_API_KEY")
    parser.add_argument("--base-url", default="https://openrouter.ai/api/v1")
    parser.add_argument("--benchmark", type=Path, default=Path(__file__).resolve().parents[1] / "benchmark_tasks.json")
    parser.add_argument("--out-dir", type=Path, default=Path("Docs/eval-reports"))
    parser.add_argument("--report-name", default="v1-provider-planning")
    parser.add_argument("--task-count", type=int, default=5)
    parser.add_argument("--timeout-seconds", type=int, default=60)
    parser.add_argument("--allow-failed-gates", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    api_key = os.environ.get(args.api_key_env)
    if not api_key:
        print(f"Missing provider API key. Set {args.api_key_env} in the environment.")
        return 2
    runner = ProviderPlanningEvalRunner(
        benchmark_path=args.benchmark,
        client=OpenAICompatibleChatClient(base_url=args.base_url, api_key=api_key, provider=args.provider),
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
        print(str(exc))
        return 2
    print(f"Wrote {result.markdown_path}")
    print(f"Wrote {result.json_path}")
    print(f"Wrote {result.observed_evidence_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
