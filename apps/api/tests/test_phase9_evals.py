from __future__ import annotations

import asyncio
import json
import subprocess
import sys

from app.db.models import EvalRun
from app.services.eval_runner import EvalRunner
from cryptography.fernet import Fernet
from repopilot_evals import (
    BenchmarkReportBuilder,
    FixtureVerifier,
    PatchQualityEvidence,
    PatchQualityScorer,
    PlanQualityEvidence,
    PlanQualityScorer,
    ProviderComparisonScorer,
    ProviderEvalEvidence,
    ProviderChatClient,
    ProviderPatchEvalRunner,
    ProviderPlanningEvalRunner,
    resolve_provider_credentials,
)
from repopilot_evals.provider_harness import default_provider_api_key_env, default_provider_base_url


class ScalarResult:
    def __init__(self, items: list[object]) -> None:
        self.items = items

    def scalars(self):
        return self

    def all(self) -> list[object]:
        return self.items


class FakeDb:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.commits = 0

    async def scalar(self, _statement):
        return 0

    async def execute(self, _statement):
        return ScalarResult([])

    def add(self, item: object) -> None:
        self.added.append(item)

    async def flush(self) -> None:
        for item in self.added:
            if isinstance(item, EvalRun) and item.id is None:
                from uuid import uuid4

                item.id = uuid4()

    async def commit(self) -> None:
        self.commits += 1

    async def refresh(self, _item: object) -> None:
        return None


def test_eval_runner_loads_fixture_dataset_with_required_coverage() -> None:
    benchmark = EvalRunner().load_benchmark()
    tasks = benchmark["tasks"]
    categories = {task.category for task in tasks}

    assert len(tasks) >= 20
    assert {"docs", "tests", "bugfix", "small_feature", "refactor", "security"}.issubset(categories)
    assert sum(1 for task in tasks if task.category == "security") >= 5


def test_eval_runner_uses_evals_package_fixture_verifier() -> None:
    runner = EvalRunner()
    benchmark = runner.load_benchmark()
    verifier = FixtureVerifier(fixture_root=runner.benchmark_path.parent)

    summary = verifier.file_check_summary(benchmark["tasks"])

    assert isinstance(runner.fixture_verifier, FixtureVerifier)
    assert summary.required > 0
    assert summary.present == summary.required
    assert verifier.repository_is_executable(runner.benchmark_path.parent / "fixtures/python-service") is True


def test_eval_runner_returns_per_task_outcomes_and_quality_gates() -> None:
    benchmark = EvalRunner().load_benchmark()
    outcomes = [EvalRunner().evaluate_fixture(task) for task in benchmark["tasks"]]
    metrics = asyncio.run(EvalRunner().metrics(FakeDb(), task_count=len(outcomes), outcomes=outcomes, benchmark=benchmark))

    assert metrics["benchmark_task_count"] >= 20
    assert metrics["task_pass_rate"] == 1.0
    assert metrics["fixture_repository_count"] == 2
    assert metrics["fixture_repository_pass_rate"] == 1.0
    assert metrics["fixture_file_coverage_rate"] == 1.0
    assert metrics["patch_quality_observed_count"] == 0
    assert metrics["patch_quality_pass_rate"] == 0.0
    assert metrics["human_edit_distance"] is None
    assert metrics["provider_comparison_count"] == 0
    assert metrics["best_provider_by_quality"] is None
    assert metrics["plan_quality_observed_count"] == 0
    assert metrics["plan_quality_pass_rate"] == 0.0
    assert metrics["context_precision"] == 0.0
    assert metrics["ci_total_prs"] == 0
    assert metrics["ci_pass_after_revision_rate"] == 0.0
    assert len(metrics["task_outcomes"]) == metrics["benchmark_task_count"]
    assert metrics["quality_gate_results"]["minimum_fixture_count_for_v1"] is True
    assert metrics["quality_gate_results"]["security_block_tasks_required"] is True
    assert metrics["quality_gate_results"]["executable_fixture_repositories_required"] is True
    assert metrics["quality_gate_results"]["fixture_file_coverage_required"] is True
    assert metrics["quality_gate_results"]["plan_quality_observations_required"] is False
    assert metrics["quality_gate_results"]["plan_quality_pass_rate_required"] is False
    assert metrics["quality_gate_results"]["context_precision_required"] is False
    assert metrics["quality_gate_results"]["patch_quality_observations_required"] is False
    assert metrics["quality_gate_results"]["patch_quality_pass_rate_required"] is False
    assert metrics["quality_gate_results"]["human_edit_distance_required"] is False
    assert metrics["quality_gate_results"]["provider_comparisons_required"] is False


