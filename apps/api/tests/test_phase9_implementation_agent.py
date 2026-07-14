from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from uuid import uuid4

from repopilot_contracts import AgentRunState, ImplementationPlan, PlanApprovalStatus, ToolCallResult, ToolCallStatus

from app.core.config import settings
from app.db.models import AgentRun, ArtifactRecord, Issue, Plan
from app.services.implementation_agent import (
    ImplementationAgent,
    ImplementationExplorationPlan,
    ImplementationToolPlan,
    ProposedImplementationReadToolCall,
    ProposedImplementationToolCall,
)
from app.services.security_envelope import stable_json_hash
from app.services.tools.registry import WORKSPACE_ROOT


class FakeGateway:
    async def complete_json(self, *_args, **_kwargs):
        if _kwargs.get("response_model") is ImplementationExplorationPlan:
            return ImplementationExplorationPlan(summary="Initial plan context is sufficient.", ready_to_write=True)
        return ImplementationToolPlan(
            summary="Rename repository issue count field and add a regression test.",
            tool_calls=[
                ProposedImplementationToolCall(
                    tool_name="workspace.replace_text",
                    arguments={
                        "path": "apps/api/app/api/routes/repos.py",
                        "old_text": "return {'issue_count': 1}",
                        "new_text": "return {'open_issue_count': 1}",
                    },
                ),
                ProposedImplementationToolCall(
                    tool_name="workspace.write_file",
                    arguments={
                        "path": "apps/api/tests/test_repositories.py",
                        "content": (
                            "from app.api.routes.repos import list_repositories\n\n\n"
                            "def test_repository_count_field_is_open_issue_count():\n"
                            "    assert list_repositories()['open_issue_count'] == 1\n"
                        ),
                    },
                ),
            ],
        )


class FakeDb:
    def __init__(self, *, run: AgentRun, plan: Plan, issue: Issue) -> None:
        self.run = run
        self.plan = plan
        self.issue = issue
        self.added: list[object] = []
        self.commits = 0

    async def get(self, model, item_id):
        if model is AgentRun and self.run.id == item_id:
            return self.run
        if model is Plan and self.plan.id == item_id:
            return self.plan
        if model is Issue and self.issue.id == item_id:
            return self.issue
        return None

    def add(self, item: object) -> None:
        self.added.append(item)

    async def commit(self) -> None:
        self.commits += 1


def _approved_plan_payload(plan: ImplementationPlan) -> dict[str, object]:
    payload = plan.model_dump(mode="json")
    payload["approved_plan_hash"] = stable_json_hash(plan.model_dump(mode="json", exclude={"plan_hash"}))
    payload["plan_hash"] = payload["approved_plan_hash"]
    return payload


def test_implementation_agent_uses_tool_executor_for_source_and_test_patch(monkeypatch, tmp_path: Path) -> None:
    repository_root = tmp_path / "repositories"
    source = repository_root / "demo"
    route = source / "apps" / "api" / "app" / "api" / "routes" / "repos.py"
    route.parent.mkdir(parents=True)
    route.write_text("def list_repositories():\n    return {'issue_count': 1}\n", encoding="utf-8")
    (source / "apps" / "api" / "tests").mkdir()
    (source / "apps" / "api" / "requirements.txt").write_text("pytest\n", encoding="utf-8")

    monkeypatch.setattr(settings, "repository_workspace_root", str(repository_root))
    monkeypatch.setattr(settings, "sandbox_backend", "local")
    monkeypatch.setattr(settings, "environment", "local")
    monkeypatch.setattr(settings, "artifact_store_root", str(tmp_path / "artifacts"))

    plan_id = uuid4()
    issue_id = uuid4()
    run = AgentRun(id=uuid4(), issue_id=issue_id, plan_id=plan_id, state=AgentRunState.WAIT_FOR_APPROVAL.value)
    issue = Issue(id=issue_id, repository_id=uuid4(), number=22, title="Fix repository issue count display")
    implementation_plan = ImplementationPlan(
        plan_id=str(plan_id),
        issue_id=str(issue_id),
        files_to_inspect=["apps/api/app/api/routes/repos.py"],
        files_to_modify=["apps/api/app/api/routes/repos.py"],
        tests_to_add=["apps/api/tests/"],
        commands_to_run=["python3 -m pytest tests/test_repositories.py"],
        rollback_plan="Close the generated branch.",
    )
    plan = Plan(
        id=plan_id,
        issue_id=issue_id,
        approval_status=PlanApprovalStatus.APPROVED.value,
        plan_json=_approved_plan_payload(implementation_plan),
    )
    db = FakeDb(run=run, plan=plan, issue=issue)
    workspace = WORKSPACE_ROOT / str(run.id)
    shutil.rmtree(workspace, ignore_errors=True)

    try:
        result = asyncio.run(
            ImplementationAgent(model_gateway=FakeGateway()).execute(
                db,
                run_id=run.id,
                request=type(
                    "Request",
                    (),
                    {
                        "workspace_path": str(source),
                        "validation_command": "python3 -m pytest tests/test_repositories.py",
                        "timeout_seconds": 60,
                        "max_changed_files": 4,
                    },
                )(),
            )
        )
    finally:
        shutil.rmtree(workspace, ignore_errors=True)

    assert result.status == "passed"
    assert result.patch is not None
    assert result.patch.diff_uri and result.patch.diff_uri.startswith(f"local://artifacts/{run.id}/")
    assert result.patch.diff_artifact is not None
    assert {change.path for change in result.patch.changed_files} == {
        "apps/api/app/api/routes/repos.py",
        "apps/api/tests/test_repositories.py",
    }
    assert "open_issue_count" in result.patch.diff
    assert any(isinstance(item, ArtifactRecord) and item.artifact_type == "patch.diff" for item in db.added)
    assert "issue_count" in route.read_text(encoding="utf-8")
    assert run.state == AgentRunState.RUN_LOCAL_VALIDATION.value


