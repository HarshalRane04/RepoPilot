from __future__ import annotations

import asyncio
import shutil
from types import SimpleNamespace
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from repopilot_contracts import AgentRunState, ImplementationPlan, PlanApprovalStatus, ToolBlockType, ToolCallRequest

from app.core.config import settings
from app.db.models import AgentRun, Plan
from app.main import app
from app.services.tools import ToolExecutor, get_tool_registry
from app.services.tools.registry import WORKSPACE_ROOT
from app.services.security_envelope import stable_json_hash

DEV_AUTH_HEADERS = {"X-RepoPilot-User": "harshal", "X-RepoPilot-Role": "owner"}


def approved_plan_payload(
    *,
    plan_id,
    issue_id,
    files_to_modify: list[str],
    tests_to_add: list[str] | None = None,
) -> dict[str, object]:
    plan = ImplementationPlan(
        plan_id=str(plan_id),
        issue_id=str(issue_id),
        files_to_modify=files_to_modify,
        tests_to_add=tests_to_add or [],
        commands_to_run=["pytest"],
        rollback_plan="Close the PR.",
    )
    payload = plan.model_dump(mode="json")
    payload["approved_plan_hash"] = stable_json_hash(plan.model_dump(mode="json", exclude={"plan_hash"}))
    payload["plan_hash"] = payload["approved_plan_hash"]
    return payload


class FakeDb:
    def __init__(self, *, run: AgentRun | None = None, plan: Plan | None = None) -> None:
        self.run = run
        self.plan = plan
        self.added: list[object] = []
        self.commits = 0

    async def get(self, model, item_id):
        if model is AgentRun and self.run is not None and self.run.id == item_id:
            return self.run
        if model is Plan and self.plan is not None and self.plan.id == item_id:
            return self.plan
        return None

    def add(self, item: object) -> None:
        self.added.append(item)

    async def commit(self) -> None:
        self.commits += 1


def test_tool_registry_exposes_model_facing_definitions() -> None:
    definitions = {tool.name: tool for tool in get_tool_registry().definitions()}

    assert "repo.search_context" in definitions
    assert "repo.read_file" in definitions
    assert "repo.read_files" in definitions
    assert "workspace.write_file" in definitions
    assert "sandbox.run_command" in definitions
    assert "github.create_branch" in definitions
    assert definitions["repo.read_file"].permission == "read"
    assert definitions["repo.read_files"].permission == "read"
    assert definitions["workspace.write_file"].requires_approved_plan is True
    assert definitions["github.create_branch"].enabled is True
    assert definitions["github.create_branch"].requires_github_write_mode is True
    assert "properties" in definitions["repo.read_file"].input_schema


def test_tools_route_lists_definitions_without_database_connection(monkeypatch) -> None:
    monkeypatch.setattr(settings, "dev_header_auth_enabled", True)
    monkeypatch.setattr(settings, "environment", "local")
    client = TestClient(app)

    response = client.get("/tools", headers=DEV_AUTH_HEADERS)

    assert response.status_code == 200
    names = {tool["name"] for tool in response.json()["tools"]}
    assert "repo.grep" in names
    assert "security.scan_patch" in names


def test_executor_blocks_unknown_tool_and_records_agent_step() -> None:
    run = AgentRun(id=uuid4(), state=AgentRunState.WAIT_FOR_APPROVAL.value)
    db = FakeDb(run=run)
    request = ToolCallRequest(
        run_id=run.id,
        state=AgentRunState.WAIT_FOR_APPROVAL,
        tool_name="missing.tool",
        actor="agent",
        arguments={},
    )

    result = asyncio.run(ToolExecutor().execute(db, request=request))

    assert result.status == "blocked"
    assert result.blocked_reason == "Unknown tool."
    assert result.block_type == ToolBlockType.UNKNOWN_TOOL
    assert any(getattr(item, "step_name", "") == "TOOL_CALL:missing.tool" for item in db.added)
    assert db.commits == 1


