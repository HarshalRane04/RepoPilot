from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.db.models import AgentRun, Installation, Issue, Plan, Repository
from app.services.auth import CurrentUser
from app.services.authorization import require_issue_access, require_plan_access, require_role, require_run_access


class FakeAuthorizationDb:
    def __init__(self, *, repository: Repository, issue: Issue, plan: Plan, run: AgentRun) -> None:
        self.repository = repository
        self.issue = issue
        self.plan = plan
        self.run = run

    async def get(self, model, item_id):
        if model is Repository and item_id == self.repository.id:
            return self.repository
        if model is Issue and item_id == self.issue.id:
            return self.issue
        if model is Plan and item_id == self.plan.id:
            return self.plan
        if model is AgentRun and item_id == self.run.id:
            return self.run
        return None


def fake_authorization_db() -> tuple[FakeAuthorizationDb, Issue, Plan, AgentRun]:
    installation = Installation(id=uuid4(), github_installation_id="1", account_name="octo")
    repository = Repository(id=uuid4(), installation_id=installation.id, owner="octo", name="demo")
    issue = Issue(id=uuid4(), repository_id=repository.id, number=1, title="Fix bug")
    run = AgentRun(id=uuid4(), issue_id=issue.id, state="WAIT_FOR_APPROVAL")
    plan = Plan(id=uuid4(), issue_id=issue.id, plan_json={"rollback_plan": "Close the PR."})
    return FakeAuthorizationDb(repository=repository, issue=issue, plan=plan, run=run), issue, plan, run


def test_require_role_blocks_insufficient_role() -> None:
    with pytest.raises(HTTPException) as exc:
        require_role(CurrentUser(username="reader", role="viewer"), "write")

    assert exc.value.status_code == 403


def test_object_authorization_resolves_related_resources() -> None:
    db, issue, plan, run = fake_authorization_db()
    user = CurrentUser(username="dev", role="write")

    resolved_issue = asyncio.run(require_issue_access(db, issue_id=issue.id, current_user=user, action="write"))
    resolved_plan = asyncio.run(require_plan_access(db, plan_id=plan.id, current_user=user, action="approve"))
    resolved_run = asyncio.run(require_run_access(db, run_id=run.id, current_user=user, action="write"))

    assert resolved_issue.id == issue.id
    assert resolved_plan.id == plan.id
    assert resolved_run.id == run.id


def test_object_authorization_returns_404_for_missing_object() -> None:
    db, _issue, _plan, _run = fake_authorization_db()
    user = CurrentUser(username="dev", role="owner")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(require_plan_access(db, plan_id=uuid4(), current_user=user, action="read"))

    assert exc.value.status_code == 404
