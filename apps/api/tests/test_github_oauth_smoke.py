from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from scripts import github_oauth_smoke


class FakeStore:
    def summary(self, fields: set[str]) -> dict[str, object]:
        return {
            "fields": [{"name": field, "configured": False, "secret": "SECRET" in field, "source": "encrypted_store"} for field in fields],
            "store_exists": False,
            "store_permissions_ok": True,
            "key_permissions_ok": True,
        }


def test_github_oauth_smoke_blocks_when_credentials_missing(monkeypatch) -> None:
    monkeypatch.setattr(github_oauth_smoke, "runtime_secret_store", lambda: FakeStore())
    monkeypatch.setattr(
        github_oauth_smoke,
        "effective_settings",
        lambda settings: SimpleNamespace(
            github_client_id=None,
            github_client_secret=None,
            github_oauth_callback_url="http://localhost:8000/auth/github/callback",
            web_app_url="http://localhost:3001",
            session_secret_key="change-me-session-secret",
            github_api_base_url="https://api.github.com",
            github_web_base_url="https://github.com",
        ),
    )

    smoke = github_oauth_smoke.capture_github_oauth_smoke()

    assert smoke.ok is False
    assert smoke.status == "blocked"
    assert "GITHUB_CLIENT_ID" in smoke.detail
    assert "GITHUB_CLIENT_SECRET" in smoke.detail
    assert smoke.authorization_url_generated is False


def test_github_oauth_smoke_passes_when_authorize_url_can_be_generated(monkeypatch) -> None:
    monkeypatch.setattr(github_oauth_smoke, "runtime_secret_store", lambda: FakeStore())
    monkeypatch.setattr(
        github_oauth_smoke,
        "effective_settings",
        lambda settings: SimpleNamespace(
            github_client_id="client-id",
            github_client_secret="configured-client-secret",
            github_oauth_callback_url="http://localhost:8000/auth/github/callback",
            web_app_url="http://localhost:3001",
            session_secret_key="configured-session-secret",
            github_api_base_url="https://api.github.com",
            github_web_base_url="https://github.com",
        ),
    )

    smoke = github_oauth_smoke.capture_github_oauth_smoke()

    assert smoke.ok is True
    assert smoke.status == "passed"
    assert smoke.authorization_url_generated is True
    assert smoke.client_secret_configured is True


def test_github_oauth_smoke_rejects_invalid_public_urls(monkeypatch) -> None:
    monkeypatch.setattr(github_oauth_smoke, "runtime_secret_store", lambda: FakeStore())
    monkeypatch.setattr(
        github_oauth_smoke,
        "effective_settings",
        lambda settings: SimpleNamespace(
            github_client_id="client-id",
            github_client_secret="configured-client-secret",
            github_oauth_callback_url="http://evil.example.com/auth/github/callback",
            web_app_url="http://localhost:3001",
            session_secret_key="configured-session-secret",
            github_api_base_url="https://api.github.com",
            github_web_base_url="https://github.com",
        ),
    )

    smoke = github_oauth_smoke.capture_github_oauth_smoke()

    assert smoke.ok is False
    assert smoke.status == "blocked"
    assert "GITHUB_OAUTH_CALLBACK_URL" in smoke.detail


def test_github_oauth_smoke_writes_redacted_artifacts(tmp_path: Path) -> None:
    smoke = github_oauth_smoke.GitHubOAuthSmoke(
        generated_at="2026-06-05T00:00:00+00:00",
        ok=False,
        status="blocked",
        client_id_configured=False,
        client_secret_configured=False,
        callback_url_configured=True,
        web_app_url_configured=True,
        session_secret_configured=True,
        github_base_urls_configured=True,
        authorization_url_generated=False,
        store_exists=False,
        store_permissions_ok=True,
        key_permissions_ok=True,
        detail="Missing or invalid GitHub OAuth setting(s): GITHUB_CLIENT_ID.",
    )
    json_out = tmp_path / "github-oauth-smoke.json"
    md_out = tmp_path / "github-oauth-smoke.md"

    github_oauth_smoke.write_outputs(smoke=smoke, json_out=json_out, md_out=md_out)

    assert "GITHUB_CLIENT_ID" in md_out.read_text(encoding="utf-8")
    assert '"authorization_url_generated": false' in json_out.read_text(encoding="utf-8")
