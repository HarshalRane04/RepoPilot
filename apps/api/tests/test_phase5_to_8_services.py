from __future__ import annotations

import asyncio
import json
import shutil
import sys
from pathlib import Path
from uuid import uuid4

from repopilot_contracts import CodeContextChunk, CodeContextPack, ImplementationPlan, SandboxCommandRequest
from repopilot_policy_engine import PolicyEngine as PackagePolicyEngine

from app.api.routes.plans import PlanDecisionRequest, PlanRevisionRequest, approve_plan, reject_plan, revise_plan
from app.db.models import AgentRun, CodeChunk, Installation, Issue, Plan, Repository
from app.services.auth import CurrentUser
from app.services.model_gateway import ModelGateway
from app.services.planning import PlanningPromptBuilder, PlanningService, implementation_plan_from_db
from app.services.policy import PolicyEngine
from app.services.repo_indexer import RepositoryIndexer
from app.services.sandbox import WORKSPACE_ROOT, SandboxRunner
from app.services.security_envelope import redact_data, stable_json_hash


class ScalarResult:
    def __init__(self, items: list[object]) -> None:
        self.items = items

    def scalars(self):
        return self

    def all(self):
        return self.items


class FakeApprovalDb:
    def __init__(self, *, plan: Plan, issue: Issue, repository: Repository, runs: list[AgentRun] | None = None) -> None:
        self.plan = plan
        self.issue = issue
        self.repository = repository
        self.runs = runs or []
        self.added: list[object] = []
        self.commits = 0

    async def get(self, model, item_id):
        if model is Plan and self.plan.id == item_id:
            return self.plan
        if model is Issue and self.issue.id == item_id:
            return self.issue
        if model is Repository and self.repository.id == item_id:
            return self.repository
        return None

    async def scalar(self, _statement):
        return None

    async def execute(self, _statement):
        return ScalarResult(self.runs)

    def add(self, item: object) -> None:
        if getattr(item, "id", None) is None:
            item.id = uuid4()
        self.added.append(item)

    async def flush(self) -> None:
        for item in self.added:
            if getattr(item, "id", None) is None:
                item.id = uuid4()

    async def commit(self) -> None:
        self.commits += 1


class FakeContextDb:
    def __init__(self, chunks: list[CodeChunk]) -> None:
        self.chunks = chunks

    async def execute(self, _statement):
        return ScalarResult(self.chunks)


def test_indexer_chunks_text_with_line_citations(tmp_path: Path) -> None:
    source = tmp_path / "demo.py"
    source.write_text(
        "\n".join(
            [
                "def list_repositories():",
                "    return []",
                "",
                "def render_dashboard():",
                "    return list_repositories()",
            ]
        ),
        encoding="utf-8",
    )

    chunks = RepositoryIndexer()._chunk_file(relative_path="demo.py", text=source.read_text(encoding="utf-8"))

    assert chunks
    assert chunks[0].file_path == "demo.py"
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 3
    assert chunks[0].symbol_name == "list_repositories"
    assert chunks[0].chunk_type == "source"
    assert chunks[1].start_line == 4
    assert chunks[1].end_line == 5
    assert chunks[1].symbol_name == "render_dashboard"


def test_indexer_chunks_markdown_with_heading_citations() -> None:
    text = "\n".join(["# Overview", "RepoPilot context.", "", "## Details", "Index chunks by heading."])

    chunks = RepositoryIndexer()._chunk_file(relative_path="README.md", text=text)

    assert [chunk.symbol_name for chunk in chunks] == ["Overview", "Details"]
    assert [chunk.chunk_type for chunk in chunks] == ["doc", "doc"]
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 3
    assert chunks[1].start_line == 4
    assert chunks[1].end_line == 5


def test_indexer_classifies_tests_and_config_chunks() -> None:
    indexer = RepositoryIndexer()
    test_chunks = indexer._chunk_file(relative_path="tests/test_api.py", text="def test_ok():\n    pass\n")
    config_chunks = indexer._chunk_file(relative_path="package.json", text='{"scripts":{}}\n')

    assert test_chunks[0].chunk_type == "test"
    assert config_chunks[0].chunk_type == "config"