def test_implementation_agent_blocks_when_model_returns_no_tool_calls(monkeypatch, tmp_path: Path) -> None:
    class EmptyGateway:
        async def complete_json(self, *_args, **_kwargs):
            if _kwargs.get("response_model") is ImplementationExplorationPlan:
                return ImplementationExplorationPlan(summary="No additional reads needed.", ready_to_write=True)
            return ImplementationToolPlan(
                summary="No patch.",
                tool_calls=[],
                stop_reason="No safe implementation path.",
            )

    repository_root = tmp_path / "repositories"
    source = repository_root / "demo"
    (source / "app").mkdir(parents=True)
    (source / "app" / "demo.py").write_text("VALUE = 1\n", encoding="utf-8")
    monkeypatch.setattr(settings, "repository_workspace_root", str(repository_root))

    plan_id = uuid4()
    issue_id = uuid4()
    run = AgentRun(id=uuid4(), issue_id=issue_id, plan_id=plan_id, state=AgentRunState.WAIT_FOR_APPROVAL.value)
    issue = Issue(id=issue_id, repository_id=uuid4(), number=23, title="Update demo")
    implementation_plan = ImplementationPlan(
        plan_id=str(plan_id),
        issue_id=str(issue_id),
        files_to_modify=["app/demo.py"],
        commands_to_run=["python -m pytest"],
        rollback_plan="Close the generated branch.",
    )
    plan = Plan(
        id=plan_id,
        issue_id=issue_id,
        approval_status=PlanApprovalStatus.APPROVED.value,
        plan_json=_approved_plan_payload(implementation_plan),
    )

    workspace = WORKSPACE_ROOT / str(run.id)
    shutil.rmtree(workspace, ignore_errors=True)
    try:
        result = asyncio.run(
            ImplementationAgent(model_gateway=EmptyGateway()).execute(
                FakeDb(run=run, plan=plan, issue=issue),
                run_id=run.id,
                request=type(
                    "Request",
                    (),
                    {
                        "workspace_path": str(source),
                        "validation_command": None,
                        "timeout_seconds": 60,
                        "max_changed_files": 4,
                    },
                )(),
            )
        )
    finally:
        shutil.rmtree(workspace, ignore_errors=True)

    assert result.status == "blocked"
    assert result.blocked_reason == "No safe implementation path."


