from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from repopilot_contracts import AgentRunState
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentRun, AgentStep
from app.services.audit import record_audit


TERMINAL_STATES = {
    AgentRunState.REJECTED.value,
    AgentRunState.CANCELLED.value,
    AgentRunState.FAILED.value,
    AgentRunState.MERGED_OR_CLOSED.value,
}

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    AgentRunState.NEW_EVENT.value: {AgentRunState.VALIDATE_WEBHOOK.value, AgentRunState.FAILED.value},
    AgentRunState.VALIDATE_WEBHOOK.value: {AgentRunState.NORMALIZE_EVENT.value, AgentRunState.FAILED.value},
    AgentRunState.NORMALIZE_EVENT.value: {AgentRunState.TRIAGE_ISSUE.value, AgentRunState.FAILED.value},
    AgentRunState.TRIAGE_ISSUE.value: {
        AgentRunState.NEEDS_INFO.value,
        AgentRunState.RETRIEVE_CONTEXT.value,
        AgentRunState.POLICY_REVIEW_PLAN.value,
        AgentRunState.WAIT_FOR_APPROVAL.value,
        AgentRunState.REJECTED.value,
        AgentRunState.FAILED.value,
    },
    AgentRunState.NEEDS_INFO.value: {AgentRunState.TRIAGE_ISSUE.value, AgentRunState.CANCELLED.value},
    AgentRunState.RETRIEVE_CONTEXT.value: {AgentRunState.GENERATE_PLAN.value, AgentRunState.FAILED.value},
    AgentRunState.GENERATE_PLAN.value: {AgentRunState.POLICY_REVIEW_PLAN.value, AgentRunState.FAILED.value},
    AgentRunState.POLICY_REVIEW_PLAN.value: {
        AgentRunState.WAIT_FOR_APPROVAL.value,
        AgentRunState.REJECTED.value,
        AgentRunState.FAILED.value,
    },
    AgentRunState.WAIT_FOR_APPROVAL.value: {
        AgentRunState.CREATE_BRANCH.value,
        AgentRunState.REJECTED.value,
        AgentRunState.CANCELLED.value,
    },
    AgentRunState.CREATE_BRANCH.value: {
        AgentRunState.IMPLEMENT_PATCH.value,
        AgentRunState.FAILED.value,
        AgentRunState.CANCELLED.value,
    },
    AgentRunState.IMPLEMENT_PATCH.value: {
        AgentRunState.GENERATE_TESTS.value,
        AgentRunState.FAILED.value,
        AgentRunState.CANCELLED.value,
    },
    AgentRunState.GENERATE_TESTS.value: {
        AgentRunState.RUN_LOCAL_VALIDATION.value,
        AgentRunState.FAILED.value,
        AgentRunState.CANCELLED.value,
    },
    AgentRunState.RUN_LOCAL_VALIDATION.value: {
        AgentRunState.RUN_SECURITY_CHECKS.value,
        AgentRunState.FAILED.value,
        AgentRunState.CANCELLED.value,
    },
    AgentRunState.RUN_SECURITY_CHECKS.value: {
        AgentRunState.OPEN_DRAFT_PR.value,
        AgentRunState.FAILED.value,
        AgentRunState.CANCELLED.value,
    },
    AgentRunState.OPEN_DRAFT_PR.value: {
        AgentRunState.WAIT_FOR_CI.value,
        AgentRunState.FAILED.value,
        AgentRunState.CANCELLED.value,
    },
    AgentRunState.WAIT_FOR_CI.value: {
        AgentRunState.READY_FOR_REVIEW.value,
        AgentRunState.FAILED.value,
        AgentRunState.CANCELLED.value,
    },
    AgentRunState.READY_FOR_REVIEW.value: {
        AgentRunState.MERGED_OR_CLOSED.value,
        AgentRunState.CANCELLED.value,
    },
}


class InvalidStateTransition(ValueError):
    pass


def can_transition(current_state: str, next_state: str) -> bool:
    if current_state == next_state:
        return True
    if current_state in TERMINAL_STATES:
        return False
    return next_state in ALLOWED_TRANSITIONS.get(current_state, set())


def next_states(current_state: str) -> list[str]:
    return sorted(ALLOWED_TRANSITIONS.get(current_state, set()))


async def transition_run(
    db: AsyncSession,
    *,
    run: AgentRun,
    next_state: AgentRunState | str,
    actor_type: str = "system",
    actor_id: str | None = None,
    reason: str,
    metadata: dict[str, Any] | None = None,
    allowed_from: Iterable[str] | None = None,
) -> None:
    target = next_state.value if isinstance(next_state, AgentRunState) else next_state
    current = run.state
    allowed = set(allowed_from or ())
    if allowed and current in allowed:
        pass
    elif not can_transition(current, target):
        raise InvalidStateTransition(f"Invalid agent run transition: {current} -> {target}")

    run.state = target
    transition_metadata = {
        "from_state": current,
        "to_state": target,
        "reason": reason,
        **(metadata or {}),
    }
    db.add(
        AgentStep(
            run_id=run.id,
            step_name=target,
            output_json=transition_metadata,
            status="succeeded",
        )
    )
    await record_audit(
        db,
        actor_type=actor_type,
        actor_id=actor_id,
        action="run.transitioned",
        entity_type="agent_run",
        entity_id=str(run.id),
        metadata=transition_metadata,
    )