def test_plan_quality_scorer_grades_plan_and_context_precision() -> None:
    benchmark = EvalRunner().load_benchmark()
    task = next(task for task in benchmark["tasks"] if task.id == "bugfix-001")
    scorer = PlanQualityScorer()

    passed = scorer.score(
        task,
        PlanQualityEvidence(
            task_id=task.id,
            summary="Rename response field and add regression coverage for open_issue_count.",
            files_to_modify=["app/api/routes/repositories.py"],
            tests_to_add=["tests/test_repositories.py"],
            commands_to_run=["python -m pytest tests/test_repositories.py"],
            context_citations=["app/api/routes/repositories.py:1-40", "tests/test_repositories.py:1-25"],
            requires_human_approval=True,
        ),
    )
    failed = scorer.score(
        task,
        PlanQualityEvidence(
            task_id=task.id,
            summary="Change database models.",
            files_to_modify=["app/db/models.py"],
            tests_to_add=[],
            commands_to_run=[],
            context_citations=["app/db/models.py:1-20"],
            requires_human_approval=False,
        ),
    )

    assert passed.status == "passed"
    assert passed.score == 1.0
    assert passed.context_precision == 1.0
    assert failed.status == "failed"
    assert failed.context_precision == 0.0
    assert "Observed plan does not require human approval." in failed.failure_reasons
    assert "Observed plan targets disallowed files: app/db/models.py." in failed.failure_reasons


def test_patch_quality_scorer_grades_observed_patch_evidence() -> None:
    benchmark = EvalRunner().load_benchmark()
    task = next(task for task in benchmark["tasks"] if task.id == "bugfix-001")
    scorer = PatchQualityScorer()

    passed = scorer.score(
        task,
        PatchQualityEvidence(
            task_id=task.id,
            changed_files=["app/api/routes/repositories.py", "tests/test_repositories.py"],
            diff_summary="Rename response field and add regression coverage for open_issue_count.",
            generated_diff="- issue_count\n+ open_issue_count\n",
            reference_diff="- issue_count\n+ open_issue_count\n",
            validation_commands=["python -m pytest tests/test_repositories.py"],
            validation_status="passed",
            security_result="pass",
        ),
    )
    failed = scorer.score(
        task,
        PatchQualityEvidence(
            task_id=task.id,
            changed_files=["app/db/models.py"],
            diff_summary="Touched database models.",
            human_edit_distance=0.75,
            validation_commands=[],
            validation_status="failed",
            security_result="pass",
        ),
    )

    assert passed.status == "passed"
    assert passed.score == 1.0
    assert passed.human_edit_distance == 0.0
    assert failed.status == "failed"
    assert failed.human_edit_distance == 0.75
    assert "Observed disallowed changes: app/db/models.py." in failed.failure_reasons
    assert any(reason.startswith("Missing expected changed files") for reason in failed.failure_reasons)


def test_patch_quality_scorer_computes_normalized_human_edit_distance() -> None:
    scorer = PatchQualityScorer()

    assert scorer.normalized_edit_distance("", "") == 0.0
    assert scorer.normalized_edit_distance("", "abc") == 1.0
    assert scorer.normalized_edit_distance("kitten", "sitting") == 0.4286