def test_executor_redacts_secret_arguments_in_persisted_steps() -> None:
    run = AgentRun(id=uuid4(), state=AgentRunState.WAIT_FOR_APPROVAL.value)
    db = FakeDb(run=run)
    secret = "sk-live-secret-value-1234567890"

    result = asyncio.run(
        ToolExecutor().execute(
            db,
            request=ToolCallRequest(
                run_id=run.id,
                state=AgentRunState.WAIT_FOR_APPROVAL,
                tool_name="missing.tool",
                actor="agent",
                arguments={"model_api_key": secret, "prompt": f"use {secret}"},
            ),
        )
    )

    assert result.status == "blocked"
    step = next(item for item in db.added if getattr(item, "step_name", "") == "TOOL_CALL:missing.tool")
    assert secret not in str(step.output_json)
    assert "[REDACTED_SECRET]" in str(step.output_json)


def test_executor_runs_read_file_tool_and_records_success() -> None:
    run = AgentRun(id=uuid4(), state=AgentRunState.WAIT_FOR_APPROVAL.value)
    source = WORKSPACE_ROOT / str(run.id)
    shutil.rmtree(source, ignore_errors=True)
    source.mkdir(parents=True)
    (source / "demo.py").write_text("alpha\nbeta\n", encoding="utf-8")
    db = FakeDb(run=run)

    try:
        result = asyncio.run(
            ToolExecutor().execute(
                db,
                request=ToolCallRequest(
                    run_id=run.id,
                    state=AgentRunState.WAIT_FOR_APPROVAL,
                    tool_name="repo.read_file",
                    actor="agent",
                    arguments={"workspace_path": str(source), "path": "demo.py", "start_line": 2, "end_line": 2},
                ),
            )
        )
    finally:
        shutil.rmtree(source, ignore_errors=True)

    assert result.status == "succeeded"
    assert result.output["content"] == "beta"
    assert any(getattr(item, "step_name", "") == "TOOL_CALL:repo.read_file" for item in db.added)


def test_executor_runs_batched_read_files_with_per_file_errors() -> None:
    run = AgentRun(id=uuid4(), state=AgentRunState.WAIT_FOR_APPROVAL.value)
    source = WORKSPACE_ROOT / str(run.id)
    shutil.rmtree(source, ignore_errors=True)
    source.mkdir(parents=True)
    (source / "demo.py").write_text("alpha\nbeta\n", encoding="utf-8")
    (source / ".env.local").write_text("TOKEN=fake-value\n", encoding="utf-8")
    db = FakeDb(run=run)

    try:
        result = asyncio.run(
            ToolExecutor().execute(
                db,
                request=ToolCallRequest(
                    run_id=run.id,
                    state=AgentRunState.WAIT_FOR_APPROVAL,
                    tool_name="repo.read_files",
                    actor="agent",
                    arguments={
                        "workspace_path": str(source),
                        "files": [
                            {"path": "demo.py", "start_line": 2, "end_line": 2},
                            {"path": ".env.local"},
                            {"path": "missing.py"},
                        ],
                    },
                ),
            )
        )
    finally:
        shutil.rmtree(source, ignore_errors=True)

    assert result.status == "succeeded"
    assert result.output["succeeded_count"] == 1
    assert result.output["blocked_count"] == 2
    assert result.output["files"][0]["content"] == "beta"
    error_reasons = {item["path"]: item["blocked_reason"] for item in result.output["errors"]}
    assert "sensitive file" in error_reasons[".env.local"]
    assert "File not found" in error_reasons["missing.py"]
    assert any(getattr(item, "step_name", "") == "TOOL_CALL:repo.read_files" for item in db.added)


