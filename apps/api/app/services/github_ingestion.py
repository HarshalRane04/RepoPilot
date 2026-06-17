from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from uuid import UUID

from repopilot_contracts import AgentRunState, PlanApprovalStatus, PolicyDecisionType
from repopilot_contracts import CIAnalysisRequest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import AgentRun, AgentStep, GitHubEvent, Installation, Issue, Plan, PullRequest, Repository, utc_now
from app.services.audit import record_audit
from app.services.ci_analyzer import CIAnalyzer
from app.services.github_webhooks import (
    GitHubEventNormalizer,
    NormalizedIssueCommentCommand,
    NormalizedIssueEvent,
    NormalizedWorkflowRunEvent,
    UnsupportedGitHubEvent,
)
from app.services.github_permissions import GitHubPermissionService
from app.services.planning import implementation_plan_from_db
from app.services.policy import PolicyEngine
from app.services.runtime_secrets import effective_settings
from app.services.security_envelope import redact_text, stable_json_hash
from app.services.state_machine import InvalidStateTransition, transition_run
from app.services.triage import TriageService


class DuplicateDelivery(Exception):
    def __init__(self, event: GitHubEvent) -> None:
        super().__init__(f"Duplicate GitHub delivery: {event.delivery_id}")
        self.event = event


async def store_webhook_event(
    db: AsyncSession,
    *,
    delivery_id: str,
    event_type: str,
    payload: dict,
) -> GitHubEvent:
    existing = await db.scalar(select(GitHubEvent).where(GitHubEvent.delivery_id == delivery_id))
    if existing is not None:
        raise DuplicateDelivery(existing)

    stored_payload = _minimized_webhook_payload(event_type=event_type, payload=payload)
    event = GitHubEvent(
        delivery_id=delivery_id,
        event_type=event_type,
        payload_json=stored_payload,
        status="received",
    )
    db.add(event)
    await db.flush()
    await record_audit(
        db,
        actor_type="github",
        actor_id=payload.get("sender", {}).get("login"),
        action="webhook.received",
        entity_type="github_event",
        entity_id=str(event.id),
        metadata={"event_type": event_type, "delivery_id": delivery_id},
    )
    return event


def _minimized_webhook_payload(*, event_type: str, payload: dict) -> dict[str, object]:
    repository = payload.get("repository") if isinstance(payload.get("repository"), dict) else {}
    owner = repository.get("owner") if isinstance(repository.get("owner"), dict) else {}
    installation = payload.get("installation") if isinstance(payload.get("installation"), dict) else {}
    sender = payload.get("sender") if isinstance(payload.get("sender"), dict) else {}
    base: dict[str, object] = {
        "action": payload.get("action"),
        "installation": _compact_dict(installation, {"id"}),
        "repository": {
            "name": repository.get("name"),
            "default_branch": repository.get("default_branch"),
            "owner": _compact_dict(owner, {"login"}),
        },
        "sender": _compact_dict(sender, {"login"}),
        "_repopilot": {
            "retention": "minimized_redacted",
            "raw_payload_sha256": _payload_hash(payload),
        },
    }
    if event_type in {"issues", "issue_comment"}:
        issue = payload.get("issue") if isinstance(payload.get("issue"), dict) else {}
        base["issue"] = {
            "number": issue.get("number"),
            "title": redact_text(str(issue.get("title") or "")),
            "body": redact_text(str(issue.get("body") or "")),
            "html_url": issue.get("html_url"),
        }
    if event_type == "issue_comment":
        comment = payload.get("comment") if isinstance(payload.get("comment"), dict) else {}
        base["comment"] = {
            "body": redact_text(str(comment.get("body") or "")),
            "html_url": comment.get("html_url"),
        }
    if event_type == "workflow_run":
        workflow_run = payload.get("workflow_run") if isinstance(payload.get("workflow_run"), dict) else {}
        base["workflow_run"] = {
            "name": workflow_run.get("name"),
            "conclusion": workflow_run.get("conclusion"),
            "pull_requests": _pull_request_numbers(workflow_run.get("pull_requests")),
            "display_title": redact_text(str(workflow_run.get("display_title") or "")),
            "html_url": workflow_run.get("html_url"),
        }
    if event_type in {"check_run", "check_suite"}:
        check_key = event_type
        check_payload = payload.get(check_key) if isinstance(payload.get(check_key), dict) else {}
        output = check_payload.get("output") if isinstance(check_payload.get("output"), dict) else {}
        app = check_payload.get("app") if isinstance(check_payload.get("app"), dict) else {}
        base[check_key] = {
            "name": check_payload.get("name"),
            "conclusion": check_payload.get("conclusion"),
            "status": check_payload.get("status"),
            "html_url": check_payload.get("html_url"),
            "pull_requests": _pull_request_numbers(check_payload.get("pull_requests")),
            "output": {"summary": redact_text(str(output.get("summary") or ""))},
            "app": _compact_dict(app, {"slug"}),
        }
    return base


