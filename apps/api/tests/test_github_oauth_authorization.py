from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from app.core.config import settings
from app.db.models import User
from app.services.github_oauth import (
    GitHubOAuthAuthorizationError,
    GitHubOAuthProfile,
    GitHubOAuthService,
)


class FakeOAuthDb:
    def __init__(self, scalar_results: list[User | None] | None = None) -> None:
        self.scalar_results = list(scalar_results or [])
        self.added: list[object] = []

    async def scalar(self, _statement):
        return self.scalar_results.pop(0) if self.scalar_results else None

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        return None


def profile(*, user_id: str = "123", username: str = "octocat") -> GitHubOAuthProfile:
    return GitHubOAuthProfile(github_user_id=user_id, username=username, email="octocat@example.com")


def test_configured_owner_login_rejects_other_github_users() -> None:
    config = settings.model_copy(update={"github_owner_login": "approved-owner"})
    service = GitHubOAuthService(config)

    with pytest.raises(GitHubOAuthAuthorizationError, match="not authorized"):
        asyncio.run(service.authorize_profile(FakeOAuthDb(), profile=profile(username="someone-else")))


def test_existing_oauth_user_keeps_database_role() -> None:
    existing = User(
        id=uuid4(),
        github_user_id="123",
        username="old-name",
        email=None,
        role="viewer",
    )
    service = GitHubOAuthService(settings.model_copy(update={"github_owner_login": "octocat"}))

    resolved = asyncio.run(service.authorize_profile(FakeOAuthDb([existing]), profile=profile()))

    assert resolved is existing
    assert resolved.role == "viewer"
    assert resolved.username == "octocat"


def test_unknown_oauth_user_is_denied_after_owner_bootstrap() -> None:
    existing_owner = User(
        id=uuid4(),
        github_user_id="owner-id",
        username="owner",
        role="owner",
    )
    service = GitHubOAuthService(settings.model_copy(update={"github_owner_login": None}))

    with pytest.raises(GitHubOAuthAuthorizationError, match="already has an OAuth owner"):
        asyncio.run(service.authorize_profile(FakeOAuthDb([None, existing_owner]), profile=profile(user_id="456")))


def test_first_oauth_user_can_bootstrap_local_workspace_owner() -> None:
    db = FakeOAuthDb([None, None])
    service = GitHubOAuthService(settings.model_copy(update={"github_owner_login": None}))

    resolved = asyncio.run(service.authorize_profile(db, profile=profile()))

    assert resolved.role == "owner"
    assert resolved.github_user_id == "123"
    assert resolved in db.added
