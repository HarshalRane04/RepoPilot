from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from repopilot_contracts import PlanApprovalStatus, PlanDetailResponse, PolicyDecision, PolicyDecisionType
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentRun, Issue, Plan, utc_now
from app.db.session import get_db
from app.services.audit import record_audit
from app.services.auth import CurrentUser, get_current_user, get_or_create_user
from app.services.authorization import require_plan_access
from app.services.planning import PlanningService, implementation_plan_from_db
from app.services.policy import PolicyEngine
from app.services.security_envelope import free_form_text_metadata, rate_limit, stable_json_hash
from app.services.state_machine import transition_run

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
        metadata={"reason": free_form_text_metadata(request.reason)},
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
    issue = await db.get(Issue, plan.issue_id)
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found for plan")
    parent_implementation_plan = implementation_plan_from_db(plan)
    revised_implementation_plan = PlanningService().revise_plan(
        issue=issue,
        parent_plan=parent_implementation_plan,
        instructions=request.instructions,
    )
    policy_decision = PolicyEngine().evaluate_plan(revised_implementation_plan)
    plan.approval_status = PlanApprovalStatus.REVISED.value
    plan.plan_json = {**plan.plan_json, "revision_instructions": request.instructions}
    revised_plan = Plan(
        issue_id=plan.issue_id,
        version=plan.version + 1,
        approval_status=PlanApprovalStatus.WAITING.value,
        plan_json={
            **revised_implementation_plan.model_dump(mode="json"),
            "plan_id": "pending-db-id",
            "context": plan.plan_json.get("context", {}),
            "policy_decision": policy_decision.model_dump(mode="json"),
            "revision_parent_plan_id": str(plan.id),
            "revision_instructions": request.instructions,
        },
    )
    db.add(revised_plan)
    await db.flush()
    revised_plan.plan_json = {**revised_plan.plan_json, "plan_id": str(revised_plan.id)}
    superseded_runs = await _supersede_waiting_runs(db, parent_plan_id=plan.id, actor_id=current_user.username)
    revised_run = AgentRun(
        issue_id=plan.issue_id,
        plan_id=revised_plan.id,
        state="WAIT_FOR_APPROVAL",
    )
    db.add(revised_run)
    await db.flush()
    revised_plan.plan_json = {**revised_plan.plan_json, "revision_run_id": str(revised_run.id)}
    await record_audit(
        db,
        actor_type="user",
        actor_id=current_user.username,
        action="plan.revision_requested",
        entity_type="plan",
        entity_id=str(plan.id),
        metadata={
            "new_plan_id": str(revised_plan.id),
            "new_run_id": str(revised_run.id),
            "instructions": free_form_text_metadata(request.instructions),
            "superseded_run_count": superseded_runs,
        },
    )
    await db.commit()
    return {
        "status": "revision_requested",
        "plan_id": str(plan.id),
        "new_plan_id": str(revised_plan.id),
        "run_id": str(revised_run.id),
        "version": revised_plan.version,
        "instructions": request.instructions,
    }


@router.get("/{plan_id}", response_model=PlanDetailResponse)
async def read_plan(
    plan_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    plan = await require_plan_access(db, plan_id=plan_id, current_user=current_user, action="read")
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
async def evaluate_plan_policy(
    plan_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    plan = await require_plan_access(db, plan_id=plan_id, current_user=current_user, action="read")
    decision = PolicyEngine().evaluate_plan(implementation_plan_from_db(plan))
    return decision.model_dump(mode="json")


async def _run_ids_for_plan(db: AsyncSession, *, plan_id: UUID) -> list[str]:
    result = await db.execute(select(AgentRun.id).where(AgentRun.plan_id == plan_id))
    return [str(run_id) for run_id in result.scalars().all()]


async def _supersede_waiting_runs(db: AsyncSession, *, parent_plan_id: UUID, actor_id: str) -> int:
    result = await db.execute(select(AgentRun).where(AgentRun.plan_id == parent_plan_id))
    runs = result.scalars().all()
    superseded = 0
    for run in runs:
        if run.state != "WAIT_FOR_APPROVAL":
            continue
        await transition_run(
            db,
            run=run,
            next_state="CANCELLED",
            actor_type="user",
            actor_id=actor_id,
            reason="The plan was superseded by a human-requested revision.",
            metadata={"parent_plan_id": str(parent_plan_id)},
        )
        superseded += 1
    return superseded