def _compact_dict(value: object, keys: set[str]) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return {key: value.get(key) for key in keys if value.get(key) is not None}


def _pull_request_numbers(value: object) -> list[dict[str, int]]:
    if not isinstance(value, list):
        return []
    pull_requests: list[dict[str, int]] = []
    for item in value:
        if isinstance(item, dict) and item.get("number") is not None:
            try:
                pull_requests.append({"number": int(item["number"])})
            except (TypeError, ValueError):
                continue
    return pull_requests


def _free_form_audit_metadata(value: str) -> dict[str, object]:
    stripped = value.strip()
    return {
        "present": bool(stripped),
        "sha256": hashlib.sha256(stripped.encode("utf-8")).hexdigest() if stripped else None,
        "length": len(stripped),
    }


async def process_github_event(db: AsyncSession, *, event_id: UUID) -> dict[str, str]:
    event = await db.get(GitHubEvent, event_id)
    if event is None:
        raise ValueError(f"GitHub event not found: {event_id}")

    event.status = "processing"
    await db.flush()

    normalizer = GitHubEventNormalizer()
    try:
        normalized = normalizer.normalize(event.event_type, event.payload_json)
    except UnsupportedGitHubEvent:
        event.status = "ignored"
        event.processed_at = utc_now()
        await record_audit(
            db,
            actor_type="system",
            action="webhook.ignored",
            entity_type="github_event",
            entity_id=str(event.id),
            metadata={"event_type": event.event_type},
        )
        await db.commit()
        return {"status": "ignored", "event_id": str(event.id)}

    if isinstance(normalized, NormalizedIssueEvent):
        issue, run = await _process_issue_event(db, event=event, normalized=normalized)
        await db.commit()
        return {"status": "processed", "event_id": str(event.id), "issue_id": str(issue.id), "run_id": str(run.id)}

    if isinstance(normalized, NormalizedIssueCommentCommand):
        issue = await _process_issue_comment_command(db, event=event, normalized=normalized)
        await db.commit()
        return {"status": "processed", "event_id": str(event.id), "issue_id": str(issue.id)}

    if isinstance(normalized, NormalizedWorkflowRunEvent):
        result = await _process_workflow_run_event(db, event=event, normalized=normalized)
        await db.commit()
        return {"status": result, "event_id": str(event.id)}

    event.status = "ignored"
    event.processed_at = utc_now()
    await db.commit()
    return {"status": "ignored", "event_id": str(event.id)}


