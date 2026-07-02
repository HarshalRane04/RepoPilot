from __future__ import annotations

import argparse
import json
import math
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from repopilot_contracts import EvalTaskFixture

from .provider_credentials import redact_for_output, resolve_provider_credentials
from .provider_harness import default_provider_api_key_env
from .report import BenchmarkReport, BenchmarkReportBuilder


class EmbeddingClient(Protocol):
    def embed(self, *, model: str, texts: list[str], timeout_seconds: int) -> list[list[float]]:
        raise NotImplementedError


@dataclass(frozen=True)
class ProviderRetrievalEvalResult:
    markdown_path: Path
    json_path: Path
    observed_evidence_path: Path
    report: BenchmarkReport


@dataclass(frozen=True)
class RetrievalCandidate:
    path: str
    text: str


class ProviderEmbeddingClient:
    def __init__(self, *, base_url: str, api_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def embed(self, *, model: str, texts: list[str], timeout_seconds: int) -> list[list[float]]:
        request = urllib.request.Request(
            url=f"{self.base_url}/embeddings",
            data=json.dumps({"model": model, "input": texts}).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"embedding provider returned HTTP {exc.code}: {redact_for_output(body, limit=500)}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"embedding provider request failed: {exc.reason}") from exc
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            raise RuntimeError("embedding provider response did not contain a data list.")
        embeddings: list[list[float]] = []
        for item in data[: len(texts)]:
            value = item.get("embedding") if isinstance(item, dict) else None
            if not isinstance(value, list):
                embeddings.append([])
                continue
            embeddings.append([float(component) for component in value if isinstance(component, (int, float))])
        if len(embeddings) != len(texts):
            raise RuntimeError("embedding provider returned an unexpected number of embeddings.")
        return embeddings


class ProviderRetrievalEvalRunner:
    def __init__(self, *, benchmark_path: Path | None = None, client: EmbeddingClient | None = None) -> None:
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
        top_k: int = 5,
        allow_failed_gates: bool = False,
    ) -> ProviderRetrievalEvalResult:
        if self.client is None:
            raise ValueError("ProviderRetrievalEvalRunner requires an embedding client.")
        benchmark = self.builder.load_benchmark()
        tasks = benchmark["tasks"][:task_count]
        observed_plan_results: list[dict[str, object]] = []
        retrieval_results: list[dict[str, object]] = []
        errors: list[dict[str, str]] = []
        latencies: list[int] = []

        for task in tasks:
            started = time.monotonic()
            try:
                result = self.retrieve_for_task(task=task, model=model, timeout_seconds=timeout_seconds, top_k=top_k)
                retrieval_results.append(result)
                observed_plan_results.append(self.plan_control_for_task(task=task, citations=self._string_list(result.get("citations"))))
            except Exception as exc:  # noqa: BLE001 - provider failures should become eval evidence.
                retrieval_results.append(self.empty_failed_retrieval(task=task))
                observed_plan_results.append(self.plan_control_for_task(task=task, citations=[]))
                errors.append({"task_id": task.id, "error": redact_for_output(exc, limit=500)})
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
            "retrieval_results": retrieval_results,
            "provider_eval_results": [provider_summary],
            "provider_errors": errors,
            "validation_note": (
                "Provider retrieval eval measures retrieved context citations. "
                "Non-retrieval observed plan fields are benchmark controls so context_precision remains the primary signal."
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
            raise RuntimeError(f"Provider retrieval eval report has failed quality gates: {failed}")
        return ProviderRetrievalEvalResult(
            markdown_path=markdown_path,
            json_path=json_path,
            observed_evidence_path=observed_evidence_path,
            report=report,
        )

    def retrieve_for_task(self, *, task: EvalTaskFixture, model: str, timeout_seconds: int, top_k: int) -> dict[str, object]:
        fixture_path = self.builder.fixture_verifier.fixture_path(task)
        candidates = self.fixture_candidates(fixture_path)
        if not candidates:
            return self.empty_failed_retrieval(task=task)
        query = self.query_for_task(task)
        texts = [query, *[candidate.text for candidate in candidates]]
        embeddings = self.client.embed(model=model, texts=texts, timeout_seconds=timeout_seconds)
        if len(embeddings) != len(texts):
            raise RuntimeError("Embedding client returned an unexpected number of vectors.")
        query_embedding = embeddings[0]
        scored = [
            {
                "path": candidate.path,
                "score": round(_cosine_similarity(query_embedding, embedding), 6),
            }
            for candidate, embedding in zip(candidates, embeddings[1:], strict=False)
        ]
        ranked = sorted(scored, key=lambda item: float(item["score"]), reverse=True)[:top_k]
        citations = [str(item["path"]) for item in ranked]
        expected = {path for path in task.expected_changed_files if path != "*"}
        relevant = [path for path in citations if path in expected]
        precision = round(len(relevant) / len(citations), 4) if citations else 0.0
        return {
            "task_id": task.id,
            "citations": citations,
            "expected_changed_files": sorted(expected),
            "relevant_citations": relevant,
            "precision": precision,
            "scores": ranked,
        }

    def fixture_candidates(self, fixture_path: Path, *, max_files: int = 120, max_chars: int = 1800) -> list[RetrievalCandidate]:
        if not fixture_path.is_dir():
            return []
        ignored_parts = {".git", ".pytest_cache", "__pycache__", "node_modules", ".next"}
        candidates: list[RetrievalCandidate] = []
        for path in sorted(fixture_path.rglob("*")):
            if len(candidates) >= max_files:
                break
            if path.is_dir() or any(part in ignored_parts for part in path.parts):
                continue
            relative = path.relative_to(fixture_path).as_posix()
            if relative.startswith("."):
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="replace")[:max_chars]
            except OSError:
                continue
            candidates.append(RetrievalCandidate(path=relative, text=f"### {relative}\n{content}"))
        return candidates

    def query_for_task(self, task: EvalTaskFixture) -> str:
        return "\n".join(
            [
                task.issue_title,
                task.issue_body,
                "Acceptance criteria:",
                *task.acceptance_criteria,
                "Expected validation:",
                *task.expected_tests,
            ]
        )

    def plan_control_for_task(self, *, task: EvalTaskFixture, citations: list[str]) -> dict[str, object]:
        return {
            "task_id": task.id,
            "summary": task.expected_diff_summary,
            "files_to_modify": list(task.expected_changed_files),
            "tests_to_add": list(task.expected_tests),
            "commands_to_run": list(task.expected_tests),
            "context_citations": citations,
            "requires_human_approval": True,
        }

    def empty_failed_retrieval(self, *, task: EvalTaskFixture) -> dict[str, object]:
        return {
            "task_id": task.id,
            "citations": [],
            "expected_changed_files": [path for path in task.expected_changed_files if path != "*"],
            "relevant_citations": [],
            "precision": 0.0,
            "scores": [],
        }

    def _string_list(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if item]


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    size = min(len(left), len(right))
    left_slice = left[:size]
    right_slice = right[:size]
    left_norm = math.sqrt(sum(value * value for value in left_slice))
    right_norm = math.sqrt(sum(value * value for value in right_slice))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    dot = sum(left_value * right_value for left_value, right_value in zip(left_slice, right_slice, strict=False))
    return dot / (left_norm * right_norm)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run provider-backed RepoPilot retrieval-quality evals.")
    parser.add_argument("--provider", default="openrouter")
    parser.add_argument("--model", required=True)
    parser.add_argument("--api-key-env")
    parser.add_argument("--base-url")
    parser.add_argument("--no-runtime-secret-store", action="store_true")
    parser.add_argument("--benchmark", type=Path, default=Path(__file__).resolve().parents[1] / "benchmark_tasks.json")
    parser.add_argument("--out-dir", type=Path, default=Path("Docs/eval-reports"))
    parser.add_argument("--report-name", default="v1-provider-retrieval")
    parser.add_argument("--task-count", type=int, default=5)
    parser.add_argument("--top-k", type=int, default=5)
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
            "Missing provider API key. Set the provider-specific environment variable or save MODEL_API_KEY "
            "in RepoPilot's local runtime secret store."
        )
        return 2
    runner = ProviderRetrievalEvalRunner(
        benchmark_path=args.benchmark,
        client=ProviderEmbeddingClient(base_url=credentials.base_url, api_key=credentials.api_key),
    )
    try:
        runner.run(
            provider=args.provider,
            model=args.model,
            output_dir=args.out_dir,
            report_name=args.report_name,
            task_count=args.task_count,
            timeout_seconds=args.timeout_seconds,
            top_k=args.top_k,
            allow_failed_gates=args.allow_failed_gates,
        )
    except RuntimeError:
        print("Provider retrieval eval failed; console output was redacted to avoid leaking provider response data.")
        return 2
    print("Provider retrieval eval completed; redacted artifacts were written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
