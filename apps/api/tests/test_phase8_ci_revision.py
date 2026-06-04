from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from repopilot_contracts import AgentRunState, CIAnalysisRequest, ImplementationPlan

from app.db.models import AgentRun, AgentStep, Plan, PullRequest
from app.services.ci_analyzer import CIAnalyzer
from app.services.ci_metrics import CIMetricsCalculator
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


def test_ci_metrics_track_first_run_and_revision_passes() -> None:
    issue_a = uuid4()
    issue_b = uuid4()
    issue_c = uuid4()
    parent_plan_b = uuid4()
    revision_plan_b = uuid4()
    run_a = AgentRun(id=uuid4(), issue_id=issue_a, plan_id=uuid4(), state=AgentRunState.READY_FOR_REVIEW.value)
    run_b = AgentRun(id=uuid4(), issue_id=issue_b, plan_id=revision_plan_b, state=AgentRunState.READY_FOR_REVIEW.value)
    run_c = AgentRun(id=uuid4(), issue_id=issue_c, plan_id=uuid4(), state=AgentRunState.WAIT_FOR_CI.value)
    run_without_ci = AgentRun(id=uuid4(), issue_id=uuid4(), plan_id=uuid4(), state=AgentRunState.WAIT_FOR_CI.value)
    prs = [
        PullRequest(id=uuid4(), run_id=run_a.id, pr_number=1, url="local://pr/1", status="ready_for_review", ci_status="success"),
        PullRequest(id=uuid4(), run_id=run_b.id, pr_number=2, url="local://pr/2", status="ready_for_review", ci_status="success"),
        PullRequest(id=uuid4(), run_id=run_c.id, pr_number=3, url="local://pr/3", status="draft", ci_status="failure"),
        PullRequest(id=uuid4(), run_id=run_without_ci.id, pr_number=4, url="local://pr/4", status="draft"),
    ]
    plans = [
        Plan(id=parent_plan_b, issue_id=issue_b, version=1, approval_status="approved", plan_json={"plan_id": str(parent_plan_b)}),
        Plan(
            id=revision_plan_b,
            issue_id=issue_b,
            version=2,
            approval_status="waiting",
            plan_json={"plan_id": str(revision_plan_b), "revision_parent_plan_id": str(parent_plan_b)},
        ),
    ]
    steps = [
        AgentStep(
            run_id=run_b.id,
            step_name=AgentRunState.WAIT_FOR_CI.value,
            output_json={"conclusion": "failure"},
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        AgentStep(
            run_id=run_b.id,
            step_name=AgentRunState.WAIT_FOR_CI.value,
            output_json={"conclusion": "success"},
            created_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
        AgentStep(
            run_id=run_c.id,
            step_name=AgentRunState.WAIT_FOR_CI.value,
            output_json={"conclusion": "failure"},
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        ),
    ]

    metrics = CIMetricsCalculator().calculate(
        pull_requests=prs,
        runs=[run_a, run_b, run_c, run_without_ci],
        plans=plans,
        steps=steps,
    )

    assert metrics.ci_total_prs == 3
    assert metrics.ci_successful_prs == 2
    assert metrics.ci_failed_prs == 1
    assert metrics.ci_pass_rate == 0.6667
    assert metrics.ci_first_run_pass_count == 1
    assert metrics.ci_first_run_ci_pass_rate == 0.3333
    assert metrics.ci_revision_fixup_attempts == 1
    assert metrics.ci_revised_pr_count == 1
    assert metrics.ci_pass_after_revision_count == 1
    assert metrics.ci_pass_after_revision_rate == 1.0