async def _process_issue_comment_command(
    db: AsyncSession,
    *,
    event: GitHubEvent,
    normalized: NormalizedIssueCommentCommand,
) -> Issue:
    installation = await _upsert_installation(db, normalized)
    repository = await _upsert_repository(db, installation=installation, normalized=normalized)
    issue = await _upsert_issue(db, repository=repository, normalized=normalized)
    plan = await _latest_plan_for_issue(db, issue=issue)
    run = await _latest_run_for_issue(db, issue=issue)

    await record_audit(
        db,
        actor_type="github",
        actor_id=normalized.sender_login,
        action="github.command.received",
        entity_type="issue",
        entity_id=str(issue.id),
        metadata={
            "command": normalized.command,
            "args": _free_form_audit_metadata(normalized.command_args),
            "comment_url": normalized.comment_url,
            "permission_check": "not_connected",
        },
    )

    if normalized.command in {"approve", "reject", "revise", "status", "stop"}:
        escalated = False
        if plan is not None:
            escalated = PolicyEngine().evaluate_plan(implementation_plan_from_db(plan)).decision == PolicyDecisionType.ESCALATE
        permission = await GitHubPermissionService().check_command_permission(
            installation=installation,
            repository=repository,
            username=normalized.sender_login,
            command=normalized.command,
            escalated=escalated,
        )
        await record_audit(
            db,
            actor_type="github",
            actor_id=normalized.sender_login,
            action="github.command.permission_checked",
            entity_type="issue",
            entity_id=str(issue.id),
            metadata={
                "command": normalized.command,
                "allowed": permission.allowed,
                "github_permission": permission.github_permission,
                "repopilot_role": permission.repopilot_role,
                "reason": permission.reason,
            },
        )
        if permission.allowed:
            await _apply_authorized_command(
                db,
                issue=issue,
                plan=plan,
                run=run,
                command=normalized.command,
                args=normalized.command_args,
                actor_id=normalized.sender_login,
            )
            event.status = "processed"
            event.processed_at = utc_now()
            return issue

        await record_audit(
            db,
            actor_type="system",
            action="github.command.blocked",
            entity_type="issue",
            entity_id=str(issue.id),
            metadata={
                "command": normalized.command,
                "reason": permission.reason,
                "github_permission": permission.github_permission,
                "repopilot_role": permission.repopilot_role,
            },
        )
        event.status = "blocked"
        event.processed_at = utc_now()
        return issue

    await record_audit(
        db,
        actor_type="system",
        action="github.command.unhandled",
        entity_type="issue",
        entity_id=str(issue.id),
        metadata={"command": normalized.command, "has_plan": plan is not None, "has_run": run is not None},
    )

    event.status = "processed"
    event.processed_at = utc_now()
    return issue


async def _apply_authorized_command(
    db: AsyncSession,
    *,
    issue: Issue,
    plan: Plan | None,
    run: AgentRun | None,
    command: str,
    args: str,
    actor_id: str,
) -> None:
    if command == "status":
        await record_audit(
            db,
            actor_type="github",
            actor_id=actor_id,
            action="github.command.status",
            entity_type="issue",
            entity_id=str(issue.id),
            metadata={"plan_id": str(plan.id) if plan else None, "run_id": str(run.id) if run else None},
        )
        return

    if command in {"approve", "reject", "revise"} and plan is None:
        await record_audit(
            db,
            actor_type="system",
            action="github.command.no_plan",
            entity_type="issue",
            entity_id=str(issue.id),
            metadata={"command": command},
        )
        return

    if command == "approve" and plan is not None:
        implementation_plan = implementation_plan_from_db(plan)
        approved_hash = stable_json_hash(implementation_plan.model_dump(mode="json", exclude={"plan_hash"}))
        plan.approval_status = PlanApprovalStatus.APPROVED.value
        plan.approved_at = utc_now()
        plan.plan_json = {
            **implementation_plan.model_dump(mode="json"),
            "plan_hash": approved_hash,
            "approved_plan_hash": approved_hash,
        }
        if run is not None:
            run.plan_id = plan.id
        await record_audit(
            db,
            actor_type="github",
            actor_id=actor_id,
            action="plan.approved_via_github_command",
            entity_type="plan",
            entity_id=str(plan.id),
            metadata={"issue_id": str(issue.id), "approved_plan_hash": approved_hash},
        )
        return

    if command == "reject" and plan is not None:
        reason = args.strip() or "Rejected from GitHub issue comment."
        plan.approval_status = PlanApprovalStatus.REJECTED.value
        plan.plan_json = {**plan.plan_json, "rejection_reason": reason}
        await record_audit(
            db,
            actor_type="github",
            actor_id=actor_id,
            action="plan.rejected_via_github_command",
            entity_type="plan",
            entity_id=str(plan.id),
            metadata={"reason": _free_form_audit_metadata(reason)},
        )
        return

    if command == "revise" and plan is not None:
        instructions = args.strip() or "Revision requested from GitHub issue comment."
        plan.approval_status = PlanApprovalStatus.REVISED.value
        new_plan = Plan(
            issue_id=plan.issue_id,
            approval_status=PlanApprovalStatus.WAITING.value,
            version=plan.version + 1,
            plan_json={
                **implementation_plan_from_db(plan).model_dump(mode="json"),
                "plan_id": "pending-db-id",
                "revision_parent_plan_id": str(plan.id),
                "revision_instructions": instructions,
            },
        )
        db.add(new_plan)
        await db.flush()
        new_plan.plan_json = {**new_plan.plan_json, "plan_id": str(new_plan.id)}
        if run is not None:
            run.plan_id = new_plan.id
        await record_audit(
            db,
            actor_type="github",
            actor_id=actor_id,
            action="plan.revision_requested_via_github_command",
            entity_type="plan",
            entity_id=str(plan.id),
            metadata={
                "instructions": _free_form_audit_metadata(instructions),
                "new_plan_id": str(new_plan.id),
                "run_id": str(run.id) if run else None,
            },
        )
        return

    if command == "stop" and run is not None:
        await _safe_transition(
            db,
            run=run,
            next_state=AgentRunState.CANCELLED,
            actor_id=actor_id,
            reason="GitHub issue comment requested run stop.",
        )