def test_repo_read_tools_filter_sensitive_workspace_files() -> None:
    run = AgentRun(id=uuid4(), state=AgentRunState.WAIT_FOR_APPROVAL.value)
    workspace = WORKSPACE_ROOT / str(run.id)
    shutil.rmtree(workspace, ignore_errors=True)
    workspace.mkdir(parents=True)
    (workspace / "app.py").write_text("print('ok')\n", encoding="utf-8")
    (workspace / ".env.local").write_text("MODEL_API_KEY=sk-live-secret-value-1234567890\n", encoding="utf-8")
    (workspace / ".npmrc").write_text("//registry.example/:_authToken=npm-secret-token\n", encoding="utf-8")
    (workspace / "id_ed25519").write_text("-----BEGIN OPENSSH PRIVATE KEY-----\n", encoding="utf-8")
    (workspace / "secrets").mkdir()
    (workspace / "secrets" / "config.json").write_text('{"token":"ghp_live_secret_value"}\n', encoding="utf-8")
    db = FakeDb(run=run)

    try:
        listed = asyncio.run(
            ToolExecutor().execute(
                db,
                request=ToolCallRequest(
                    run_id=run.id,
                    state=AgentRunState.WAIT_FOR_APPROVAL,
                    tool_name="repo.list_files",
                    actor="agent",
                    arguments={"workspace_path": str(workspace)},
                ),
            )
        )
        grep = asyncio.run(
            ToolExecutor().execute(
                db,
                request=ToolCallRequest(
                    run_id=run.id,
                    state=AgentRunState.WAIT_FOR_APPROVAL,
                    tool_name="repo.grep",
                    actor="agent",
                    arguments={"workspace_path": str(workspace), "query": "secret"},
                ),
            )
        )
        tree = asyncio.run(
            ToolExecutor().execute(
                db,
                request=ToolCallRequest(
                    run_id=run.id,
                    state=AgentRunState.WAIT_FOR_APPROVAL,
                    tool_name="repo.summarize_tree",
                    actor="agent",
                    arguments={"workspace_path": str(workspace)},
                ),
            )
        )
        read_secret = asyncio.run(
            ToolExecutor().execute(
                db,
                request=ToolCallRequest(
                    run_id=run.id,
                    state=AgentRunState.WAIT_FOR_APPROVAL,
                    tool_name="repo.read_file",
                    actor="agent",
                    arguments={"workspace_path": str(workspace), "path": ".env.local"},
                ),
            )
        )
    finally:
        shutil.rmtree(workspace, ignore_errors=True)

    assert listed.status == "succeeded"
    assert [item["path"] for item in listed.output["files"]] == ["app.py"]
    assert grep.status == "succeeded"
    assert grep.output["matches"] == []
    assert tree.status == "succeeded"
    assert tree.output["entries"] == ["app.py"]
    assert read_secret.status == "blocked"
    assert "sensitive file" in (read_secret.blocked_reason or "")


