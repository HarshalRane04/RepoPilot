from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Any, Literal


class WebhookSignatureError(ValueError):
    pass


class UnsupportedGitHubEvent(ValueError):
    pass


class GitHubSignatureVerifier:
    def __init__(self, secret: str) -> None:
        self.secret = secret.encode("utf-8")

    def verify(self, *, body: bytes, signature_header: str | None) -> None:
        if not signature_header:
            raise WebhookSignatureError("Missing X-Hub-Signature-256 header")

        expected = "sha256=" + hmac.new(self.secret, body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature_header):
            raise WebhookSignatureError("Invalid webhook signature")


@dataclass(frozen=True)
class NormalizedIssueEvent:
    source_event: Literal["issues"]
    action: str
    installation_id: str
    account_name: str
    repository_owner: str
    repository_name: str
    default_branch: str
    issue_number: int
    issue_title: str
    issue_body: str
    issue_url: str
    sender_login: str


@dataclass(frozen=True)
class NormalizedIssueCommentCommand:
    source_event: Literal["issue_comment"]
    action: str
    command: str
    command_args: str
    installation_id: str
    account_name: str
    repository_owner: str
    repository_name: str
    default_branch: str
    issue_number: int
    issue_title: str
    issue_body: str
    comment_body: str
    comment_url: str
    sender_login: str


@dataclass(frozen=True)
class NormalizedWorkflowRunEvent:
    source_event: Literal["workflow_run"]
    action: str
    installation_id: str
    account_name: str
    repository_owner: str
    repository_name: str
    default_branch: str
    workflow_name: str
    conclusion: str
    pull_request_number: int | None
    log_excerpt: str
    sender_login: str


