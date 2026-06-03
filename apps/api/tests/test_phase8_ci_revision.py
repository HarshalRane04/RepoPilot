from __future__ import annotations

import asyncio
from uuid import uuid4

from repopilot_contracts import AgentRunState, CIAnalysisRequest, ImplementationPlan

from app.db.models import AgentRun, AgentStep, Plan, PullRequest
from app.services.ci_analyzer import CIAnalyzer
from app.services.revision_planner import RevisionPlanner


class ScalarResult:
    def __init__(self, items):
        self.items = items

    def scalars(self):
        return self

    def all(self):
        return self.items

    def first(self):
        return self.items[0] if self.items else None


class FakeDb:
    def __init__(self, *, run: AgentRun, pr: PullRequest, plan: Plan, steps: list[AgentStep] | None = None) -> None:
        self.run = run
        self.pr = pr
        self.plan = plan
        self.steps = steps or []
        self.added: list[object] = []
        self.commits = 0
        self.flushes = 0

    async def get(self, model, item_id):
        if model is PullRequest and self.pr.id == item_id:
            return self.pr
        if model is AgentRun and self.run.id == item_id:
            return self.run
        if model is Plan and self.plan.id == item_id:
            return self.plan
        return None

    async def execute(self, _statement):
        return ScalarResult(self.steps)

    def add(self, item):
        if isinstance(item, AgentStep):
            self.steps.append(item)
        self.added.append(item)

    async def flush(self):
        self.flushes += 1
        for item in self.added:
            if getattr(item, "id", None) is None:
                item.id = uuid4()

    async def commit(self):
        self.commits += 1


def _plan_payload(plan_id: str, issue_id: str) -> dict[str, object]:
    return ImplementationPlan(
        plan_id=plan_id,
        issue_id=issue_id,
        files_to_modify=["app/demo.py"],
        tests_to_add=["tests/test_demo.py"],
        commands_to_run=["python -m pytest"],
        rollback_plan="Close the generated branch.",
    ).model_dump(mode="json")


def test_ci_analyzer_extracts_failure_context() -> None:
    analyzer = CIAnalyzer()
    log_text = "Job: test\nRun python -m pytest\nERROR tests/test_demo.py::test_demo failed\n"

    assert analyzer.failed_job(workflow_name="ci", log_text=log_text) == "test"
    assert analyzer.failing_command(log_text) == "python -m pytest"
    assert analyzer.proposed_fix_path(log_text) == "tests/test_demo.py"
    assert analyzer.failure_reasons(log_text) == ["ERROR tests/test_demo.py::test_demo failed"]


def test_revision_planner_creates_fresh_waiting_plan_from_ci_failure() -> None:
    plan_id = uuid4()
    issue_id = uuid4()
    run = AgentRun(id=uuid4(), issue_id=issue_id, plan_id=plan_id, state=AgentRunState.WAIT_FOR_CI.value)
    pr = PullRequest(id=uuid4(), run_id=run.id, pr_number=12, url="local://pr/12", status="draft")
    plan = Plan(id=plan_id, issue_id=issue_id, version=2, plan_json=_plan_payload(str(plan_id), str(issue_id)))
    ci_step = AgentStep(
        run_id=run.id,
        step_name=AgentRunState.WAIT_FOR_CI.value,
        output_json={
            "root_cause": "ERROR tests/test_demo.py::test_demo failed",
            "proposed_fix_path": "tests/test_demo.py",
        },
    )
    db = FakeDb(run=run, pr=pr, plan=plan, steps=[ci_step])

    revision = asyncio.run(
        RevisionPlanner().create_revision_plan(
            db,
            pr_id=pr.id,
            instructions="Fix the regression and rerun validation.",
            actor_id="owner",
        )
    )

    assert revision.approval_status == "waiting"
    assert revision.version == 3
    assert revision.plan_json["revision_parent_plan_id"] == str(plan.id)
    assert revision.plan_json["revision_instructions"] == "Fix the regression and rerun validation."
    assert revision.plan_json["files_to_modify"] == ["tests/test_demo.py"]
    assert run.plan_id == revision.id
    assert db.commits == 1


def test_ci_analyzer_returns_revision_fields_without_db() -> None:
    analyzer = CIAnalyzer()
    request = CIAnalysisRequest(
        workflow_name="ci",
        conclusion="failure",
        log_text="Job: test\nRun python -m pytest\nERROR app/demo.py failed\n",
    )

    assert analyzer.summary(conclusion=request.conclusion, failure_reasons=analyzer.failure_reasons(request.log_text)).startswith(
        "CI concluded failure"
    )