def test_implementation_agent_uses_explicit_issue_body_fallback(monkeypatch, tmp_path: Path) -> None:
    class EmptyGateway:
        async def complete_json(self, *_args, **_kwargs):
            if _kwargs.get("response_model") is ImplementationExplorationPlan:
                return ImplementationExplorationPlan(summary="No additional reads needed.", ready_to_write=True)
            return ImplementationToolPlan(
                summary="No patch.",
                tool_calls=[],
                stop_reason="No safe implementation path.",
            )

    repository_root = tmp_path / "repositories"
    source = repository_root / "demo"
    source.mkdir(parents=True)
    (source / "smoke_app.py").write_text(
        'def smoke_message() -> str:\n    return "RepoPilot smoke pending"\n',
        encoding="utf-8",
    )
    tests = source / "tests"
    tests.mkdir()
    (tests / "test_smoke_app.py").write_text(
        'from smoke_app import smoke_message\n\n\n'
        "def test_smoke_message_mentions_repopilot():\n"
        '    assert "RepoPilot" in smoke_message()\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "repository_workspace_root", str(repository_root))
    monkeypatch.setattr(settings, "sandbox_backend", "local")
    monkeypatch.setattr(settings, "environment", "local")
    monkeypatch.setattr(settings, "artifact_store_root", str(tmp_path / "artifacts"))

    plan_id = uuid4()
    issue_id = uuid4()
    run = AgentRun(id=uuid4(), issue_id=issue_id, plan_id=plan_id, state=AgentRunState.WAIT_FOR_APPROVAL.value)
    issue = Issue(
        id=issue_id,
        repository_id=uuid4(),
        number=24,
        title="RepoPilot live write-mode smoke",
        body_text="Update smoke_app.py so smoke_message returns exactly RepoPilot live write smoke passed.",
    )
    implementation_plan = ImplementationPlan(
        plan_id=str(plan_id),
        issue_id=str(issue_id),
        files_to_inspect=["smoke_app.py", "tests/test_smoke_app.py"],
        files_to_modify=["smoke_app.py"],
        tests_to_add=["tests/test_smoke_app.py"],
        commands_to_run=["python -m pytest"],
        rollback_plan="Close the generated branch.",
    )
    plan = Plan(
        id=plan_id,
        issue_id=issue_id,
        approval_status=PlanApprovalStatus.APPROVED.value,
        plan_json=_approved_plan_payload(implementation_plan),
    )
    workspace = WORKSPACE_ROOT / str(run.id)
    shutil.rmtree(workspace, ignore_errors=True)
    try:
        result = asyncio.run(
            ImplementationAgent(model_gateway=EmptyGateway()).execute(
                FakeDb(run=run, plan=plan, issue=issue),
                run_id=run.id,
                request=type(
                    "Request",
                    (),
                    {
                        "workspace_path": str(source),
                        "validation_command": "python -m pytest",
                        "timeout_seconds": 60,
                        "max_changed_files": 2,
                    },
                )(),
            )
        )
    finally:
        shutil.rmtree(workspace, ignore_errors=True)

    assert result.status == "passed"
    assert result.patch is not None
    assert "RepoPilot live write smoke passed" in result.patch.diff
    assert source.joinpath("smoke_app.py").read_text(encoding="utf-8").count("pending") == 1


def test_implementation_agent_builds_scoped_markdown_section_note_fallback() -> None:
    issue = Issue(
        id=uuid4(),
        repository_id=uuid4(),
        number=25,
        title="Document isolated production web build",
        body_text=(
            "Update Docs/RUNBOOK.md only. In the Local Stack section, add a concise note that "
            "make web-build builds the production runner image without replacing the live development server's .next volume. "
            "Do not modify any other file."
        ),
    )
    plan = ImplementationPlan(
        plan_id=str(uuid4()),
        issue_id=str(issue.id),
        files_to_inspect=["Docs/RUNBOOK.md"],
        files_to_modify=["Docs/RUNBOOK.md"],
        commands_to_run=["python -m pytest -q apps/api/tests/test_release_targets.py"],
        rollback_plan="Close the generated branch.",
    )

    tool_plan = ImplementationAgent(model_gateway=FakeGateway())._deterministic_tool_plan(
        issue=issue,
        implementation_plan=plan,
        snippets=[
            {
                "path": "Docs/RUNBOOK.md",
                "content": "# Runbook\n\n## Local Stack\n\nRun `make start-local`.\n",
            }
        ],
    )

    assert tool_plan.summary == "Inserted an explicit documentation note in the requested approved section."
    assert len(tool_plan.tool_calls) == 1
    call = tool_plan.tool_calls[0]
    assert call.tool_name == "workspace.replace_text"
    assert call.arguments["path"] == "Docs/RUNBOOK.md"
    assert call.arguments["old_text"] == "## Local Stack"
    assert "make web-build builds the production runner image" in call.arguments["new_text"]


def test_implementation_agent_skips_apply_patch_diff_payload() -> None:
    captured: list[dict[str, object]] = []
    agent = ImplementationAgent(model_gateway=FakeGateway())
    run = AgentRun(id=uuid4(), state=AgentRunState.IMPLEMENT_PATCH.value)

    async def fake_execute_tool(*_args, **kwargs):
        captured.append({"tool_name": kwargs["tool_name"], "arguments": kwargs["arguments"]})
        return ToolCallResult(tool_name=kwargs["tool_name"], status=ToolCallStatus.SUCCEEDED, output={})

    agent._execute_tool = fake_execute_tool  # type: ignore[method-assign]

    asyncio.run(
        agent._execute_write_tool_calls(
            object(),
            run=run,
            workspace_path="/tmp/repopilot-agent-workspaces/demo",
            tool_plan=ImplementationToolPlan(
                summary="Apply patch.",
                tool_calls=[
                    ProposedImplementationToolCall(
                        tool_name="workspace.apply_patch",
                        arguments={"diff": "diff --git a/app.py b/app.py\n"},
                    )
                ],
            ),
            max_changed_files=4,
        )
    )

    assert captured == [
        {
            "tool_name": "workspace.apply_patch",
            "arguments": {
                "workspace_path": "/tmp/repopilot-agent-workspaces/demo",
                "diff": "diff --git a/app.py b/app.py\n",
                "max_changed_files": 4,
                "return_diff": False,
            },
        }
    ]


def test_implementation_agent_reads_context_with_batched_tool() -> None:
    captured: list[dict[str, object]] = []
    agent = ImplementationAgent(model_gateway=FakeGateway())
    run = AgentRun(id=uuid4(), state=AgentRunState.IMPLEMENT_PATCH.value)
    implementation_plan = ImplementationPlan(
        plan_id=str(uuid4()),
        issue_id=str(uuid4()),
        files_to_inspect=["apps/api/app/demo.py"],
        files_to_modify=["apps/api/app/demo.py", "apps/api/tests/test_demo.py"],
        tests_to_add=[],
        commands_to_run=["python -m pytest"],
        rollback_plan="Close the generated branch.",
    )

    async def fake_execute_tool(*_args, **kwargs):
        captured.append({"tool_name": kwargs["tool_name"], "arguments": kwargs["arguments"]})
        return ToolCallResult(
            tool_name=kwargs["tool_name"],
            status=ToolCallStatus.SUCCEEDED,
            output={
                "files": [
                    {"path": "apps/api/app/demo.py", "start_line": 1, "end_line": 1, "line_count": 1, "content": "VALUE = 1"}
                ],
                "errors": [],
            },
        )

    agent._execute_tool = fake_execute_tool  # type: ignore[method-assign]

    snippets = asyncio.run(
        agent._read_context_snippets(
            object(),
            run=run,
            workspace_path="/tmp/repopilot-agent-workspaces/demo",
            implementation_plan=implementation_plan,
        )
    )

    assert snippets == [{"path": "apps/api/app/demo.py", "start_line": 1, "end_line": 1, "line_count": 1, "content": "VALUE = 1"}]
    assert captured == [
        {
            "tool_name": "repo.read_files",
            "arguments": {
                "workspace_path": "/tmp/repopilot-agent-workspaces/demo",
                "files": [
                    {"path": "apps/api/app/demo.py", "start_line": 1, "end_line": 220},
                    {"path": "apps/api/tests/test_demo.py", "start_line": 1, "end_line": 220},
                ],
            },
        }
    ]


def test_implementation_agent_includes_retry_workspace_state_in_prompt() -> None:
    class PromptGateway:
        def __init__(self) -> None:
            self.user_prompt = ""

        async def complete_json(self, *_args, **kwargs):
            self.user_prompt = kwargs["user_prompt"]
            return ImplementationToolPlan(summary="Retry with fresh diff.", tool_calls=[])

    gateway = PromptGateway()
    agent = ImplementationAgent(model_gateway=gateway)
    run = AgentRun(id=uuid4(), state=AgentRunState.RUN_LOCAL_VALIDATION.value)
    issue = Issue(id=uuid4(), repository_id=uuid4(), number=24, title="Fix demo")
    implementation_plan = ImplementationPlan(
        plan_id=str(uuid4()),
        issue_id=str(issue.id),
        files_to_modify=["app/demo.py"],
        commands_to_run=["python -m pytest"],
        rollback_plan="Close the generated branch.",
    )

    asyncio.run(
        agent._propose_tool_plan(
            object(),
            run=run,
            issue=issue,
            implementation_plan=implementation_plan,
            workspace_path="/tmp/repopilot-agent-workspaces/demo",
            snippets=[{"path": "app/demo.py", "content": "VALUE = 1"}],
            exploration_observations=[],
            workspace_state={
                "diff_available": True,
                "changed_files": [{"path": "app/demo.py", "change_type": "modify", "additions": 1, "deletions": 1}],
                "changed_file_count": 1,
                "diff_excerpt": "@@ -1 +1 @@\n-VALUE = 1\n+VALUE = 2\n",
                "diff_truncated": False,
            },
            attempt=2,
            previous_validation=None,
            previous_tool_errors=[
                {
                    "tool_name": "workspace.apply_patch",
                    "status": "blocked",
                    "reason": "git apply failed: No valid patches in input",
                }
            ],
        )
    )

    prompt = json.loads(gateway.user_prompt)
    assert prompt["attempt"] == 2
    assert prompt["previous_tool_errors"][0]["tool_name"] == "workspace.apply_patch"
    assert "No valid patches" in prompt["previous_tool_errors"][0]["reason"]
    assert prompt["workspace_state"]["changed_files"][0]["path"] == "app/demo.py"
    assert "VALUE = 2" in prompt["workspace_state"]["diff_excerpt"]


def test_implementation_explorer_suppresses_repeated_read_calls(monkeypatch) -> None:
    class ExplorationGateway:
        def __init__(self) -> None:
            self.calls = 0

        async def complete_json(self, *_args, **_kwargs):
            self.calls += 1
            return ImplementationExplorationPlan(
                summary="Find the target symbol.",
                ready_to_write=self.calls > 1,
                tool_calls=[
                    ProposedImplementationReadToolCall(
                        tool_name="repo.grep",
                        arguments={"query": "target_symbol", "max_results": 5},
                    )
                ],
            )

    gateway = ExplorationGateway()
    agent = ImplementationAgent(model_gateway=gateway)
    run = AgentRun(id=uuid4(), state=AgentRunState.IMPLEMENT_PATCH.value)
    issue = Issue(id=uuid4(), repository_id=uuid4(), number=25, title="Update target symbol")
    implementation_plan = ImplementationPlan(
        plan_id=str(uuid4()),
        issue_id=str(issue.id),
        files_to_modify=["app/demo.py"],
        commands_to_run=["python -m pytest"],
        rollback_plan="Close the generated branch.",
    )
    executed: list[str] = []

    async def fake_execute_tool(*_args, **kwargs):
        executed.append(kwargs["tool_name"])
        return ToolCallResult(
            tool_name=kwargs["tool_name"],
            status=ToolCallStatus.SUCCEEDED,
            output={"query": "target_symbol", "matches": [{"path": "app/demo.py", "line": 3, "text": "target_symbol = 1"}]},
        )

    agent._execute_tool = fake_execute_tool  # type: ignore[method-assign]
    monkeypatch.setattr(settings, "implementation_exploration_max_rounds", 3)
    db = FakeDb(
        run=run,
        plan=Plan(id=uuid4(), issue_id=issue.id, plan_json={}),
        issue=issue,
    )

    observations, snippets = asyncio.run(
        agent._explore_context(
            db,
            run=run,
            issue=issue,
            implementation_plan=implementation_plan,
            workspace_path="/tmp/repopilot-agent-workspaces/demo",
            initial_snippets=[],
            attempt=1,
            previous_validation=None,
        )
    )

    assert gateway.calls == 2
    assert executed == ["repo.grep"]
    assert any(item["status"] == "blocked" for item in observations)
    assert snippets == []


def test_phase9_normalizes_pytest_validation_command() -> None:
    agent = ImplementationAgent(model_gateway=FakeGateway())

    assert agent._normalize_validation_command("pytest") == "python -m pytest"
    assert agent._normalize_validation_command("pytest tests") == "python -m pytest tests"
    assert agent._normalize_validation_command("python3 -m pytest tests") == "python -m pytest tests"
    assert agent._normalize_validation_command("npm test") == "npm test"
