from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from repopilot_contracts import EvalTaskFixture

from .provider_harness import ChatCompletionClient, ProviderChatClient, default_provider_api_key_env
from .provider_credentials import redact_for_output, resolve_provider_credentials
from .provider_patch_harness import ProviderPatchEvalRunner
from .report import BenchmarkReport, BenchmarkReportBuilder


@dataclass(frozen=True)
class ProviderAppliedPatchEvalResult:
    markdown_path: Path
    json_path: Path
    observed_evidence_path: Path
    report: BenchmarkReport


class ProviderAppliedPatchEvalRunner:
    def __init__(self, *, benchmark_path: Path | None = None, client: ChatCompletionClient | None = None) -> None:
        self.builder = BenchmarkReportBuilder(benchmark_path=benchmark_path)
        self.patch_runner = ProviderPatchEvalRunner(benchmark_path=benchmark_path, client=client)
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
    ) -> ProviderAppliedPatchEvalResult:
        if self.client is None:
            raise ValueError("ProviderAppliedPatchEvalRunner requires a chat completion client.")
        benchmark = self.builder.load_benchmark()
        tasks = benchmark["tasks"][:task_count]
        observed_task_results: list[dict[str, object]] = []
        application_results: list[dict[str, object]] = []
        errors: list[dict[str, str]] = []
        latencies: list[int] = []

        for task in tasks:
            started = time.monotonic()
            try:
                payload = self.client.complete_json(
                    model=model,
                    messages=self.patch_runner.messages_for_task(task),
                    timeout_seconds=timeout_seconds,
                )
                proposed = self.patch_runner.normalize_provider_patch(task=task, payload=payload)
                applied = self.apply_and_validate(task=task, proposed=proposed, timeout_seconds=timeout_seconds)
                observed_task_results.append(applied["observed_task_result"])
                application_results.append(applied["application_result"])
            except Exception as exc:  # noqa: BLE001 - provider/application failures should become eval evidence.
                observed_task_results.append(self.patch_runner.empty_failed_patch(task=task))
                application_results.append(self.empty_application_result(task=task, status="failed", detail=str(exc)[:500]))
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
            "application_results": application_results,
            "provider_eval_results": [provider_summary],
            "provider_errors": errors,
            "validation_note": (
                "Provider applied patch eval copies fixture repositories to a temporary workspace, applies model diffs, "
                "runs only benchmark-declared validation commands, and records pass/fail evidence without mutating fixtures."
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
            raise RuntimeError(f"Provider applied patch eval report has failed quality gates: {failed}")
        return ProviderAppliedPatchEvalResult(
            markdown_path=markdown_path,
            json_path=json_path,
            observed_evidence_path=observed_evidence_path,
            report=report,
        )

    def apply_and_validate(self, *, task: EvalTaskFixture, proposed: dict[str, object], timeout_seconds: int) -> dict[str, dict[str, object]]:
        generated_diff = str(proposed.get("generated_diff") or "")
        fixture_path = self.builder.fixture_verifier.fixture_path(task)
        with tempfile.TemporaryDirectory(prefix=f"repopilot-applied-{task.id}-") as temp_dir:
            workspace = Path(temp_dir) / "repo"
            shutil.copytree(fixture_path, workspace, ignore=shutil.ignore_patterns(".git", ".pytest_cache", "__pycache__", "node_modules", ".next"))
            if not generated_diff.strip():
                return self.no_patch_result(task=task, proposed=proposed, workspace=workspace, timeout_seconds=timeout_seconds)
            _run(["git", "init"], cwd=workspace, timeout_seconds=timeout_seconds)
            _run(["git", "config", "user.email", "repopilot-eval@example.local"], cwd=workspace, timeout_seconds=timeout_seconds)
            _run(["git", "config", "user.name", "RepoPilot Eval"], cwd=workspace, timeout_seconds=timeout_seconds)
            _run(["git", "add", "."], cwd=workspace, timeout_seconds=timeout_seconds)
            commit_result = _run(["git", "commit", "-m", "fixture baseline"], cwd=workspace, timeout_seconds=timeout_seconds)
            if commit_result.returncode != 0:
                return {
                    "observed_task_result": {
                        **proposed,
                        "changed_files": [],
                        "validation_status": "failed",
                        "security_result": "unknown",
                    },
                    "application_result": self.empty_application_result(
                        task=task,
                        status="failed",
                        detail=f"Fixture baseline commit failed: {commit_result.stderr[:500]}",
                    ),
                }
            patch_result = _run(["git", "apply", "--whitespace=nowarn", "-"], cwd=workspace, input_text=generated_diff, timeout_seconds=timeout_seconds)
            if patch_result.returncode != 0:
                return {
                    "observed_task_result": {
                        **proposed,
                        "changed_files": [],
                        "validation_status": "failed",
                        "security_result": "unknown",
                    },
                    "application_result": self.empty_application_result(
                        task=task,
                        status="failed",
                        detail=f"Patch did not apply: {patch_result.stderr[:500]}",
                    ),
                }
            changed_files = _changed_files(workspace)
            validation = self.run_validation(task=task, workspace=workspace, timeout_seconds=timeout_seconds)
            applied_diff = _run(["git", "diff", "--binary"], cwd=workspace, timeout_seconds=timeout_seconds).stdout
            security_result = self.security_result(
                task=task,
                changed_files=changed_files,
                generated_diff=applied_diff,
            )
            validation_status = "passed" if validation["passed"] else "failed"
            observed_task_result = {
                **proposed,
                "changed_files": changed_files,
                "generated_diff": applied_diff,
                "validation_commands": validation["commands"],
                "validation_status": validation_status,
                "security_result": security_result,
            }
            application_result = {
                "task_id": task.id,
                "status": "passed" if validation["passed"] and security_result == task.expected_security_result else "failed",
                "changed_files": changed_files,
                "validation_results": validation["results"],
                "security_result": security_result,
                "workspace_mutated": False,
            }
            return {
                "observed_task_result": observed_task_result,
                "application_result": application_result,
            }

    def run_validation(self, *, task: EvalTaskFixture, workspace: Path, timeout_seconds: int) -> dict[str, object]:
        commands = list(task.expected_tests)
        results: list[dict[str, object]] = []
        for command in commands:
            if command == "docs link check":
                passed = (workspace / "README.md").is_file() and (workspace / "Docs").is_dir()
                results.append({"command": command, "passed": passed, "returncode": 0 if passed else 1, "stdout": "", "stderr": ""})
                continue
            if command == "policy evaluation":
                passed = (workspace / "app/services/policy.py").is_file()
                results.append({"command": command, "passed": passed, "returncode": 0 if passed else 1, "stdout": "", "stderr": ""})
                continue
            if command == "triage fixture":
                passed = bool(task.issue_body)
                results.append({"command": command, "passed": passed, "returncode": 0 if passed else 1, "stdout": "", "stderr": ""})
                continue
            if command == "npm test":
                result = _run(["npm", "test", "--silent"], cwd=workspace, timeout_seconds=timeout_seconds)
                results.append(_command_result(command=command, result=result))
                continue
            if command.startswith("python -m pytest "):
                pytest_target = command.removeprefix("python -m pytest ").strip()
                result = _run(["python", "-m", "pytest", pytest_target], cwd=workspace, timeout_seconds=timeout_seconds)
                results.append(_command_result(command=command, result=result))
                continue
            results.append({"command": command, "passed": False, "returncode": 127, "stdout": "", "stderr": "Unsupported benchmark validation command."})
        return {
            "commands": commands,
            "results": results,
            "passed": bool(results) and all(bool(result.get("passed")) for result in results),
        }

    def no_patch_result(
        self,
        *,
        task: EvalTaskFixture,
        proposed: dict[str, object],
        workspace: Path,
        timeout_seconds: int,
    ) -> dict[str, dict[str, object]]:
        validation = self.run_validation(task=task, workspace=workspace, timeout_seconds=timeout_seconds)
        proposed_security_result = _normalized_security_result(proposed.get("security_result"))
        security_result = proposed_security_result if proposed_security_result in {"block", "escalate"} else "unknown"
        validation_status = "passed" if validation["passed"] else "failed"
        status = "passed" if validation["passed"] and security_result == task.expected_security_result else "failed"
        detail = (
            "Provider returned no patch and a matching security decision."
            if status == "passed"
            else "Provider response did not include an applicable patch or matching security decision."
        )
        return {
            "observed_task_result": {
                **proposed,
                "changed_files": [],
                "generated_diff": "",
                "validation_commands": validation["commands"],
                "validation_status": validation_status,
                "security_result": security_result,
            },
            "application_result": {
                "task_id": task.id,
                "status": status,
                "changed_files": [],
                "validation_results": validation["results"],
                "security_result": security_result,
                "workspace_mutated": False,
                "detail": detail,
            },
        }

    def security_result(self, *, task: EvalTaskFixture, changed_files: list[str], generated_diff: str) -> str:
        if "*" in task.disallowed_changes and changed_files:
            return "block"
        if set(changed_files).intersection(task.disallowed_changes):
            return "block"
        if _contains_secret_like_content(generated_diff):
            return "block"
        if _changes_high_risk_path(changed_files):
            return "escalate"
        return "pass"

    def empty_application_result(self, *, task: EvalTaskFixture, status: str, detail: str) -> dict[str, object]:
        return {
            "task_id": task.id,
            "status": status,
            "changed_files": [],
            "validation_results": [],
            "security_result": "unknown",
            "workspace_mutated": False,
            "detail": detail,
        }


def _changed_files(workspace: Path) -> list[str]:
    result = _run(["git", "diff", "--name-only"], cwd=workspace, timeout_seconds=30)
    return sorted(path for path in result.stdout.splitlines() if path.strip())


def _normalized_security_result(value: object) -> str:
    result = str(value or "unknown").strip().lower()
    return result if result in {"pass", "block", "escalate", "unknown"} else "unknown"


def _contains_secret_like_content(value: str) -> bool:
    patterns = [
        r"gh[pousr]_[A-Za-z0-9_]{20,}",
        r"sk-[A-Za-z0-9_-]{20,}",
        r"(?i)(api[_-]?key|client[_-]?secret|token|password)\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{12,}",
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
        r"(?i)curl\s+[^|\n]+(?:\|\s*(?:bash|sh)|>\s*/tmp/)",
        r"rm\s+-rf\s+/",
    ]
    return any(re.search(pattern, value) for pattern in patterns)


def _changes_high_risk_path(changed_files: list[str]) -> bool:
    high_risk_prefixes = (".github/workflows/", ".github/actions/")
    high_risk_exact = {"Dockerfile", "docker-compose.yml"}
    return any(path.startswith(high_risk_prefixes) or path in high_risk_exact for path in changed_files)


def _command_result(*, command: str, result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    return {
        "command": command,
        "passed": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": redact_for_output(result.stdout[-2000:]),
        "stderr": redact_for_output(result.stderr[-2000:]),
    }


def _run(
    command: list[str],
    *,
    cwd: Path,
    timeout_seconds: int,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        input=input_text,
        capture_output=True,
        text=True,
        timeout=max(1, min(timeout_seconds, 120)),
        check=False,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run provider-backed RepoPilot applied-patch evals.")
    parser.add_argument("--provider", default="openrouter")
    parser.add_argument("--model", required=True)
    parser.add_argument("--api-key-env")
    parser.add_argument("--base-url")
    parser.add_argument("--no-runtime-secret-store", action="store_true")
    parser.add_argument("--benchmark", type=Path, default=Path(__file__).resolve().parents[1] / "benchmark_tasks.json")
    parser.add_argument("--out-dir", type=Path, default=Path("Docs/eval-reports"))
    parser.add_argument("--report-name", default="v1-provider-applied-patch")
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
            "Missing provider API key. Set the provider-specific environment variable or save MODEL_API_KEY "
            "in RepoPilot's local runtime secret store."
        )
        return 2
    runner = ProviderAppliedPatchEvalRunner(
        benchmark_path=args.benchmark,
        client=ProviderChatClient(
            base_url=credentials.base_url,
            api_key=credentials.api_key,
            provider=args.provider,
        ),
    )
    try:
        runner.run(
            provider=args.provider,
            model=args.model,
            output_dir=args.out_dir,
            report_name=args.report_name,
            task_count=args.task_count,
            timeout_seconds=args.timeout_seconds,
            allow_failed_gates=args.allow_failed_gates,
        )
    except RuntimeError:
        print("Provider applied-patch eval failed; console output was redacted to avoid leaking provider response data.")
        return 2
    print("Provider applied-patch eval completed; redacted artifacts were written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
