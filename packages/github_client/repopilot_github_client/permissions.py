from __future__ import annotations

from dataclasses import dataclass

GITHUB_ROLE_TO_REPOPILOT = {
    "admin": "admin",
    "maintain": "maintainer",
    "write": "write",
    "triage": "triage",
    "read": "read",
    "none": "viewer",
}

COMMAND_MIN_ROLE = {
    "approve": "write",
    "reject": "write",
    "revise": "triage",
    "status": "triage",
    "stop": "write",
}

ROLE_LEVELS = {
    "viewer": 0,
    "read": 0,
    "triage": 1,
    "write": 2,
    "maintainer": 3,
    "admin": 4,
    "owner": 5,
}


@dataclass(frozen=True)
class GitHubPermissionDecision:
    allowed: bool
    github_permission: str
    repopilot_role: str
    reason: str


def role_for_github_permission(permission: str) -> str:
    return GITHUB_ROLE_TO_REPOPILOT.get(permission, "viewer")


def required_role_for_command(command: str, *, escalated: bool = False) -> str:
    if escalated and command == "approve":
        return "maintainer"
    return COMMAND_MIN_ROLE.get(command, "owner")


def role_allows(*, actual_role: str, required_role: str) -> bool:
    return ROLE_LEVELS.get(actual_role, 0) >= ROLE_LEVELS.get(required_role, ROLE_LEVELS["owner"])


def command_permission_decision(*, github_permission: str, command: str, escalated: bool = False) -> GitHubPermissionDecision:
    repopilot_role = role_for_github_permission(github_permission)
    minimum = required_role_for_command(command, escalated=escalated)
    allowed = role_allows(actual_role=repopilot_role, required_role=minimum)
    reason = "Permission accepted." if allowed else f"Command '{command}' requires RepoPilot role '{minimum}'."
    return GitHubPermissionDecision(
        allowed=allowed,
        github_permission=github_permission,
        repopilot_role=repopilot_role,
        reason=reason,
    )
