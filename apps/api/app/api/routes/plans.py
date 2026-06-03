from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from repopilot_contracts import PlanApprovalStatus, PlanDetailResponse, PolicyDecision, PolicyDecisionType
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentRun, Plan, utc_now
from app.db.session import get_db
from app.services.audit import record_audit
from app.services.auth import CurrentUser, get_current_user, get_or_create_user
from app.services.authorization import require_plan_access
from app.services.planning import implementation_plan_from_db
from app.services.policy import PolicyEngine
from app.services.security_envelope import rate_limit, stable_json_hash

router = APIRouter()


class PlanDecisionRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)


class PlanRevisionRequest(BaseModel):
    instructions: str = Field(min_length=3, max_length=4000)


@router.post("/{plan_id}/approve", status_code=202)
async def approve_plan(
    plan_id: UUID,
    _rate_limit: None = Depends(rate_limit("plan-approval")),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, object]:
    plan = await require_plan_access(db, plan_id=plan_id, current_user=current_user, action="approve")

    implementation_plan = implementation_plan_from_db(plan)
    policy_decision = PolicyEngine().evaluate_plan(implementation_plan)
    if policy_decision.decision == PolicyDecisionType.DENY:
        raise HTTPException(status_code=409, detail=policy_decision.model_dump(mode="json"))
    if policy_decision.decision == PolicyDecisionType.ESCALATE and current_user.role not in {"owner", "maintainer"}:
        raise HTTPException(status_code=403, detail=policy_decision.model_dump(mode="json"))

    user = await get_or_create_user(db, current_user)
    approved_plan_hash = stable_json_hash(implementation_plan.model_dump(mode="json", exclude={"plan_hash"}))
    plan.approval_status = PlanApprovalStatus.APPROVED.value
    plan.approved_by = user.id
    plan.approved_at = utc_now()
    plan.plan_json = {
        **plan.plan_json,
        "plan_hash": approved_plan_hash,
        "approved_plan_hash": approved_plan_hash,
        "approval_policy_decision": policy_decision.model_dump(mode="json"),
    }
    await record_audit(
        db,
        actor_type="user",
        actor_id=current_user.username,
        action="plan.approved",
        entity_type="plan",
        entity_id=str(plan.id),
        metadata={"policy": policy_decision.decision.value, "approved_plan_hash": approved_plan_hash},
    )
    await db.commit()
    return {
        "status": "approved",
        "plan_id": str(plan.id),
        "approved_plan_hash": approved_plan_hash,
        "policy_decision": policy_decision.model_dump(mode="json"),
    }


@router.post("/{plan_id}/reject", status_code=202)
async def reject_plan(
    plan_id: UUID,
    request: PlanDecisionRequest,
    _rate_limit: None = Depends(rate_limit("plan-approval")),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, object]:
    plan = await require_plan_access(db, plan_id=plan_id, current_user=current_user, action="approve")
    plan.approval_status = PlanApprovalStatus.REJECTED.value
    plan.plan_json = {**plan.plan_json, "rejection_reason": request.reason}
    await record_audit(
        db,
        actor_type="user",
        actor_id=current_user.username,
        action="plan.rejected",
        entity_type="plan",
        entity_id=str(plan.id),
        metadata={"reason": request.reason},
    )
    await db.commit()
    return {"status": "rejected", "plan_id": str(plan.id), "reason": request.reason}


@router.post("/{plan_id}/revise", status_code=202)
async def revise_plan(
    plan_id: UUID,
    request: PlanRevisionRequest,
    _rate_limit: None = Depends(rate_limit("plan-approval")),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, object]:
    plan = await require_plan_access(db, plan_id=plan_id, current_user=current_user, action="approve")
    plan.approval_status = PlanApprovalStatus.REVISED.value
    plan.plan_json = {**plan.plan_json, "revision_instructions": request.instructions}
    revised_plan = Plan(
        issue_id=plan.issue_id,
        version=plan.version + 1,
        approval_status=PlanApprovalStatus.WAITING.value,
        plan_json={
            **plan.plan_json,
            "plan_id": "pending-db-id",
            "revision_parent_plan_id": str(plan.id),
            "revision_instructions": request.instructions,
        },
    )
    db.add(revised_plan)
    await db.flush()
    revised_plan.plan_json = {**revised_plan.plan_json, "plan_id": str(revised_plan.id)}
    rebound_runs = await _rebind_runs_to_revision(db, parent_plan_id=plan.id, revision_plan_id=revised_plan.id)
    await record_audit(
        db,
        actor_type="user",
        actor_id=current_user.username,
        action="plan.revision_requested",
        entity_type="plan",
        entity_id=str(plan.id),
        metadata={"new_plan_id": str(revised_plan.id), "instructions": request.instructions, "rebound_run_count": rebound_runs},
    )
    await db.commit()
    return {
        "status": "revision_requested",
        "plan_id": str(plan.id),
        "new_plan_id": str(revised_plan.id),
        "version": revised_plan.version,
        "instructions": request.instructions,
    }


@router.get("/{plan_id}", response_model=PlanDetailResponse)
async def read_plan(plan_id: UUID, db: AsyncSession = Depends(get_db)) -> dict[str, object]:
    plan = await db.get(Plan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    active_run_ids = await _run_ids_for_plan(db, plan_id=plan.id)
    return {
        "id": str(plan.id),
        "issue_id": str(plan.issue_id),
        "active_run_ids": active_run_ids,
        "approval_status": plan.approval_status,
        "approved_by": str(plan.approved_by) if plan.approved_by else None,
        "approved_at": plan.approved_at,
        "version": plan.version,
        "plan": plan.plan_json,
    }


@router.get("/{plan_id}/policy", response_model=PolicyDecision)
async def evaluate_plan_policy(plan_id: UUID, db: AsyncSession = Depends(get_db)) -> dict[str, object]:
    plan = await db.get(Plan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    decision = PolicyEngine().evaluate_plan(implementation_plan_from_db(plan))
    return decision.model_dump(mode="json")


async def _run_ids_for_plan(db: AsyncSession, *, plan_id: UUID) -> list[str]:
    result = await db.execute(select(AgentRun.id).where(AgentRun.plan_id == plan_id))
    return [str(run_id) for run_id in result.scalars().all()]


async def _rebind_runs_to_revision(db: AsyncSession, *, parent_plan_id: UUID, revision_plan_id: UUID) -> int:
    result = await db.execute(select(AgentRun).where(AgentRun.plan_id == parent_plan_id))
    runs = result.scalars().all()
    for run in runs:
        run.plan_id = revision_plan_id
    return len(runs)