def test_indexer_embeddings_are_deterministic() -> None:
    indexer = RepositoryIndexer()

    first = indexer._embed_text("dashboard crash pagination")
    second = indexer._embed_text("dashboard crash pagination")

    assert first == second
    assert len(first) == 1536
    assert sum(first) > 0


def test_indexer_skips_secret_like_files(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("def ok():\n    return True\n", encoding="utf-8")
    (tmp_path / ".secrets").mkdir()
    (tmp_path / ".secrets" / "config.json").write_text('{"token":"secret"}', encoding="utf-8")
    (tmp_path / "secrets.py").write_text("TOKEN = 'secret'\n", encoding="utf-8")
    (tmp_path / "private.pem").write_text("-----BEGIN PRIVATE KEY-----\n", encoding="utf-8")

    files = RepositoryIndexer()._iter_indexable_files(tmp_path, max_files=20, max_file_bytes=10000)

    assert [path.name for path in files] == ["app.py"]


def test_indexer_skips_generated_dirs_files_and_symlink_escapes(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("def ok():\n    return True\n", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "package.json").write_text('{"private": true}\n', encoding="utf-8")
    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "library.py").write_text("def vendored():\n    return True\n", encoding="utf-8")
    (tmp_path / "target").mkdir()
    (tmp_path / "target" / "build.rs").write_text("fn generated() {}\n", encoding="utf-8")
    (tmp_path / "bundle.min.js").write_text("function generated() {}\n", encoding="utf-8")
    outside = tmp_path.parent / f"{tmp_path.name}-outside.py"
    outside.write_text("TOKEN = 'outside-root'\n", encoding="utf-8")
    symlink = tmp_path / "linked.py"
    try:
        symlink.symlink_to(outside)
    except OSError:
        symlink = None

    files = RepositoryIndexer()._iter_indexable_files(tmp_path, max_files=20, max_file_bytes=10000)

    assert [path.name for path in files] == ["app.py"]
    if symlink is not None:
        assert symlink.name not in {path.name for path in files}


def test_retrieve_context_includes_score_breakdown_and_freshness(monkeypatch) -> None:
    monkeypatch.setattr("app.services.repo_indexer.settings.embedding_provider", "mock")
    monkeypatch.setattr("app.services.repo_indexer.settings.embedding_model", "mock-embedding")
    monkeypatch.setattr("app.services.repo_indexer.settings.embedding_dimensions", 1536)
    repository_id = uuid4()
    indexer = RepositoryIndexer()
    text = "export function renderDashboard() {\n  return listRepositories();\n}"
    chunk = CodeChunk(
        repository_id=repository_id,
        file_path="apps/web/app/dashboard.tsx",
        symbol_name="renderDashboard",
        chunk_type="source",
        chunk_text=f"@@ lines=10-12\n{text}",
        embedding=ModelGateway()._mock_embedding("dashboard render repositories", dimensions=1536),
        embedding_provider="mock",
        embedding_model="mock-embedding",
        embedding_dimensions=1536,
        commit_sha="abc123",
    )

    context = asyncio.run(
        indexer.retrieve_context(
            FakeContextDb([chunk]),
            repository_id=repository_id,
            query="dashboard repositories",
            limit=1,
        )
    )

    selected = context.chunks[0]
    assert selected.score > 0
    assert selected.lexical_score > 0
    assert selected.semantic_score > 0
    assert selected.path_score > 0
    assert "query terms matched" in selected.selection_reason
    assert selected.freshness == {
        "commit_sha": "abc123",
        "embedding_provider": "mock",
        "embedding_model": "mock-embedding",
        "embedding_dimensions": 1536,
        "chunker_version": "semantic-v1",
        "stale": False,
    }
    assert context.citations == ["apps/web/app/dashboard.tsx:10-12"]


def test_indexer_detects_embedding_model_staleness(monkeypatch) -> None:
    monkeypatch.setattr("app.services.repo_indexer.settings.embedding_provider", "mock")
    monkeypatch.setattr("app.services.repo_indexer.settings.embedding_model", "mock-embedding-v2")
    monkeypatch.setattr("app.services.repo_indexer.settings.embedding_dimensions", 1536)
    chunk = type(
        "Chunk",
        (),
        {
            "embedding_provider": "mock",
            "embedding_model": "mock-embedding-v1",
            "embedding_dimensions": 1536,
        },
    )()

    assert RepositoryIndexer().index_is_stale_for_embeddings([chunk]) is True


def test_indexer_detects_index_metadata_staleness(monkeypatch) -> None:
    monkeypatch.setattr("app.services.repo_indexer.settings.embedding_provider", "mock")
    monkeypatch.setattr("app.services.repo_indexer.settings.embedding_model", "mock-embedding")
    monkeypatch.setattr("app.services.repo_indexer.settings.embedding_dimensions", 1536)
    fresh = type(
        "Index",
        (),
        {
            "embedding_provider": "mock",
            "embedding_model": "mock-embedding",
            "embedding_dimensions": 1536,
            "chunker_version": "semantic-v1",
        },
    )()
    stale = type(
        "Index",
        (),
        {
            "embedding_provider": "mock",
            "embedding_model": "mock-embedding",
            "embedding_dimensions": 1536,
            "chunker_version": "semantic-v0",
        },
    )()

    indexer = RepositoryIndexer()

    assert indexer.index_metadata_is_stale(fresh) is False
    assert indexer.index_metadata_is_stale(stale) is True


def test_policy_allows_low_risk_plan() -> None:
    plan = ImplementationPlan(
        plan_id="plan-1",
        issue_id="issue-1",
        files_to_modify=["apps/api/app/api/routes/repos.py"],
        commands_to_run=["pytest"],
        rollback_plan="Close the PR.",
    )

    decision = PolicyEngine().evaluate_plan(plan)

    assert decision.decision == "allow"


def test_api_policy_service_reexports_policy_engine_package() -> None:
    assert PolicyEngine is PackagePolicyEngine


def test_planning_service_builds_review_ready_plan_fields() -> None:
    issue = Issue(id=uuid4(), repository_id=uuid4(), number=12, title="Fix dashboard crash", risk_score=20)

    plan = PlanningService()._build_plan(
        issue=issue,
        context_citations=["apps/web/app/page.tsx:1-20", "apps/web/app/page.test.tsx:1-15"],
    )

    assert plan.summary
    assert plan.context_citations == ["apps/web/app/page.tsx:1-20", "apps/web/app/page.test.tsx:1-15"]
    assert plan.intended_changes
    assert plan.validation_strategy
    assert plan.assumptions


def test_planning_prompt_includes_context_evidence_and_redacts_excerpts() -> None:
    issue = Issue(
        id=uuid4(),
        repository_id=uuid4(),
        number=12,
        title="Fix dashboard crash",
        body_hash="body-hash",
        issue_type="bug",
        complexity="small",
        risk_score=30,
    )
    deterministic_plan = PlanningService()._build_plan(
        issue=issue,
        context_citations=["apps/web/app/dashboard.tsx:10-12"],
    )
    secret = "sk-live-secret-value-1234567890"
    context = CodeContextPack(
        repository_id=str(issue.repository_id),
        query=issue.title,
        citations=["apps/web/app/dashboard.tsx:10-12"],
        chunks=[
            CodeContextChunk(
                file_path="apps/web/app/dashboard.tsx",
                symbol_name="renderDashboard",
                chunk_type="source",
                start_line=10,
                end_line=12,
                score=1.2,
                semantic_score=0.4,
                lexical_score=1.0,
                path_score=0.2,
                selection_reason="query terms matched chunk text",
                freshness={"commit_sha": "abc123", "stale": False},
                text=f"export function renderDashboard() {{ return '{secret}'; }}",
            )
        ],
    )

    payload = json.loads(
        PlanningPromptBuilder().user_prompt(
            issue=issue,
            context=context,
            deterministic_plan=deterministic_plan,
        )
    )

    chunk = payload["repository_context"]["chunks"][0]
    assert chunk["citation"] == "apps/web/app/dashboard.tsx:10-12"
    assert chunk["scores"] == {"total": 1.2, "semantic": 0.4, "lexical": 1.0, "path": 0.2}
    assert chunk["freshness"] == {"commit_sha": "abc123", "stale": False}
    assert secret not in chunk["excerpt"]
    assert "[REDACTED_SECRET]" in chunk["excerpt"]
    assert "expected_plan_evidence" in payload


def test_plan_loader_ignores_runtime_metadata() -> None:
    plan = Plan(
        issue_id="2ef3767b-5785-4f99-91e8-76c92bb457d0",
        plan_json={
            "plan_id": "pending",
            "issue_id": "issue-1",
            "files_to_modify": ["apps/api/app/api/routes/repos.py"],
            "commands_to_run": ["pytest"],
            "rollback_plan": "Close the PR.",
            "context": {"citations": []},
            "policy_decision": {"decision": "allow", "reason": "ok"},
            "approval_policy_decision": {"decision": "allow", "reason": "ok"},
            "approved_plan_hash": "abc123",
        },
    )

    loaded = implementation_plan_from_db(plan)

    assert loaded.files_to_modify == ["apps/api/app/api/routes/repos.py"]


def test_plan_approval_stores_stable_hash() -> None:
    plan_id = uuid4()
    issue_id = uuid4()
    installation = Installation(id=uuid4(), github_installation_id="1", account_name="octo")
    repository = Repository(id=uuid4(), installation_id=installation.id, owner="octo", name="demo")
    issue = Issue(id=issue_id, repository_id=repository.id, number=1, title="Fix routing")
    plan = Plan(
        id=plan_id,
        issue_id=issue_id,
        plan_json={
            "plan_id": str(plan_id),
            "issue_id": str(issue_id),
            "files_to_modify": ["apps/api/app/api/routes/repos.py"],
            "commands_to_run": ["pytest"],
            "rollback_plan": "Close the PR.",
        },
    )
    db = FakeApprovalDb(plan=plan, issue=issue, repository=repository)

    response = asyncio.run(
        approve_plan(
            plan_id=plan_id,
            _rate_limit=None,
            db=db,
            current_user=CurrentUser(username="harshal", role="owner"),
        )
    )

    assert response["status"] == "approved"
    assert response["approved_plan_hash"] == plan.plan_json["approved_plan_hash"]
    assert plan.plan_json["plan_hash"] == plan.plan_json["approved_plan_hash"]
    assert db.commits == 1


def test_plan_reject_records_reason() -> None:
    plan_id = uuid4()
    issue_id = uuid4()
    installation = Installation(id=uuid4(), github_installation_id="1", account_name="octo")
    repository = Repository(id=uuid4(), installation_id=installation.id, owner="octo", name="demo")
    issue = Issue(id=issue_id, repository_id=repository.id, number=1, title="Fix routing")
    plan = Plan(id=plan_id, issue_id=issue_id, plan_json={"plan_id": str(plan_id), "issue_id": str(issue_id), "rollback_plan": "Close the PR."})
    db = FakeApprovalDb(plan=plan, issue=issue, repository=repository)

    response = asyncio.run(
        reject_plan(
            plan_id=plan_id,
            request=PlanDecisionRequest(reason="Scope is too broad."),
            _rate_limit=None,
            db=db,
            current_user=CurrentUser(username="harshal", role="owner"),
        )
    )

    assert response["status"] == "rejected"
    assert plan.approval_status == "rejected"
    assert plan.plan_json["rejection_reason"] == "Scope is too broad."


def test_plan_revise_creates_waiting_plan_version() -> None:
    plan_id = uuid4()
    issue_id = uuid4()
    installation = Installation(id=uuid4(), github_installation_id="1", account_name="octo")
    repository = Repository(id=uuid4(), installation_id=installation.id, owner="octo", name="demo")
    issue = Issue(id=issue_id, repository_id=repository.id, number=1, title="Fix routing")
    plan = Plan(id=plan_id, issue_id=issue_id, version=2, plan_json={"plan_id": str(plan_id), "issue_id": str(issue_id), "rollback_plan": "Close the PR."})
    run = AgentRun(id=uuid4(), issue_id=issue_id, plan_id=plan_id, state="WAIT_FOR_APPROVAL")
    db = FakeApprovalDb(plan=plan, issue=issue, repository=repository, runs=[run])

    response = asyncio.run(
        revise_plan(
            plan_id=plan_id,
            request=PlanRevisionRequest(instructions="Add regression test coverage first."),
            _rate_limit=None,
            db=db,
            current_user=CurrentUser(username="harshal", role="owner"),
        )
    )

    new_plan = next(item for item in db.added if isinstance(item, Plan) and item is not plan)
    assert response["status"] == "revision_requested"
    assert response["new_plan_id"] == str(new_plan.id)
    assert plan.approval_status == "revised"
    assert new_plan.approval_status == "waiting"
    assert new_plan.version == 3
    assert new_plan.plan_json["revision_parent_plan_id"] == str(plan.id)
    assert run.plan_id == new_plan.id


def test_stable_json_hash_ignores_dictionary_order() -> None:
    first = stable_json_hash({"b": [2, 1], "a": {"z": "x"}})
    second = stable_json_hash({"a": {"z": "x"}, "b": [2, 1]})

    assert first == second
    assert len(first) == 64


def test_redact_data_hides_secret_keys_and_values() -> None:
    secret = "sk-live-secret-value-1234567890"
    redacted = redact_data({"model_api_key": secret, "log": f"provider returned {secret}"})

    assert secret not in str(redacted)
    assert redacted["model_api_key"] == "[REDACTED_SECRET]"
    assert "[REDACTED_SECRET]" in redacted["log"]


def test_policy_escalates_high_risk_files() -> None:
    plan = ImplementationPlan(
        plan_id="plan-1",
        issue_id="issue-1",
        files_to_modify=[".github/workflows/ci.yml", ".npmrc", "private.pem"],
        commands_to_run=["pytest"],
        rollback_plan="Close the PR.",
    )

    decision = PolicyEngine().evaluate_plan(plan)

    assert decision.decision == "escalate"
    assert decision.required_approvals == ["maintainer"]
    assert ".npmrc" in decision.blocked_patterns
    assert "private.pem" in decision.blocked_patterns


def test_policy_denies_blocked_command() -> None:
    decision = PolicyEngine().evaluate_command("printenv")

    assert decision.decision == "deny"


def test_sandbox_blocks_non_allowlisted_command() -> None:
    run_id = uuid4()
    workspace = WORKSPACE_ROOT / str(run_id)
    shutil.rmtree(workspace, ignore_errors=True)
    workspace.mkdir(parents=True)

    try:
        result = SandboxRunner().run_command(
            SandboxCommandRequest(
                workspace_path=str(workspace),
                command="printenv",
            ),
            run_id=run_id,
        )
    finally:
        shutil.rmtree(workspace, ignore_errors=True)

    assert result.status == "blocked"
    assert result.blocked_reason


def test_sandbox_safe_env_preserves_current_python_bin(monkeypatch, tmp_path: Path) -> None:
    venv_bin = tmp_path / "venv" / "bin"
    venv_bin.mkdir(parents=True)
    python_shim = venv_bin / "python"
    python_shim.symlink_to(Path(sys.executable))
    monkeypatch.setattr("app.services.sandbox.sys.executable", str(python_shim))

    env = SandboxRunner()._safe_env()

    assert env["PATH"].split(":")[0] == str(venv_bin)


def test_sandbox_redacts_stdout_and_stderr_before_return(tmp_path: Path) -> None:
    runner = SandboxRunner(backend="local")
    secret = "sk-live-secret-value-1234567890"
    result = runner._execute(
        command="python -m pytest",
        args=[
            sys.executable,
            "-c",
            "import sys; print('token=sk-live-secret-value-1234567890'); print('stderr sk-live-secret-value-1234567890', file=sys.stderr)",
        ],
        cwd=tmp_path,
        timeout_seconds=5,
        env=runner._safe_env(),
    )

    assert result.status == "passed"
    assert secret not in result.stdout
    assert secret not in result.stderr
    assert "[REDACTED_SECRET]" in result.stdout
    assert "[REDACTED_SECRET]" in result.stderr
