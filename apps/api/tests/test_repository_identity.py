from datetime import UTC, datetime

from app.api.routes.installations import _canonicalize_installation_responses
from app.api.routes.repos import _canonicalize_repository_responses


def test_repository_identity_prefers_writable_alias_and_preserves_latest_index_evidence() -> None:
    oauth = {
        "id": "repo-oauth",
        "installation_id": "installation-oauth",
        "source_mode": "oauth_discovery",
        "acquirable": False,
        "owner": "Octo",
        "name": "Demo",
        "default_branch": "main",
        "last_indexed_sha": "abc123",
        "issue_count": 2,
        "indexed_at": datetime(2026, 7, 13, 8, 0, tzinfo=UTC),
        "index_status": "ready",
    }
    github_app = {
        "id": "repo-app",
        "installation_id": "installation-app",
        "source_mode": "github_app",
        "acquirable": True,
        "owner": "octo",
        "name": "demo",
        "default_branch": "main",
        "last_indexed_sha": None,
        "issue_count": 2,
        "indexed_at": None,
        "index_status": None,
    }

    result = _canonicalize_repository_responses(
        [oauth, github_app],
        issue_numbers_by_repository={
            "repo-oauth": {1, 2},
            "repo-app": {1, 2},
        },
    )

    assert len(result) == 1
    repository = result[0]
    assert repository["canonical_id"] == "octo/demo"
    assert repository["id"] == "repo-app"
    assert repository["acquirable"] is True
    assert repository["alias_ids"] == ["repo-app", "repo-oauth"]
    assert repository["installation_ids"] == ["installation-app", "installation-oauth"]
    assert repository["source_modes"] == ["github_app", "oauth_discovery"]
    assert repository["issue_count"] == 2
    assert repository["last_indexed_sha"] == "abc123"
    assert repository["indexed_at"] == datetime(2026, 7, 13, 8, 0, tzinfo=UTC)


def test_repository_identity_keeps_distinct_github_repositories_separate() -> None:
    base = {
        "installation_id": "installation-app",
        "source_mode": "github_app",
        "acquirable": True,
        "owner": "octo",
        "default_branch": "main",
        "last_indexed_sha": None,
        "issue_count": 0,
        "indexed_at": None,
    }

    result = _canonicalize_repository_responses(
        [
            {**base, "id": "one", "name": "one"},
            {**base, "id": "two", "name": "two"},
        ]
    )

    assert [item["canonical_id"] for item in result] == ["octo/one", "octo/two"]


def test_installation_identity_prefers_github_app_and_counts_unique_repositories() -> None:
    created = datetime(2026, 7, 13, 8, 0, tzinfo=UTC)
    responses = [
        {
            "id": "oauth-id",
            "github_installation_id": "oauth:octo",
            "account_name": "Octo",
            "repository_count": 2,
            "created_at": created,
            "source_mode": "oauth_discovery",
            "_repository_keys": {"octo/one", "octo/two"},
        },
        {
            "id": "app-id",
            "github_installation_id": "42",
            "account_name": "octo",
            "repository_count": 2,
            "created_at": created,
            "source_mode": "github_app",
            "_repository_keys": {"octo/one", "octo/two"},
        },
    ]

    result = _canonicalize_installation_responses(responses)

    assert len(result) == 1
    installation = result[0]
    assert installation["canonical_id"] == "octo"
    assert installation["id"] == "app-id"
    assert installation["github_installation_id"] == "42"
    assert installation["alias_ids"] == ["app-id", "oauth-id"]
    assert installation["repository_count"] == 2
    assert installation["source_modes"] == ["github_app", "oauth_discovery"]
