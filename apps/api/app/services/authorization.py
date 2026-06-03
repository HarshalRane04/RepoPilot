from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentRun, Issue, Plan, PullRequest, Repository, SecurityFinding
from app.services.auth import CurrentUser

ROLE_LEVELS = {
    "viewer": 0,
    "read": 0,
    "triage": 1,
    "write": 2,
    "maintainer": 3,
    "admin": 4,
    "owner": 5,
}

ACTION_MIN_ROLE = {
    "read": "viewer",
    "triage": "triage",
    "write": "write",
    "approve": "write",
    "escalated_approve": "maintainer",
    "admin": "admin",
}


def require_role(current_user: CurrentUser, minimum_role: str) -> None:
    required = ROLE_LEVELS.get(minimum_role, ROLE_LEVELS["owner"])
    actual = ROLE_LEVELS.get(current_user.role, -1)
    if actual < required:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{current_user.role}' cannot perform actions requiring '{minimum_role}'.",
        )


async def require_repository_access(
    db: AsyncSession,
    *,
    repository_id: UUID,
    current_user: CurrentUser,
    action: str = "read",
) -> Repository:
    require_role(current_user, ACTION_MIN_ROLE.get(action, "owner"))
    repository = await db.get(Repository, repository_id)
    if repository is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")
    return repository


async def require_issue_access(
    db: AsyncSession,
    *,
    issue_id: UUID,
    current_user: CurrentUser,
    action: str = "read",
) -> Issue:
    issue = await db.get(Issue, issue_id)
    if issue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")
    await require_repository_access(db, repository_id=issue.repository_id, current_user=current_user, action=action)
    return issue


async def require_plan_access(
    db: AsyncSession,
    *,
    plan_id: UUID,
    current_user: CurrentUser,
    action: str = "read",
) -> Plan:
    plan = await db.get(Plan, plan_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    await require_issue_access(db, issue_id=plan.issue_id, current_user=current_user, action=action)
    return plan


async def require_run_access(
    db: AsyncSession,
    *,
    run_id: UUID,
    current_user: CurrentUser,
    action: str = "read",
) -> AgentRun:
    require_role(current_user, ACTION_MIN_ROLE.get(action, "owner"))
    run = await db.get(AgentRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent run not found")
    if run.issue_id is not None:
        await require_issue_access(db, issue_id=run.issue_id, current_user=current_user, action=action)
    return run


async def require_pr_access(
    db: AsyncSession,
    *,
    pr_id: UUID,
    current_user: CurrentUser,
    action: str = "read",
) -> PullRequest:
    pr = await db.get(PullRequest, pr_id)
    if pr is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pull request not found")
    await require_run_access(db, run_id=pr.run_id, current_user=current_user, action=action)
    return pr


async def require_security_finding_access(
    db: AsyncSession,
    *,
    finding_id: UUID,
    current_user: CurrentUser,
    action: str = "read",
) -> SecurityFinding:
    finding = await db.get(SecurityFinding, finding_id)
    if finding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Security finding not found")
    await require_run_access(db, run_id=finding.run_id, current_user=current_user, action=action)
    return finding
