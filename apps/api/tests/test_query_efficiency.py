from __future__ import annotations

import asyncio
from uuid import uuid4

from app.api.routes.prs import list_pull_requests
from app.api.routes.runs import list_runs
from app.api.routes.security import list_security_findings
from app.db.models import AgentRun, AgentStep, Issue, Plan, PullRequest, Repository, SecurityFinding
from app.services.auth import CurrentUser


class Result:
    def __init__(self, items):
        self.items = items

    def scalars(self):
        return self

    def all(self):
        return self.items


class SequenceDb:
    def __init__(self, results):
        self.results = list(results)
        self.execute_count = 0

    async def execute(self, _statement):
        self.execute_count += 1
        return Result(self.results.pop(0))


def _graph():
    repository = Repository(id=uuid4(), installation_id=uuid4(), owner="octo", name="demo", default_branch="main")
    issue = Issue(id=uuid4(), repository_id=repository.id, number=1, title="Fix bug", status="in_progress")
    plan = Plan(id=uuid4(), issue_id=issue.id, plan_json={}, approval_status="approved")
    run = AgentRun(id=uuid4(), issue_id=issue.id, plan_id=plan.id, state="WAIT_FOR_CI")
    pr = PullRequest(
        id=uuid4(), run_id=run.id, repository_id=repository.id, pr_number=7,
        url="local://pull-requests/7", status="draft", risk_score=10,
    )
    finding = SecurityFinding(
        id=uuid4(), run_id=run.id, tool="secret-scan", severity="high", description="finding", status="open",
    )
    open_step = AgentStep(run_id=run.id, step_name="OPEN_DRAFT_PR", output_json={"mode": "local_record"}, status="succeeded")
    return repository, issue, plan, run, pr, finding, open_step


def test_pull_request_list_uses_fixed_query_count() -> None:
    repository, issue, plan, run, pr, finding, open_step = _graph()
    db = SequenceDb([[pr], [run], [issue], [repository], [plan], [], [finding], [open_step]])

    result = asyncio.run(
        list_pull_requests(limit=100, current_user=CurrentUser(username="viewer", role="viewer"), db=db)
    )

    assert result[0]["pr_number"] == 7
    assert db.execute_count == 8


def test_security_finding_list_uses_fixed_query_count() -> None:
    repository, issue, _plan, run, pr, finding, open_step = _graph()
    db = SequenceDb([[finding], [run], [issue], [repository], [pr], [open_step]])

    result = asyncio.run(
        list_security_findings(limit=100, current_user=CurrentUser(username="viewer", role="viewer"), db=db)
    )

    assert result[0]["pull_request"]["number"] == 7
    assert db.execute_count == 6


def test_run_list_uses_fixed_query_count() -> None:
    _repository, _issue, _plan, run, _pr, _finding, open_step = _graph()
    db = SequenceDb([[run], [open_step], []])

    result = asyncio.run(list_runs(limit=50, current_user=CurrentUser(username="viewer", role="viewer"), db=db))

    assert result[0]["id"] == str(run.id)
    assert db.execute_count == 3
