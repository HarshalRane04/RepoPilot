from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, settings
from app.db.models import Installation, Repository, User
from app.services.audit import record_audit
from app.services.runtime_secrets import effective_settings
from app.services.url_safety import github_api_base_url, github_web_base_url


class GitHubOAuthError(RuntimeError):
    pass


class GitHubOAuthAuthorizationError(GitHubOAuthError):
    """Raised when a valid GitHub identity is not allowed into this workspace."""


@dataclass(frozen=True)
class GitHubOAuthProfile:
    github_user_id: str
    username: str
    email: str | None


class GitHubOAuthService:
    def __init__(self, config: Settings | None = None) -> None:
        self.config = config or effective_settings(settings)

    def is_configured(self) -> bool:
        return bool(self.config.github_client_id and self.config.github_client_secret)

    def authorization_url(self, *, state: str) -> str:
        if not self.config.github_client_id:
            raise GitHubOAuthError("GitHub OAuth client id is not configured.")
        return f"{github_web_base_url(self.config.github_web_base_url)}/login/oauth/authorize?" + urlencode(
            {
                "client_id": self.config.github_client_id,
                "redirect_uri": self.config.github_oauth_callback_url,
                "scope": "repo read:user user:email",
                "state": state,
                "allow_signup": "true",
            }
        )

    async def exchange_code(self, *, code: str) -> str:
        if not self.is_configured():
            raise GitHubOAuthError("GitHub OAuth credentials are not configured.")
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{github_web_base_url(self.config.github_web_base_url)}/login/oauth/access_token",
                headers={"Accept": "application/json"},
                data={
                    "client_id": self.config.github_client_id,
                    "client_secret": self.config.github_client_secret,
                    "code": code,
                    "redirect_uri": self.config.github_oauth_callback_url,
                },
            )
        if response.status_code >= 400:
            raise GitHubOAuthError(f"GitHub OAuth token exchange failed: {response.status_code} {response.text[:240]}")
        body = response.json()
        if body.get("error"):
            raise GitHubOAuthError(str(body.get("error_description") or body["error"]))
        token = body.get("access_token")
        if not token:
            raise GitHubOAuthError("GitHub OAuth token exchange did not return an access token.")
        return str(token)

    async def fetch_profile(self, *, token: str) -> GitHubOAuthProfile:
        async with httpx.AsyncClient(timeout=30) as client:
            user_response = await client.get(
                f"{github_api_base_url(self.config.github_api_base_url)}/user",
                headers=self._headers(token),
            )
            email_response = await client.get(
                f"{github_api_base_url(self.config.github_api_base_url)}/user/emails",
                headers=self._headers(token),
            )
        if user_response.status_code >= 400:
            raise GitHubOAuthError(f"GitHub user request failed: {user_response.status_code} {user_response.text[:240]}")
        user = user_response.json()
        email = user.get("email")
        if not email and email_response.status_code < 400:
            email = _primary_email(email_response.json())
        return GitHubOAuthProfile(
            github_user_id=str(user["id"]),
            username=str(user["login"]),
            email=str(email) if email else None,
        )

    async def fetch_repositories(self, *, token: str) -> list[dict[str, Any]]:
        repositories: list[dict[str, Any]] = []
        page = 1
        async with httpx.AsyncClient(timeout=30) as client:
            while page <= 10:
                response = await client.get(
                    f"{github_api_base_url(self.config.github_api_base_url)}/user/repos",
                    headers=self._headers(token),
                    params={
                        "affiliation": "owner,collaborator,organization_member",
                        "sort": "updated",
                        "direction": "desc",
                        "per_page": 100,
                        "page": page,
                    },
                )
                if response.status_code >= 400:
                    raise GitHubOAuthError(f"GitHub repository request failed: {response.status_code} {response.text[:240]}")
                batch = response.json()
                if not isinstance(batch, list) or not batch:
                    break
                repositories.extend(dict(item) for item in batch if isinstance(item, dict))
                if len(batch) < 100:
                    break
                page += 1
        return repositories

    async def sync_user_repositories(
        self,
        db: AsyncSession,
        *,
        profile: GitHubOAuthProfile,
        repositories: list[dict[str, Any]],
        user: User | None = None,
    ) -> Installation:
        user = user or await self.authorize_profile(db, profile=profile)
        user.username = profile.username
        user.email = profile.email or user.email

        installation = await db.scalar(
            select(Installation).where(Installation.github_installation_id == f"oauth:{profile.github_user_id}")
        )
        if installation is None:
            installation = Installation(
                github_installation_id=f"oauth:{profile.github_user_id}",
                account_name=profile.username,
                permissions_json={"source": "github_oauth", "scopes": ["repo", "read:user", "user:email"]},
            )
            db.add(installation)
            await db.flush()
        else:
            installation.account_name = profile.username
            installation.permissions_json = {"source": "github_oauth", "scopes": ["repo", "read:user", "user:email"]}

        for item in repositories:
            owner = item.get("owner") if isinstance(item.get("owner"), dict) else {}
            owner_name = str(owner.get("login") or profile.username)
            repo_name = str(item.get("name") or "")
            if not repo_name:
                continue
            repository = await db.scalar(
                select(Repository).where(
                    Repository.installation_id == installation.id,
                    Repository.owner == owner_name,
                    Repository.name == repo_name,
                )
            )
            if repository is None:
                repository = Repository(
                    installation_id=installation.id,
                    owner=owner_name,
                    name=repo_name,
                    default_branch=str(item.get("default_branch") or "main"),
                )
                db.add(repository)
            else:
                repository.default_branch = str(item.get("default_branch") or repository.default_branch)

        await record_audit(
            db,
            actor_type="github",
            actor_id=profile.username,
            action="github.oauth.repositories_synced",
            entity_type="installation",
            entity_id=str(installation.id),
            metadata={"repository_count": len(repositories)},
        )
        await db.commit()
        return installation

    async def authorize_profile(self, db: AsyncSession, *, profile: GitHubOAuthProfile) -> User:
        """Resolve an OAuth identity without granting owner access to arbitrary signers.

        An explicit owner login is the production-safe path. For local-first installs,
        the first GitHub identity may bootstrap the workspace; later unknown identities
        are denied until an administrator provisions a real membership model.
        """

        configured_owner = (self.config.github_owner_login or "").strip().casefold()
        if configured_owner and profile.username.casefold() != configured_owner:
            raise GitHubOAuthAuthorizationError(
                f"GitHub user '{profile.username}' is not authorized for this RepoPilot workspace."
            )

        user = await db.scalar(select(User).where(User.github_user_id == profile.github_user_id))
        if user is not None:
            user.username = profile.username
            user.email = profile.email or user.email
            return user

        existing_oauth_user = await db.scalar(select(User).where(User.github_user_id.is_not(None)).limit(1))
        if existing_oauth_user is not None:
            raise GitHubOAuthAuthorizationError(
                "This RepoPilot workspace already has an OAuth owner; ask that owner to provision access."
            )

        user = User(
            github_user_id=profile.github_user_id,
            username=profile.username,
            email=profile.email,
            role="owner",
        )
        db.add(user)
        await db.flush()
        await record_audit(
            db,
            actor_type="github",
            actor_id=profile.username,
            action="github.oauth.owner_bootstrapped",
            entity_type="user",
            entity_id=str(user.id),
            metadata={"configured_owner": bool(configured_owner)},
        )
        return user

    def _headers(self, token: str) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }


def _primary_email(items: Any) -> str | None:
    if not isinstance(items, list):
        return None
    primary = next((item for item in items if isinstance(item, dict) and item.get("primary") and item.get("verified")), None)
    if primary and primary.get("email"):
        return str(primary["email"])
    verified = next((item for item in items if isinstance(item, dict) and item.get("verified") and item.get("email")), None)
    return str(verified["email"]) if verified and verified.get("email") else None