def test_provider_comparison_scorer_ranks_quality_before_cost() -> None:
    results = ProviderComparisonScorer().score_all(
        [
            ProviderEvalEvidence(
                provider="cheap",
                model="small",
                task_count=20,
                plan_quality_pass_rate=0.6,
                patch_quality_pass_rate=0.6,
                context_precision=0.6,
                human_edit_distance=0.3,
                cost_per_run=0.01,
                latency_ms=500,
            ),
            ProviderEvalEvidence(
                provider="openrouter",
                model="google/gemma-4-31b-it:free",
                task_count=20,
                plan_quality_pass_rate=0.9,
                patch_quality_pass_rate=0.85,
                context_precision=0.8,
                human_edit_distance=0.1,
                cost_per_run=0.05,
                latency_ms=900,
            ),
        ]
    )

    assert results[0].provider == "openrouter"
    assert results[0].quality_score > results[1].quality_score
    assert results[0].human_edit_distance == 0.1


def test_eval_runner_reports_observed_plan_quality_from_model_settings() -> None:
    benchmark = EvalRunner().load_benchmark()
    task = next(task for task in benchmark["tasks"] if task.id == "docs-001")
    observed = [
        {
            "task_id": task.id,
            "summary": "Replace DB_URL references with DATABASE_URL and add migration note.",
            "files_to_modify": ["README.md"],
            "tests_to_add": ["Docs/RUNBOOK.md"],
            "commands_to_run": ["docs link check"],
            "context_citations": ["README.md:1-20", "Docs/RUNBOOK.md:1-30", "app/db/models.py:1-5"],
            "requires_human_approval": True,
        },
        {
            "task_id": "unknown-task",
            "summary": "",
            "files_to_modify": [],
            "commands_to_run": [],
            "context_citations": [],
        },
    ]

    results = EvalRunner().evaluate_observed_plan_quality(tasks=[task], observed_plan_results=observed)

    assert len(results) == 2
    assert results[0]["status"] == "passed"
    assert results[0]["score"] == 1.0
    assert results[0]["context_precision"] == 0.6667
    assert results[1]["status"] == "failed"
    assert "unknown task" in results[1]["failure_reasons"][0]


def test_eval_runner_reports_observed_patch_quality_from_model_settings() -> None:
    benchmark = EvalRunner().load_benchmark()
    task = next(task for task in benchmark["tasks"] if task.id == "docs-001")
    observed = [
        {
            "task_id": task.id,
            "changed_files": ["README.md", "Docs/RUNBOOK.md"],
            "diff_summary": "Replace DB_URL references with DATABASE_URL and add migration note.",
            "validation_commands": ["docs link check"],
            "validation_status": "passed",
            "security_result": "pass",
        },
        {
            "task_id": "unknown-task",
            "changed_files": [],
            "diff_summary": "",
            "validation_commands": [],
            "validation_status": "failed",
            "security_result": "pass",
        },
    ]

    results = EvalRunner().evaluate_observed_patch_quality(tasks=[task], observed_task_results=observed)

    assert len(results) == 2
    assert results[0]["status"] == "passed"
    assert results[0]["score"] == 1.0
    assert results[1]["status"] == "failed"
    assert "unknown task" in results[1]["failure_reasons"][0]


def test_eval_runner_reports_provider_comparisons_from_model_settings() -> None:
    results = EvalRunner().evaluate_provider_comparisons(
        provider_eval_results=[
            {
                "provider": "mock",
                "model": "baseline",
                "task_count": 20,
                "plan_quality_pass_rate": 0.5,
                "patch_quality_pass_rate": 0.5,
                "context_precision": 0.4,
                "human_edit_distance": 0.4,
                "cost_per_run": 0,
                "latency_ms": 100,
            },
            {
                "provider": "openrouter",
                "model": "google/gemma-4-31b-it:free",
                "task_count": 20,
                "plan_quality_pass_rate": 0.9,
                "patch_quality_pass_rate": 0.85,
                "context_precision": 0.8,
                "human_edit_distance": 0.1,
                "cost_per_run": 0.01,
                "latency_ms": 900,
            },
            "invalid",
        ]
    )

    assert len(results) == 2
    assert results[0]["provider"] == "openrouter"
    assert results[0]["quality_score"] > results[1]["quality_score"]