def test_workspace_create_run_copy_excludes_sensitive_files(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(settings, "repository_workspace_root", str(tmp_path))
    plan_id = uuid4()
    issue_id = uuid4()
    run = AgentRun(id=uuid4(), plan_id=plan_id, state=AgentRunState.CREATE_BRANCH.value)
    plan = Plan(
        id=plan_id,
        issue_id=issue_id,
        approval_status=PlanApprovalStatus.APPROVED.value,
        plan_json=approved_plan_payload(plan_id=plan_id, issue_id=issue_id, files_to_modify=["app.py"]),
    )
    source = tmp_path / "repo"
    source.mkdir()
    (source / "app.py").write_text("print('ok')\n", encoding="utf-8")
    (source / ".env.local").write_text("MODEL_API_KEY=sk-live-secret-value-1234567890\n", encoding="utf-8")
    (source / ".pypirc").write_text("password = pypi-secret\n", encoding="utf-8")
    (source / "private.pem").write_text("-----BEGIN PRIVATE KEY-----\n", encoding="utf-8")
    (source / "secrets").mkdir()
    (source / "secrets" / "config.json").write_text('{"token":"ghp_live_secret_value"}\n', encoding="utf-8")
    target = WORKSPACE_ROOT / str(run.id)
    shutil.rmtree(target, ignore_errors=True)
    db = FakeDb(run=run, plan=plan)

    try:
        result = asyncio.run(
            ToolExecutor().execute(
                db,
                request=ToolCallRequest(
                    run_id=run.id,
                    state=AgentRunState.CREATE_BRANCH,
                    tool_name="workspace.create_run_copy",
                    actor="agent",
                    arguments={"run_id": str(run.id), "source_workspace": str(source)},
                ),
            )
        )

        assert result.status == "succeeded"
        assert (target / "app.py").is_file()
        assert not (target / ".env.local").exists()
        assert not (target / ".pypirc").exists()
        assert not (target / "private.pem").exists()
        assert not (target / "secrets").exists()
        baseline = target / ".repopilot" / "baseline.json"
        assert baseline.is_file()
        assert "sk-live-secret" not in baseline.read_text(encoding="utf-8")
    finally:
        shutil.rmtree(target, ignore_errors=True)


def test_executor_blocks_write_tool_without_approved_plan(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    run = AgentRun(id=uuid4(), state=AgentRunState.CREATE_BRANCH.value)
    db = FakeDb(run=run)

    result = asyncio.run(
        ToolExecutor().execute(
            db,
            request=ToolCallRequest(
                run_id=run.id,
                state=AgentRunState.CREATE_BRANCH,
                tool_name="workspace.write_file",
                actor="agent",
                arguments={"workspace_path": str(workspace), "path": "tests/test_demo.py", "content": "def test_ok(): pass\n"},
            ),
        )
    )

    assert result.status == "blocked"
    assert result.blocked_reason == "Tool requires an approved plan."
    assert result.block_type == ToolBlockType.APPROVAL_REQUIRED
    assert not (workspace / "tests" / "test_demo.py").exists()


def test_executor_blocks_write_tool_outside_isolated_workspace(tmp_path: Path) -> None:
    plan_id = uuid4()
    issue_id = uuid4()
    run = AgentRun(id=uuid4(), plan_id=plan_id, state=AgentRunState.CREATE_BRANCH.value)
    plan = Plan(
        id=plan_id,
        issue_id=issue_id,
        approval_status=PlanApprovalStatus.APPROVED.value,
        plan_json=approved_plan_payload(plan_id=plan_id, issue_id=issue_id, files_to_modify=["tests/test_demo.py"]),
    )
    workspace = tmp_path / "not-isolated"
    workspace.mkdir()
    db = FakeDb(run=run, plan=plan)

    result = asyncio.run(
        ToolExecutor().execute(
            db,
            request=ToolCallRequest(
                run_id=run.id,
                state=AgentRunState.CREATE_BRANCH,
                tool_name="workspace.write_file",
                actor="agent",
                arguments={"workspace_path": str(workspace), "path": "tests/test_demo.py", "content": "def test_ok(): pass\n"},
            ),
        )
    )

    assert result.status == "blocked"
    assert "isolated run workspace" in (result.blocked_reason or "")
    assert result.block_type == ToolBlockType.POLICY_DENIED
    assert not (workspace / "tests" / "test_demo.py").exists()


def test_executor_blocks_approved_plan_with_stale_hash(tmp_path: Path) -> None:
    plan_id = uuid4()
    issue_id = uuid4()
    run = AgentRun(id=uuid4(), plan_id=plan_id, state=AgentRunState.CREATE_BRANCH.value)
    payload = approved_plan_payload(plan_id=plan_id, issue_id=issue_id, files_to_modify=["tests/test_demo.py"])
    payload["files_to_modify"] = ["tests/changed_after_approval.py"]
    plan = Plan(
        id=plan_id,
        issue_id=issue_id,
        approval_status=PlanApprovalStatus.APPROVED.value,
        plan_json=payload,
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    db = FakeDb(run=run, plan=plan)

    result = asyncio.run(
        ToolExecutor().execute(
            db,
            request=ToolCallRequest(
                run_id=run.id,
                state=AgentRunState.CREATE_BRANCH,
                tool_name="workspace.write_file",
                actor="agent",
                arguments={"workspace_path": str(workspace), "path": "tests/test_demo.py", "content": "def test_ok(): pass\n"},
            ),
        )
    )

    assert result.status == "blocked"
    assert result.block_type == ToolBlockType.APPROVAL_REQUIRED
    assert result.blocked_reason == "Tool requires an approved plan."


def test_executor_blocks_workspace_write_to_unapproved_path() -> None:
    plan_id = uuid4()
    issue_id = uuid4()
    run = AgentRun(id=uuid4(), plan_id=plan_id, state=AgentRunState.CREATE_BRANCH.value)
    plan = Plan(
        id=plan_id,
        issue_id=issue_id,
        approval_status=PlanApprovalStatus.APPROVED.value,
        plan_json=approved_plan_payload(
            plan_id=plan_id,
            issue_id=issue_id,
            files_to_modify=["app/approved.py"],
            tests_to_add=["tests/"],
        ),
    )
    workspace = WORKSPACE_ROOT / str(run.id)
    shutil.rmtree(workspace, ignore_errors=True)
    workspace.mkdir(parents=True)
    db = FakeDb(run=run, plan=plan)

    try:
        result = asyncio.run(
            ToolExecutor().execute(
                db,
                request=ToolCallRequest(
                    run_id=run.id,
                    state=AgentRunState.CREATE_BRANCH,
                    tool_name="workspace.write_file",
                    actor="agent",
                    arguments={"workspace_path": str(workspace), "path": "app/not_approved.py", "content": "VALUE = 1\n"},
                ),
            )
        )
    finally:
        shutil.rmtree(workspace, ignore_errors=True)

    assert result.status == "blocked"
    assert result.block_type == ToolBlockType.POLICY_DENIED
    assert "not approved by the plan" in (result.blocked_reason or "")
    assert not (workspace / "app" / "not_approved.py").exists()


def test_executor_allows_workspace_write_under_approved_test_directory() -> None:
    plan_id = uuid4()
    issue_id = uuid4()
    run = AgentRun(id=uuid4(), plan_id=plan_id, state=AgentRunState.CREATE_BRANCH.value)
    plan = Plan(
        id=plan_id,
        issue_id=issue_id,
        approval_status=PlanApprovalStatus.APPROVED.value,
        plan_json=approved_plan_payload(
            plan_id=plan_id,
            issue_id=issue_id,
            files_to_modify=["apps/api/app/approved.py"],
            tests_to_add=["apps/api/tests/"],
        ),
    )
    workspace = WORKSPACE_ROOT / str(run.id)
    shutil.rmtree(workspace, ignore_errors=True)
    workspace.mkdir(parents=True)
    db = FakeDb(run=run, plan=plan)

    try:
        result = asyncio.run(
            ToolExecutor().execute(
                db,
                request=ToolCallRequest(
                    run_id=run.id,
                    state=AgentRunState.CREATE_BRANCH,
                    tool_name="workspace.write_file",
                    actor="agent",
                    arguments={"workspace_path": str(workspace), "path": "tests/test_approved.py", "content": "def test_ok():\n    assert True\n"},
                ),
            )
        )
        assert (workspace / "tests" / "test_approved.py").is_file()
    finally:
        shutil.rmtree(workspace, ignore_errors=True)

    assert result.status == "succeeded"
    assert result.output["path"] == "tests/test_approved.py"


def test_security_dependency_audit_adapter_skips_when_disabled(monkeypatch) -> None:
    monkeypatch.setattr(settings, "dependency_audit_enabled", False)
    plan_id = uuid4()
    issue_id = uuid4()
    run = AgentRun(id=uuid4(), plan_id=plan_id, state=AgentRunState.RUN_SECURITY_CHECKS.value)
    plan = Plan(
        id=plan_id,
        issue_id=issue_id,
        approval_status=PlanApprovalStatus.APPROVED.value,
        plan_json=approved_plan_payload(
            plan_id=plan_id,
            issue_id=issue_id,
            files_to_modify=["app/approved.py"],
            tests_to_add=["tests/"],
        ),
    )
    workspace = WORKSPACE_ROOT / str(run.id)
    shutil.rmtree(workspace, ignore_errors=True)
    workspace.mkdir(parents=True)
    (workspace / "package-lock.json").write_text("{}", encoding="utf-8")
    db = FakeDb(run=run, plan=plan)

    try:
        result = asyncio.run(
            ToolExecutor().execute(
                db,
                request=ToolCallRequest(
                    run_id=run.id,
                    state=AgentRunState.RUN_SECURITY_CHECKS,
                    tool_name="security.dependency_audit",
                    actor="agent",
                    arguments={"run_id": str(run.id), "workspace_path": str(workspace)},
                ),
            )
        )
    finally:
        shutil.rmtree(workspace, ignore_errors=True)

    assert result.status == "succeeded"
    assert result.output["adapter"] == "dependency_audit"
    assert result.output["status"] == "skipped"


def test_security_semgrep_adapter_fails_closed_when_enabled_but_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(settings, "semgrep_enabled", True)
    monkeypatch.setattr("app.services.tools.registry.shutil.which", lambda executable: None)
    plan_id = uuid4()
    issue_id = uuid4()
    run = AgentRun(id=uuid4(), plan_id=plan_id, state=AgentRunState.RUN_SECURITY_CHECKS.value)
    plan = Plan(
        id=plan_id,
        issue_id=issue_id,
        approval_status=PlanApprovalStatus.APPROVED.value,
        plan_json=approved_plan_payload(
            plan_id=plan_id,
            issue_id=issue_id,
            files_to_modify=["app/approved.py"],
            tests_to_add=["tests/"],
        ),
    )
    workspace = WORKSPACE_ROOT / str(run.id)
    shutil.rmtree(workspace, ignore_errors=True)
    workspace.mkdir(parents=True)
    db = FakeDb(run=run, plan=plan)

    try:
        result = asyncio.run(
            ToolExecutor().execute(
                db,
                request=ToolCallRequest(
                    run_id=run.id,
                    state=AgentRunState.RUN_SECURITY_CHECKS,
                    tool_name="security.semgrep",
                    actor="agent",
                    arguments={"run_id": str(run.id), "workspace_path": str(workspace)},
                ),
            )
        )
    finally:
        shutil.rmtree(workspace, ignore_errors=True)

    assert result.status == "succeeded"
    assert result.output["adapter"] == "semgrep"
    assert result.output["status"] == "failed"
    assert result.output["finding_count"] == 1
    assert any(getattr(item, "tool", "") == "semgrep" for item in db.added)


def test_security_dependency_audit_parses_npm_audit_json(monkeypatch) -> None:
    monkeypatch.setattr(settings, "dependency_audit_enabled", True)
    monkeypatch.setattr("app.services.tools.registry.shutil.which", lambda executable: f"/usr/bin/{executable}")

    def fake_run(*args, **kwargs):
        return SimpleNamespace(
            returncode=1,
            stdout='{"vulnerabilities":{"ansi-regex":{"severity":"high","via":[{"title":"ReDoS vulnerability"}]}}}',
            stderr="",
        )

    monkeypatch.setattr("app.services.tools.registry.subprocess.run", fake_run)
    plan_id = uuid4()
    issue_id = uuid4()
    run = AgentRun(id=uuid4(), plan_id=plan_id, state=AgentRunState.RUN_SECURITY_CHECKS.value)
    plan = Plan(
        id=plan_id,
        issue_id=issue_id,
        approval_status=PlanApprovalStatus.APPROVED.value,
        plan_json=approved_plan_payload(
            plan_id=plan_id,
            issue_id=issue_id,
            files_to_modify=["app/approved.py"],
            tests_to_add=["tests/"],
        ),
    )
    workspace = WORKSPACE_ROOT / str(run.id)
    shutil.rmtree(workspace, ignore_errors=True)
    workspace.mkdir(parents=True)
    (workspace / "package-lock.json").write_text("{}", encoding="utf-8")
    db = FakeDb(run=run, plan=plan)

    try:
        result = asyncio.run(
            ToolExecutor().execute(
                db,
                request=ToolCallRequest(
                    run_id=run.id,
                    state=AgentRunState.RUN_SECURITY_CHECKS,
                    tool_name="security.dependency_audit",
                    actor="agent",
                    arguments={"run_id": str(run.id), "workspace_path": str(workspace)},
                ),
            )
        )
    finally:
        shutil.rmtree(workspace, ignore_errors=True)

    assert result.status == "succeeded"
    assert result.output["adapter"] == "dependency_audit"
    assert result.output["status"] == "failed"
    assert result.output["finding_count"] == 1
    assert result.output["findings"][0]["severity"] == "high"
    assert any(getattr(item, "tool", "") == "dependency-audit" for item in db.added)