async def _process_workflow_run_event(
    db: AsyncSession,
    *,
    event: GitHubEvent,
    normalized: NormalizedWorkflowRunEvent,
) -> str:
    if normalized.pull_request_number is None:
        event.status = "ignored"
        event.processed_at = utc_now()
        await record_audit(
            db,
            actor_type="system",
            action="workflow_run.ignored",
            entity_type="github_event",
            entity_id=str(event.id),
            metadata={"reason": "workflow_run has no pull request number"},
        )
        return "ignored"

    pr = await db.scalar(
        select(PullRequest)
        .where(PullRequest.pr_number == normalized.pull_request_number)
        .order_by(PullRequest.created_at.desc())
    )
    if pr is None:
        event.status = "ignored"
        event.processed_at = utc_now()
        await record_audit(
            db,
            actor_type="system",
            action="workflow_run.unmatched",
            entity_type="github_event",
            entity_id=str(event.id),
            metadata={"pr_number": normalized.pull_request_number},
        )
        return "ignored"

    conclusion = normalized.conclusion if normalized.conclusion in {"success", "failure", "cancelled", "skipped"} else "failure"
    await CIAnalyzer().analyze_pr(
        db,
        pr_id=pr.id,
        request=CIAnalysisRequest(
            workflow_name=normalized.workflow_name,
            conclusion=conclusion,
            log_text=normalized.log_excerpt,
        ),
    )
    event.status = "processed"
    event.processed_at = utc_now()
    return "processed"


async def _process_issue_event(
    db: AsyncSession,
    *,
    event: GitHubEvent,
    normalized: NormalizedIssueEvent,
) -> tuple[Issue, AgentRun]:
    installation = await _upsert_installation(db, normalized)
    repository = await _upsert_repository(db, installation=installation, normalized=normalized)
    issue = await _upsert_issue(db, repository=repository, normalized=normalized)

    run = AgentRun(
        issue_id=issue.id,
        state=AgentRunState.TRIAGE_ISSUE.value,
        model_used=effective_settings(settings).model_name,
    )
    db.add(run)
    await db.flush()

    db.add(
        AgentStep(
            run_id=run.id,
            step_name="NORMALIZE_EVENT",
            input_hash=_payload_hash(event.payload_json),
            output_json=asdict(normalized),
            status="succeeded",
        )
    )

    triage = TriageService().triage(issue_id=str(issue.id), title=issue.title, body=normalized.issue_body)
    issue.issue_type = triage.issue_type.value
    issue.complexity = triage.complexity.value
    issue.risk_score = triage.risk_score
    issue.status = _status_for_recommended_action(triage.recommended_action)
    run.state = _state_for_recommended_action(triage.recommended_action)

    db.add(
        AgentStep(
            run_id=run.id,
            step_name="TRIAGE_ISSUE",
            input_hash=_payload_hash({"title": issue.title, "body": normalized.issue_body}),
            output_json=triage.model_dump(mode="json"),
            status="succeeded",
        )
    )

    event.status = "processed"
    event.processed_at = utc_now()
    await record_audit(
        db,
        actor_type="system",
        action="issue.triaged",
        entity_type="issue",
        entity_id=str(issue.id),
        metadata={"run_id": str(run.id), "recommended_action": triage.recommended_action},
    )
    return issue, run