def test_benchmark_report_builder_writes_markdown_and_json(tmp_path) -> None:
    builder = BenchmarkReportBuilder()
    markdown_path, json_path, report = builder.write(
        output_dir=tmp_path,
        report_name="local-report",
        task_count=2,
        observed_evidence={
            "observed_plan_results": [
                {
                    "task_id": "docs-001",
                    "summary": "Replace DB_URL references with DATABASE_URL and add migration note.",
                    "files_to_modify": ["README.md"],
                    "tests_to_add": ["Docs/RUNBOOK.md"],
                    "commands_to_run": ["docs link check"],
                    "context_citations": ["README.md:1-20", "Docs/RUNBOOK.md:1-30"],
                    "requires_human_approval": True,
                }
            ],
            "observed_task_results": [
                {
                    "task_id": "docs-001",
                    "changed_files": ["README.md", "Docs/RUNBOOK.md"],
                    "diff_summary": "Replace DB_URL references with DATABASE_URL and add migration note.",
                    "generated_diff": "- DB_URL\n+ DATABASE_URL\n",
                    "reference_diff": "- DB_URL\n+ DATABASE_URL\n",
                    "validation_commands": ["docs link check"],
                    "validation_status": "passed",
                    "security_result": "pass",
                }
            ],
            "provider_eval_results": [
                {
                    "provider": "openrouter",
                    "model": "google/gemma-4-31b-it:free",
                    "task_count": 20,
                    "plan_quality_pass_rate": 0.9,
                    "patch_quality_pass_rate": 0.85,
                    "context_precision": 0.8,
                    "human_edit_distance": 0.1,
                    "cost_per_run": 0.0,
                    "latency_ms": 900,
                },
                {
                    "provider": "mock",
                    "model": "baseline",
                    "task_count": 20,
                    "plan_quality_pass_rate": 0.5,
                    "patch_quality_pass_rate": 0.5,
                    "context_precision": 0.4,
                    "human_edit_distance": 0.4,
                    "cost_per_run": 0.0,
                    "latency_ms": 100,
                },
            ],
        },
    )

    payload = json_path.read_text(encoding="utf-8")
    markdown = markdown_path.read_text(encoding="utf-8")

    assert report.metrics["benchmark_task_count"] == 2
    assert report.metrics["provider_comparison_count"] == 2
    assert report.metrics["best_provider_by_quality"]["provider"] == "openrouter"
    assert '"provider_comparison_count": 2' in payload
    assert "# RepoPilot Eval Report" in markdown
    assert "## Provider Comparison" in markdown
    assert "openrouter" in markdown


def test_provider_planning_eval_runner_writes_observed_evidence_without_network(tmp_path) -> None:
    class FakeChatClient:
        def complete_json(self, *, model: str, messages: list[dict[str, str]], timeout_seconds: int) -> dict[str, object]:
            assert model == "mock-planner"
            assert timeout_seconds == 5
            prompt = "\n".join(message["content"] for message in messages)
            assert "expected_changed_files" not in prompt
            assert "Task ID: docs-001" in prompt
            return {
                "summary": "Replace DB_URL references with DATABASE_URL and add migration note.",
                "files_to_modify": ["README.md"],
                "tests_to_add": ["Docs/RUNBOOK.md"],
                "commands_to_run": ["docs link check"],
                "context_citations": ["README.md:1-20", "Docs/RUNBOOK.md:1-30"],
                "requires_human_approval": True,
            }

    result = ProviderPlanningEvalRunner(client=FakeChatClient()).run(
        provider="mock",
        model="mock-planner",
        output_dir=tmp_path,
        report_name="provider-plan",
        task_count=1,
        timeout_seconds=5,
        allow_failed_gates=True,
    )
    observed_payload = result.observed_evidence_path.read_text(encoding="utf-8")
    report_markdown = result.markdown_path.read_text(encoding="utf-8")

    assert result.report.metrics["plan_quality_pass_rate"] == 1.0
    assert result.report.metrics["provider_comparison_count"] == 1
    assert result.report.metrics["best_provider_by_quality"]["provider"] == "mock"
    assert "observed_plan_results" in observed_payload
    assert "provider_eval_results" in observed_payload
    assert "mock-planner" in report_markdown


