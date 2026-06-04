from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from scripts import github_app_smoke


class FakeStore:
    def __init__(self) -> None:
        self.saved: dict[str, str] = {}

    def summary(self, fields: set[str]) -> dict[str, object]:
        return {
            "fields": [{"name": field, "configured": False, "secret": "SECRET" in field or "KEY" in field, "source": "encrypted_store"} for field in fields],
            "store_exists": False,
            "store_permissions_ok": True,
            "key_permissions_ok": True,
        }

    def save_values(self, values: dict[str, str]) -> None:
        self.saved.update(values)


def test_github_app_smoke_blocks_when_credentials_missing(monkeypatch) -> None:
    store = FakeStore()
    monkeypatch.setattr(github_app_smoke, "runtime_secret_store", lambda: store)
    monkeypatch.setattr(
        github_app_smoke,
        "effective_settings",
        lambda settings: SimpleNamespace(
            github_app_id=None,
            github_private_key=None,
            github_private_key_path=None,
            github_installation_id=None,
            github_webhook_secret="change-me-local-dev",
        ),
    )

    smoke = github_app_smoke.asyncio.run(github_app_smoke.capture_github_app_smoke())

    assert smoke.ok is False
    assert smoke.status == "blocked"
    assert "GITHUB_APP_ID" in smoke.detail
    assert smoke.token_received is False


def test_github_app_smoke_persists_verified_marker(monkeypatch) -> None:
    store = FakeStore()
    effective = SimpleNamespace(
        github_app_id="12345",
        github_private_key="-----BEGIN PRIVATE KEY-----\nredacted\n-----END PRIVATE KEY-----",
        github_private_key_path=None,
        github_installation_id="98765",
        github_webhook_secret="configured-webhook",
    )
    monkeypatch.setattr(github_app_smoke, "runtime_secret_store", lambda: store)
    monkeypatch.setattr(github_app_smoke, "effective_settings", lambda settings: effective)

    class FakeProvider:
        def __init__(self, config) -> None:
            self.config = config

        async def create_installation_access_token(self, installation_id: str) -> str:
            assert installation_id == "98765"
            return "installation-token-value"

    monkeypatch.setattr(github_app_smoke, "GitHubAppTokenProvider", FakeProvider)

    smoke = github_app_smoke.asyncio.run(github_app_smoke.capture_github_app_smoke())

    assert smoke.ok is True
    assert smoke.status == "passed"
    assert smoke.token_received is True
    assert store.saved["GITHUB_APP_VERIFIED_INSTALLATION_ID"] == "98765"
    assert "GITHUB_APP_VERIFIED_AT" in store.saved


def test_github_app_smoke_redacts_failure_detail(monkeypatch) -> None:
    store = FakeStore()
    effective = SimpleNamespace(
        github_app_id="12345",
        github_private_key="-----BEGIN PRIVATE KEY-----\nredacted\n-----END PRIVATE KEY-----",
        github_private_key_path=None,
        github_installation_id="98765",
        github_webhook_secret="configured-webhook",
    )
    monkeypatch.setattr(github_app_smoke, "runtime_secret_store", lambda: store)
    monkeypatch.setattr(github_app_smoke, "effective_settings", lambda settings: effective)

    class FakeProvider:
        def __init__(self, config) -> None:
            self.config = config

        async def create_installation_access_token(self, installation_id: str) -> str:
            raise github_app_smoke.GitHubIntegrationError("GitHub returned token=secret-token-value")

    monkeypatch.setattr(github_app_smoke, "GitHubAppTokenProvider", FakeProvider)

    smoke = github_app_smoke.asyncio.run(github_app_smoke.capture_github_app_smoke())

    assert smoke.ok is False
    assert smoke.status == "failed"
    assert "secret-token-value" not in smoke.detail


def test_github_app_smoke_writes_artifacts(tmp_path: Path) -> None:
    smoke = github_app_smoke.GitHubAppSmoke(
        generated_at="2026-06-04T00:00:00+00:00",
        ok=False,
        status="blocked",
        app_id_configured=False,
        private_key_configured=False,
        installation_id_configured=False,
        webhook_secret_configured=True,
        store_exists=False,
        store_permissions_ok=True,
        key_permissions_ok=True,
        verified_at=None,
        installation_id=None,
        token_received=False,
        detail="Missing required GitHub App credential(s): GITHUB_APP_ID.",
    )
    json_out = tmp_path / "github-app-smoke.json"
    md_out = tmp_path / "github-app-smoke.md"

    github_app_smoke.write_outputs(smoke=smoke, json_out=json_out, md_out=md_out)

    assert "GITHUB_APP_ID" in md_out.read_text(encoding="utf-8")
    assert '"token_received": false' in json_out.read_text(encoding="utf-8")
