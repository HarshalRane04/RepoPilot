from __future__ import annotations

from repopilot_github_client import GitHubPermissionDecision, command_permission_decision, role_for_github_permission

from app.db.models import Installation, Repository
from app.services.github_app import GitHubApiClient, GitHubIntegrationError


class GitHubPermissionService:
    def __init__(self, *, client: GitHubApiClient | None = None) -> None:
        self.client = client or GitHubApiClient()

    async def check_command_permission(
        self,
        *,
        installation: Installation,
        repository: Repository,
        username: str,
        command: str,
        escalated: bool = False,
    ) -> GitHubPermissionDecision:
        try:
            github_permission = await self.client.get_collaborator_permission(
                installation_id=installation.github_installation_id,
                owner=repository.owner,
                repo=repository.name,
                username=username,
            )
        except GitHubIntegrationError as exc:
            return GitHubPermissionDecision(
                allowed=False,
                github_permission="unavailable",
                repopilot_role="viewer",
                reason=f"GitHub permission check failed: {exc}",
            )

        return command_permission_decision(
            github_permission=github_permission,
            command=command,
            escalated=escalated,
        )


__all__ = ["GitHubPermissionDecision", "GitHubPermissionService", "role_for_github_permission"]