class GitHubEventNormalizer:
    def normalize_issue_event(self, payload: dict[str, Any]) -> NormalizedIssueEvent:
        issue = payload.get("issue") or {}
        repository = payload.get("repository") or {}
        owner = repository.get("owner") or {}
        installation = payload.get("installation") or {}
        sender = payload.get("sender") or {}

        missing = [
            field
            for field, value in {
                "installation.id": installation.get("id"),
                "repository.name": repository.get("name"),
                "repository.owner.login": owner.get("login"),
                "issue.number": issue.get("number"),
                "issue.title": issue.get("title"),
            }.items()
            if value in (None, "")
        ]
        if missing:
            raise ValueError(f"Missing required GitHub issue payload fields: {', '.join(missing)}")

        return NormalizedIssueEvent(
            source_event="issues",
            action=str(payload.get("action") or "unknown"),
            installation_id=str(installation["id"]),
            account_name=str(owner["login"]),
            repository_owner=str(owner["login"]),
            repository_name=str(repository["name"]),
            default_branch=str(repository.get("default_branch") or "main"),
            issue_number=int(issue["number"]),
            issue_title=str(issue["title"]),
            issue_body=str(issue.get("body") or ""),
            issue_url=str(issue.get("html_url") or ""),
            sender_login=str(sender.get("login") or "unknown"),
        )

    def normalize_issue_comment_event(self, payload: dict[str, Any]) -> NormalizedIssueCommentCommand:
        comment = payload.get("comment") or {}
        body = str(comment.get("body") or "").strip()
        if not body.startswith("/repopilot"):
            raise UnsupportedGitHubEvent("Issue comment is not a RepoPilot command")
        parts = body.split(maxsplit=2)
        command = parts[1].lower() if len(parts) >= 2 else "help"
        args = parts[2] if len(parts) >= 3 else ""
        issue = payload.get("issue") or {}
        repository = payload.get("repository") or {}
        owner = repository.get("owner") or {}
        installation = payload.get("installation") or {}
        sender = payload.get("sender") or {}
        missing = [
            field
            for field, value in {
                "installation.id": installation.get("id"),
                "repository.name": repository.get("name"),
                "repository.owner.login": owner.get("login"),
                "issue.number": issue.get("number"),
                "issue.title": issue.get("title"),
            }.items()
            if value in (None, "")
        ]
        if missing:
            raise ValueError(f"Missing required GitHub issue_comment payload fields: {', '.join(missing)}")
        return NormalizedIssueCommentCommand(
            source_event="issue_comment",
            action=str(payload.get("action") or "unknown"),
            command=command,
            command_args=args,
            installation_id=str(installation["id"]),
            account_name=str(owner["login"]),
            repository_owner=str(owner["login"]),
            repository_name=str(repository["name"]),
            default_branch=str(repository.get("default_branch") or "main"),
            issue_number=int(issue["number"]),
            issue_title=str(issue["title"]),
            issue_body=str(issue.get("body") or ""),
            comment_body=body,
            comment_url=str(comment.get("html_url") or ""),
            sender_login=str(sender.get("login") or "unknown"),
        )

    def normalize_workflow_run_event(self, payload: dict[str, Any]) -> NormalizedWorkflowRunEvent:
        workflow_run = payload.get("workflow_run") or {}
        repository = payload.get("repository") or {}
        owner = repository.get("owner") or {}
        installation = payload.get("installation") or {}
        sender = payload.get("sender") or {}
        pull_requests = workflow_run.get("pull_requests") or []
        pr_number = None
        if pull_requests and isinstance(pull_requests[0], dict) and pull_requests[0].get("number") is not None:
            pr_number = int(pull_requests[0]["number"])
        missing = [
            field
            for field, value in {
                "installation.id": installation.get("id"),
                "repository.name": repository.get("name"),
                "repository.owner.login": owner.get("login"),
                "workflow_run.name": workflow_run.get("name"),
                "workflow_run.conclusion": workflow_run.get("conclusion"),
            }.items()
            if value in (None, "")
        ]
        if missing:
            raise ValueError(f"Missing required GitHub workflow_run payload fields: {', '.join(missing)}")
        return NormalizedWorkflowRunEvent(
            source_event="workflow_run",
            action=str(payload.get("action") or "unknown"),
            installation_id=str(installation["id"]),
            account_name=str(owner["login"]),
            repository_owner=str(owner["login"]),
            repository_name=str(repository["name"]),
            default_branch=str(repository.get("default_branch") or "main"),
            workflow_name=str(workflow_run["name"]),
            conclusion=str(workflow_run["conclusion"]),
            pull_request_number=pr_number,
            log_excerpt=str(workflow_run.get("display_title") or workflow_run.get("html_url") or ""),
            sender_login=str(sender.get("login") or "unknown"),
        )

    def normalize_check_run_event(self, payload: dict[str, Any]) -> NormalizedWorkflowRunEvent:
        check_run = payload.get("check_run") or {}
        return self._normalize_check_payload(payload=payload, check_payload=check_run, default_name="check_run")

    def normalize_check_suite_event(self, payload: dict[str, Any]) -> NormalizedWorkflowRunEvent:
        check_suite = payload.get("check_suite") or {}
        return self._normalize_check_payload(payload=payload, check_payload=check_suite, default_name="check_suite")

    def _normalize_check_payload(
        self,
        *,
        payload: dict[str, Any],
        check_payload: dict[str, Any],
        default_name: str,
    ) -> NormalizedWorkflowRunEvent:
        repository = payload.get("repository") or {}
        owner = repository.get("owner") or {}
        installation = payload.get("installation") or {}
        sender = payload.get("sender") or {}
        pull_requests = check_payload.get("pull_requests") or []
        pr_number = None
        if pull_requests and isinstance(pull_requests[0], dict) and pull_requests[0].get("number") is not None:
            pr_number = int(pull_requests[0]["number"])
        app = check_payload.get("app") if isinstance(check_payload.get("app"), dict) else {}
        output = check_payload.get("output") if isinstance(check_payload.get("output"), dict) else {}
        conclusion = str(check_payload.get("conclusion") or check_payload.get("status") or "failure")
        missing = [
            field
            for field, value in {
                "installation.id": installation.get("id"),
                "repository.name": repository.get("name"),
                "repository.owner.login": owner.get("login"),
            }.items()
            if value in (None, "")
        ]
        if missing:
            raise ValueError(f"Missing required GitHub check payload fields: {', '.join(missing)}")
        return NormalizedWorkflowRunEvent(
            source_event="workflow_run",
            action=str(payload.get("action") or "unknown"),
            installation_id=str(installation["id"]),
            account_name=str(owner["login"]),
            repository_owner=str(owner["login"]),
            repository_name=str(repository["name"]),
            default_branch=str(repository.get("default_branch") or "main"),
            workflow_name=str(check_payload.get("name") or app.get("slug") or default_name),
            conclusion=conclusion,
            pull_request_number=pr_number,
            log_excerpt=str(output.get("summary") or check_payload.get("html_url") or ""),
            sender_login=str(sender.get("login") or "unknown"),
        )

    def normalize(
        self,
        event_type: str,
        payload: dict[str, Any],
    ) -> NormalizedIssueEvent | NormalizedIssueCommentCommand | NormalizedWorkflowRunEvent:
        if event_type == "issues":
            return self.normalize_issue_event(payload)
        if event_type == "issue_comment":
            return self.normalize_issue_comment_event(payload)
        if event_type == "workflow_run":
            return self.normalize_workflow_run_event(payload)
        if event_type == "check_run":
            return self.normalize_check_run_event(payload)
        if event_type == "check_suite":
            return self.normalize_check_suite_event(payload)
        raise UnsupportedGitHubEvent(f"Unsupported GitHub event type: {event_type}")