def test_provider_patch_eval_runner_writes_observed_patch_evidence_without_network(tmp_path) -> None:
    class FakeChatClient:
        def complete_json(self, *, model: str, messages: list[dict[str, str]], timeout_seconds: int) -> dict[str, object]:
            assert model == "mock-patcher"
            assert timeout_seconds == 5
            prompt = "\n".join(message["content"] for message in messages)
            assert "expected_changed_files" not in prompt
            assert "Task ID: docs-001" in prompt
            assert "Relevant file excerpts" in prompt
            return {
                "changed_files": ["README.md", "Docs/RUNBOOK.md"],
                "diff_summary": "Replace DB_URL references with DATABASE_URL and add migration note.",
                "generated_diff": "- DB_URL\n+ DATABASE_URL\n",
                "validation_commands": ["docs link check"],
                "validation_status": "not_run",
                "security_result": "pass",
                "ci_status": None,
            }

    result = ProviderPatchEvalRunner(client=FakeChatClient()).run(
        provider="mock",
        model="mock-patcher",
        output_dir=tmp_path,
        report_name="provider-patch",
        task_count=1,
        timeout_seconds=5,
        allow_failed_gates=True,
    )
    observed_payload = result.observed_evidence_path.read_text(encoding="utf-8")
    report_markdown = result.markdown_path.read_text(encoding="utf-8")

    assert result.report.metrics["patch_quality_observed_count"] == 1
    assert result.report.metrics["patch_quality_pass_rate"] == 0.0
    assert result.report.metrics["patch_quality_results"][0]["failure_reasons"] == [
        "Expected passed validation but observed not_run."
    ]
    assert result.report.metrics["provider_comparison_count"] == 1
    assert result.report.metrics["best_provider_by_quality"]["provider"] == "mock"
    assert "observed_task_results" in observed_payload
    assert "validation_note" in observed_payload
    assert "mock-patcher" in report_markdown


class FakeUrlopenResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_provider_chat_client_uses_anthropic_messages_adapter(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_urlopen(request, timeout):
        calls.append(
            {
                "url": request.full_url,
                "headers": {key.lower(): value for key, value in request.header_items()},
                "body": json.loads(request.data.decode("utf-8")),
                "timeout": timeout,
            }
        )
        return FakeUrlopenResponse({"content": [{"type": "text", "text": '{"summary":"claude ok"}'}]})

    monkeypatch.setattr("repopilot_evals.provider_harness.urllib.request.urlopen", fake_urlopen)

    payload = ProviderChatClient(
        provider="anthropic",
        base_url="https://api.anthropic.com",
        api_key="anthropic-test",
    ).complete_json(
        model="claude-sonnet-4-6",
        messages=[{"role": "system", "content": "Return JSON."}, {"role": "user", "content": "Plan."}],
        timeout_seconds=7,
    )

    assert payload == {"summary": "claude ok"}
    assert calls[0]["url"] == "https://api.anthropic.com/v1/messages"
    assert calls[0]["headers"]["x-api-key"] == "anthropic-test"
    assert calls[0]["headers"]["anthropic-version"] == "2023-06-01"
    assert calls[0]["body"]["system"] == "Return JSON."
    assert calls[0]["body"]["messages"][0]["content"][0]["text"] == "Plan."
    assert calls[0]["timeout"] == 7


def test_provider_chat_client_uses_gemini_generate_content_adapter(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_urlopen(request, timeout):
        calls.append(
            {
                "url": request.full_url,
                "headers": {key.lower(): value for key, value in request.header_items()},
                "body": json.loads(request.data.decode("utf-8")),
                "timeout": timeout,
            }
        )
        return FakeUrlopenResponse(
            {"candidates": [{"content": {"parts": [{"text": '{"summary":"gemini ok"}'}]}}]}
        )

    monkeypatch.setattr("repopilot_evals.provider_harness.urllib.request.urlopen", fake_urlopen)

    payload = ProviderChatClient(
        provider="google",
        base_url="https://generativelanguage.googleapis.com",
        api_key="gemini-test",
    ).complete_json(
        model="gemini-2.5-pro",
        messages=[{"role": "system", "content": "Return JSON."}, {"role": "user", "content": "Plan."}],
        timeout_seconds=9,
    )

    assert payload == {"summary": "gemini ok"}
    assert calls[0]["url"] == "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent"
    assert calls[0]["headers"]["x-goog-api-key"] == "gemini-test"
    assert calls[0]["body"]["systemInstruction"] == {"parts": [{"text": "Return JSON."}]}
    assert calls[0]["body"]["contents"][0]["parts"][0]["text"] == "Plan."
    assert calls[0]["body"]["generationConfig"]["responseMimeType"] == "application/json"
    assert calls[0]["timeout"] == 9


def test_provider_harness_defaults_provider_key_env_and_base_url() -> None:
    assert default_provider_api_key_env("openrouter") == "OPENROUTER_API_KEY"
    assert default_provider_api_key_env("anthropic") == "ANTHROPIC_API_KEY"
    assert default_provider_api_key_env("google") == "GEMINI_API_KEY"
    assert default_provider_base_url("google") == "https://generativelanguage.googleapis.com"


def test_provider_credentials_use_runtime_secret_store(tmp_path, monkeypatch) -> None:
    key = Fernet.generate_key()
    fernet = Fernet(key)
    store_path = tmp_path / "runtime-secrets.json"
    key_path = tmp_path / "runtime-secrets.key"
    key_path.write_bytes(key + b"\n")
    store_path.write_text(
        json.dumps(
            {
                "version": 1,
                "values": {
                    "MODEL_PROVIDER": fernet.encrypt(b"openrouter").decode("utf-8"),
                    "MODEL_API_KEY": fernet.encrypt(b"runtime-test-key").decode("utf-8"),
                    "MODEL_BASE_URL": fernet.encrypt(b"https://openrouter.example/api/v1").decode("utf-8"),
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("REPOPILOT_RUNTIME_SECRETS_STORE_PATH", str(store_path))
    monkeypatch.setenv("REPOPILOT_RUNTIME_SECRETS_KEY_PATH", str(key_path))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    credentials = resolve_provider_credentials(provider="openrouter")

    assert credentials.api_key == "runtime-test-key"
    assert credentials.base_url == "https://openrouter.example/api/v1"
    assert credentials.source == "runtime_secret_store"


def test_provider_credentials_keep_environment_override(tmp_path, monkeypatch) -> None:
    key = Fernet.generate_key()
    fernet = Fernet(key)
    store_path = tmp_path / "runtime-secrets.json"
    key_path = tmp_path / "runtime-secrets.key"
    key_path.write_bytes(key)
    store_path.write_text(
        json.dumps(
            {
                "values": {
                    "MODEL_PROVIDER": fernet.encrypt(b"openrouter").decode(),
                    "MODEL_API_KEY": fernet.encrypt(b"runtime-key").decode(),
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("REPOPILOT_RUNTIME_SECRETS_STORE_PATH", str(store_path))
    monkeypatch.setenv("REPOPILOT_RUNTIME_SECRETS_KEY_PATH", str(key_path))
    monkeypatch.setenv("OPENROUTER_API_KEY", "env-key")

    credentials = resolve_provider_credentials(provider="openrouter")

    assert credentials.api_key == "env-key"
    assert credentials.source == "environment:OPENROUTER_API_KEY"


def test_provider_credentials_ignore_runtime_secret_for_other_provider(tmp_path, monkeypatch) -> None:
    key = Fernet.generate_key()
    fernet = Fernet(key)
    store_path = tmp_path / "runtime-secrets.json"
    key_path = tmp_path / "runtime-secrets.key"
    key_path.write_bytes(key)
    store_path.write_text(
        json.dumps(
            {
                "values": {
                    "MODEL_PROVIDER": fernet.encrypt(b"openrouter").decode(),
                    "MODEL_API_KEY": fernet.encrypt(b"runtime-key").decode(),
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("REPOPILOT_RUNTIME_SECRETS_STORE_PATH", str(store_path))
    monkeypatch.setenv("REPOPILOT_RUNTIME_SECRETS_KEY_PATH", str(key_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    credentials = resolve_provider_credentials(provider="anthropic")

    assert credentials.api_key is None
    assert credentials.source == "missing"


def test_eval_fixture_repositories_are_executable() -> None:
    fixture_root = EvalRunner().benchmark_path.parent / "fixtures"

    python_result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests"],
        cwd=fixture_root / "python-service",
        capture_output=True,
        text=True,
        check=False,
    )
    assert python_result.returncode == 0, python_result.stdout + python_result.stderr

    web_result = subprocess.run(
        ["npm", "test", "--silent"],
        cwd=fixture_root / "web-dashboard",
        capture_output=True,
        text=True,
        check=False,
    )
    assert web_result.returncode == 0, web_result.stdout + web_result.stderr


def test_eval_runner_persists_fixture_report() -> None:
    from repopilot_contracts import EvalRunRequest

    db = FakeDb()
    result = asyncio.run(
        EvalRunner().run(
            db,
            request=EvalRunRequest(
                task_count=5,
                model_config={
                    "observed_plan_results": [
                        {
                            "task_id": "docs-001",
                            "summary": "Replace DB_URL references with DATABASE_URL and add migration note.",
                            "files_to_modify": ["README.md"],
                            "tests_to_add": ["Docs/RUNBOOK.md"],
                            "commands_to_run": ["docs link check"],
                            "context_citations": ["README.md:1-20", "Docs/RUNBOOK.md:1-30"],
                            "requires_human_approval": True,
                        }
                    ],
                    "observed_task_results": [
                        {
                            "task_id": "docs-001",
                            "changed_files": ["README.md", "Docs/RUNBOOK.md"],
                            "diff_summary": "Replace DB_URL references with DATABASE_URL and add migration note.",
                            "generated_diff": "- DB_URL\n+ DATABASE_URL\n",
                            "reference_diff": "- DB_URL\n+ DATABASE_URL\n",
                            "validation_commands": ["docs link check"],
                            "validation_status": "passed",
                            "security_result": "pass",
                        }
                    ],
                    "provider_eval_results": [
                        {
                            "provider": "openrouter",
                            "model": "google/gemma-4-31b-it:free",
                            "task_count": 20,
                            "plan_quality_pass_rate": 0.9,
                            "patch_quality_pass_rate": 0.85,
                            "context_precision": 0.8,
                            "human_edit_distance": 0.1,
                            "cost_per_run": 0.01,
                            "latency_ms": 900,
                        },
                        {
                            "provider": "mock",
                            "model": "baseline",
                            "task_count": 20,
                            "plan_quality_pass_rate": 0.5,
                            "patch_quality_pass_rate": 0.5,
                            "context_precision": 0.4,
                            "human_edit_distance": 0.4,
                            "cost_per_run": 0,
                            "latency_ms": 100,
                        },
                    ],
                },
            ),
        )
    )

    assert result.metrics["benchmark_task_count"] == 5
    assert result.metrics["plan_quality_observed_count"] == 1
    assert result.metrics["plan_quality_pass_rate"] == 1.0
    assert result.metrics["context_precision"] == 1.0
    assert result.metrics["patch_quality_observed_count"] == 1
    assert result.metrics["patch_quality_pass_rate"] == 1.0
    assert result.metrics["human_edit_distance"] == 0.0
    assert result.metrics["quality_gate_results"]["human_edit_distance_required"] is True
    assert result.metrics["provider_comparison_count"] == 2
    assert result.metrics["best_provider_by_quality"]["provider"] == "openrouter"
    assert result.metrics["quality_gate_results"]["provider_comparisons_required"] is True
    assert len(result.task_outcomes) == 5
    assert result.report_uri.startswith("local://evals/")
    assert db.commits == 1