async def _upsert_installation(db: AsyncSession, normalized: NormalizedIssueEvent) -> Installation:
    installation = await db.scalar(
        select(Installation).where(Installation.github_installation_id == normalized.installation_id)
    )
    if installation is None:
        installation = Installation(
            github_installation_id=normalized.installation_id,
            account_name=normalized.account_name,
            permissions_json={},
        )
        db.add(installation)
        await db.flush()
    else:
        installation.account_name = normalized.account_name
    return installation


async def _upsert_repository(
    db: AsyncSession,
    *,
    installation: Installation,
    normalized: NormalizedIssueEvent,
) -> Repository:
    repository = await db.scalar(
        select(Repository).where(
            Repository.installation_id == installation.id,
            Repository.owner == normalized.repository_owner,
            Repository.name == normalized.repository_name,
        )
    )
    if repository is None:
        repository = Repository(
            installation_id=installation.id,
            owner=normalized.repository_owner,
            name=normalized.repository_name,
            default_branch=normalized.default_branch,
        )
        db.add(repository)
        await db.flush()
    else:
        repository.default_branch = normalized.default_branch
    return repository


async def _upsert_issue(
    db: AsyncSession,
    *,
    repository: Repository,
    normalized: NormalizedIssueEvent,
) -> Issue:
    body_hash = _text_hash(normalized.issue_body)
    issue = await db.scalar(
        select(Issue).where(
            Issue.repository_id == repository.id,
            Issue.number == normalized.issue_number,
        )
    )
    if issue is None:
        issue = Issue(
            repository_id=repository.id,
            number=normalized.issue_number,
            title=normalized.issue_title,
            body_hash=body_hash,
            status="new",
        )
        db.add(issue)
        await db.flush()
    else:
        issue.title = normalized.issue_title
        issue.body_hash = body_hash
    return issue


async def _latest_plan_for_issue(db: AsyncSession, *, issue: Issue) -> Plan | None:
    result = await db.execute(select(Plan).where(Plan.issue_id == issue.id).order_by(Plan.version.desc()))
    return result.scalars().first()


async def _latest_run_for_issue(db: AsyncSession, *, issue: Issue) -> AgentRun | None:
    result = await db.execute(select(AgentRun).where(AgentRun.issue_id == issue.id).order_by(AgentRun.started_at.desc()))
    return result.scalars().first()


async def _safe_transition(
    db: AsyncSession,
    *,
    run: AgentRun,
    next_state: AgentRunState,
    actor_id: str,
    reason: str,
) -> None:
    try:
        await transition_run(
            db,
            run=run,
            next_state=next_state,
            actor_type="github",
            actor_id=actor_id,
            reason=reason,
        )
    except InvalidStateTransition as exc:
        await record_audit(
            db,
            actor_type="system",
            action="run.transition_blocked",
            entity_type="agent_run",
            entity_id=str(run.id),
            metadata={"error": str(exc), "requested_state": next_state.value},
        )


def _text_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _payload_hash(payload: dict) -> str:
    return _text_hash(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def _status_for_recommended_action(recommended_action: str) -> str:
    if recommended_action == "ask_info":
        return "needs_info"
    if recommended_action == "human_review":
        return "needs_human_review"
    if recommended_action == "reject":
        return "rejected"
    return "agent_ready"


def _state_for_recommended_action(recommended_action: str) -> str:
    if recommended_action == "plan":
        return AgentRunState.WAIT_FOR_APPROVAL.value
    if recommended_action == "human_review":
        return AgentRunState.POLICY_REVIEW_PLAN.value
    if recommended_action == "reject":
        return AgentRunState.REJECTED.value
    return AgentRunState.NEEDS_INFO.value
