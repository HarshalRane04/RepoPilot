from __future__ import annotations

import hashlib
import hmac
import json
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services.security_envelope import rate_limiter

DEV_AUTH_HEADERS = {"X-RepoPilot-User": "harshal", "X-RepoPilot-Role": "owner"}


def isolate_runtime_secret_store(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(settings, "runtime_secrets_key", None)
    monkeypatch.setattr(settings, "runtime_secrets_key_path", str(tmp_path / "runtime-secrets.key"))
    monkeypatch.setattr(settings, "runtime_secrets_store_path", str(tmp_path / "runtime-secrets.json"))


def enable_dev_header_auth(monkeypatch) -> None:
    monkeypatch.setattr(settings, "dev_header_auth_enabled", True)
    monkeypatch.setattr(settings, "environment", "local")


def authenticated(headers: dict[str, str] | None = None) -> dict[str, str]:
    return {**DEV_AUTH_HEADERS, **(headers or {})}


def sign(body: bytes) -> str:
    return "sha256=" + hmac.new(settings.github_webhook_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def test_health_route() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_protected_route_requires_authenticated_user(monkeypatch) -> None:
    monkeypatch.setattr(settings, "dev_header_auth_enabled", False)
    client = TestClient(app)

    response = client.get("/settings/readiness")

    assert response.status_code == 401


def test_session_route_uses_dev_headers(monkeypatch) -> None:
    enable_dev_header_auth(monkeypatch)
    client = TestClient(app)

    response = client.get("/auth/session", headers=DEV_AUTH_HEADERS)

    assert response.status_code == 200
    assert response.json()["username"] == "harshal"
    assert response.json()["role"] == "owner"


def test_github_login_reports_setup_when_oauth_credentials_are_missing(monkeypatch, tmp_path) -> None:
    isolate_runtime_secret_store(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "github_client_id", None)
    monkeypatch.setattr(settings, "github_client_secret", None)
    client = TestClient(app)

    response = client.get("/auth/github/login")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "placeholder"
    assert body["authorize_url"] is None
    assert "Settings -> GitHub" in body["next_step"]


def test_github_login_sets_state_cookie_and_returns_authorize_url(monkeypatch, tmp_path) -> None:
    isolate_runtime_secret_store(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "github_client_id", "client-123")
    monkeypatch.setattr(settings, "github_client_secret", "secret-123")
    monkeypatch.setattr(settings, "github_oauth_callback_url", "http://localhost:8000/auth/github/callback")
    client = TestClient(app)

    response = client.get("/auth/github/login")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "configured"
    assert body["authorize_url"]
    parsed_url = urlparse(body["authorize_url"])
    params = parse_qs(parsed_url.query)
    assert parsed_url.netloc == "github.com"
    assert parsed_url.path == "/login/oauth/authorize"
    assert params["client_id"] == ["client-123"]
    assert params["redirect_uri"] == ["http://localhost:8000/auth/github/callback"]
    assert params["scope"] == ["repo read:user user:email"]
    assert params["state"]
    assert "repopilot_oauth_state=" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]


def test_github_oauth_config_save_is_encrypted_and_used(monkeypatch, tmp_path) -> None:
    isolate_runtime_secret_store(monkeypatch, tmp_path)
    enable_dev_header_auth(monkeypatch)
    monkeypatch.setattr(settings, "github_client_id", None)
    monkeypatch.setattr(settings, "github_client_secret", None)
    monkeypatch.setattr(settings, "session_secret_key", "change-me-session-secret")
    client = TestClient(app)
    payload = {
        "github_client_id": "runtime-client",
        "github_client_secret": "runtime-secret-value",
        "session_secret_key": "runtime-session-secret-0123456789abcdef0123456789abcdef",
        "github_oauth_callback_url": "http://localhost:8000/auth/github/callback",
        "web_app_url": "http://127.0.0.1:3001",
        "github_api_base_url": "https://api.github.com",
        "github_web_base_url": "https://github.com",
    }

    response = client.post(
        "/settings/github/oauth",
        json=payload,
        headers=authenticated({"X-RepoPilot-Intent": "save-oauth-secrets"}),
    )

    assert response.status_code == 200
    body = response.json()
    assert all(field["configured"] for field in body["fields"])
    assert "runtime-secret-value" not in response.text
    store_text = (tmp_path / "runtime-secrets.json").read_text(encoding="utf-8")
    assert "runtime-secret-value" not in store_text
    assert "runtime-session-secret" not in store_text
    assert (tmp_path / "runtime-secrets.json").stat().st_mode & 0o077 == 0
    assert (tmp_path / "runtime-secrets.key").stat().st_mode & 0o077 == 0

    login = client.get("/auth/github/login")
    params = parse_qs(urlparse(login.json()["authorize_url"]).query)
    assert params["client_id"] == ["runtime-client"]
    assert params["redirect_uri"] == ["http://localhost:8000/auth/github/callback"]


def test_github_oauth_config_save_requires_intent_header(monkeypatch, tmp_path) -> None:
    isolate_runtime_secret_store(monkeypatch, tmp_path)
    enable_dev_header_auth(monkeypatch)
    client = TestClient(app)

    response = client.post(
        "/settings/github/oauth",
        json={
            "github_client_id": "runtime-client",
            "github_client_secret": "runtime-secret-value",
            "session_secret_key": "runtime-session-secret-0123456789abcdef0123456789abcdef",
            "github_oauth_callback_url": "http://localhost:8000/auth/github/callback",
            "web_app_url": "http://127.0.0.1:3001",
        },
        headers=authenticated(),
    )

    assert response.status_code == 400
    assert not (tmp_path / "runtime-secrets.json").exists()


def test_github_app_config_save_is_encrypted_and_marks_unverified(monkeypatch, tmp_path) -> None:
    isolate_runtime_secret_store(monkeypatch, tmp_path)
    enable_dev_header_auth(monkeypatch)
    monkeypatch.setattr(settings, "github_app_id", None)
    monkeypatch.setattr(settings, "github_private_key", None)
    monkeypatch.setattr(settings, "github_private_key_path", None)
    monkeypatch.setattr(settings, "github_installation_id", None)
    client = TestClient(app)

    response = client.post(
        "/settings/github/app",
        json={
            "github_webhook_secret": "runtime-webhook-secret-0123456789",
            "github_app_id": "12345",
            "github_app_slug": "repopilot-demo",
            "github_private_key": "-----BEGIN PRIVATE KEY-----\\nfake\\n-----END PRIVATE KEY-----",
            "github_installation_id": "67890",
        },
        headers=authenticated({"X-RepoPilot-Intent": "save-github-app-secrets"}),
    )

    assert response.status_code == 200
    body = response.json()
    configured_fields = {field["name"] for field in body["fields"] if field["configured"]}
    assert {"GITHUB_WEBHOOK_SECRET", "GITHUB_APP_ID", "GITHUB_APP_PRIVATE_KEY", "GITHUB_INSTALLATION_ID"} <= configured_fields
    assert "runtime-webhook-secret" not in response.text
    assert "BEGIN PRIVATE KEY" not in response.text
    store_text = (tmp_path / "runtime-secrets.json").read_text(encoding="utf-8")
    assert "runtime-webhook-secret" not in store_text
    assert "BEGIN PRIVATE KEY" not in store_text

    readiness = client.get("/settings/readiness", headers=authenticated()).json()
    app_gate = next(item for item in readiness["integrations"] if item["name"] == "GitHub App installation credentials")
    assert app_gate["state"] == "unverified"
    assert readiness["github_mode"] == "credentials_unverified"


def test_github_app_verify_persists_verified_read_only_state(monkeypatch, tmp_path) -> None:
    isolate_runtime_secret_store(monkeypatch, tmp_path)
    enable_dev_header_auth(monkeypatch)
    client = TestClient(app)
    client.post(
        "/settings/github/app",
        json={
            "github_webhook_secret": "runtime-webhook-secret-0123456789",
            "github_app_id": "12345",
            "github_private_key": "-----BEGIN PRIVATE KEY-----\\nfake\\n-----END PRIVATE KEY-----",
            "github_installation_id": "67890",
        },
        headers=authenticated({"X-RepoPilot-Intent": "save-github-app-secrets"}),
    )

    async def fake_create_installation_access_token(self, installation_id: str) -> str:
        assert installation_id == "67890"
        return "ghs_runtime_token"

    monkeypatch.setattr(
        "app.api.routes.settings.GitHubAppTokenProvider.create_installation_access_token",
        fake_create_installation_access_token,
    )

    response = client.post("/settings/github/app/verify", headers=authenticated())

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert "ghs_runtime_token" not in response.text

    readiness = client.get("/settings/readiness", headers=authenticated()).json()
    app_gate = next(item for item in readiness["integrations"] if item["name"] == "GitHub App installation credentials")
    assert app_gate["state"] == "verified"
    assert app_gate["mode"] == "read_only_verified"
    assert readiness["github_mode"] == "read_only_verified"


def test_model_catalog_exposes_verified_provider_models(monkeypatch) -> None:
    enable_dev_header_auth(monkeypatch)
    client = TestClient(app)
    from app.services import model_catalog as model_catalog_service

    model_catalog_service._dynamic_model_cache.clear()

    async def fake_fetch_openrouter_models(*, timeout_seconds: int = 10, base_url: str | None = None) -> list[dict[str, object]]:
        assert timeout_seconds >= 5
        assert base_url is None or base_url.startswith("https://")
        return [
            {
                "id": "openrouter/auto",
                "name": "Auto Router",
                "context_window": "2,000,000",
                "capabilities": ("tools",),
                "reasoning_levels": (),
                "is_free": False,
                "pricing": {"prompt": "-1", "completion": "-1"},
            },
            {
                "id": "google/gemma-3-27b-it:free",
                "name": "Gemma 3 27B (Free)",
                "context_window": "131,072",
                "capabilities": ("text",),
                "reasoning_levels": (),
                "is_free": True,
                "pricing": {"prompt": "0", "completion": "0", "request": "0"},
            },
        ]

    monkeypatch.setattr("app.services.model_catalog.fetch_openrouter_models", fake_fetch_openrouter_models)

    response = client.get("/settings/models/catalog", headers=authenticated())

    assert response.status_code == 200
    providers = {provider["id"]: provider for provider in response.json()["providers"]}
    assert "openai" in providers
    assert "anthropic" in providers
    assert "google" in providers
    assert "openrouter" in providers
    assert any(model["id"] == "gpt-5.5" for model in providers["openai"]["models"])
    assert any(model["id"] == "claude-sonnet-4-6" for model in providers["anthropic"]["models"])
    assert any(model["id"] == "gemini-3-pro-preview" for model in providers["google"]["models"])
    assert any("high" in model["reasoning_levels"] for model in providers["openai"]["models"])
    assert any(model["id"] == "google/gemma-3-27b-it:free" and model["is_free"] for model in providers["openrouter"]["models"])


def test_model_config_save_is_encrypted_and_updates_readiness(monkeypatch, tmp_path) -> None:
    isolate_runtime_secret_store(monkeypatch, tmp_path)
    enable_dev_header_auth(monkeypatch)
    monkeypatch.setattr(settings, "model_provider", "mock")
    monkeypatch.setattr(settings, "model_name", "mock-planner")
    monkeypatch.setattr(settings, "model_api_key", None)
    monkeypatch.setattr(settings, "model_base_url", None)
    client = TestClient(app)

    response = client.post(
        "/settings/models/config",
        json={
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "model_api_key": "sk-ant-runtime-secret",
            "model_base_url": "https://api.anthropic.com",
            "model_reasoning_level": "high",
        },
        headers=authenticated({"X-RepoPilot-Intent": "save-model-provider"}),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "anthropic"
    assert body["model"] == "claude-sonnet-4-6"
    assert body["status"] == "configured"
    assert body["api_key_configured"] is True
    assert body["reasoning_level"] == "high"
    assert "sk-ant-runtime-secret" not in response.text
    store_text = (tmp_path / "runtime-secrets.json").read_text(encoding="utf-8")
    assert "sk-ant-runtime-secret" not in store_text

    readiness = client.get("/settings/readiness", headers=authenticated()).json()
    model_gate = next(item for item in readiness["integrations"] if item["name"] == "LLM model gateway")
    assert model_gate["state"] == "unverified"
    assert model_gate["mode"] == "live_model_unverified"
    assert "claude-sonnet-4-6" in model_gate["detail"]


def test_model_config_save_rejects_unsupported_reasoning_level(monkeypatch, tmp_path) -> None:
    isolate_runtime_secret_store(monkeypatch, tmp_path)
    enable_dev_header_auth(monkeypatch)
    client = TestClient(app)

    response = client.post(
        "/settings/models/config",
        json={
            "provider": "mistral",
            "model": "codestral-2508",
            "model_api_key": "sk-runtime-secret",
            "model_reasoning_level": "high",
        },
        headers=authenticated({"X-RepoPilot-Intent": "save-model-provider"}),
    )

    assert response.status_code == 422
    assert not (tmp_path / "runtime-secrets.json").exists()


def test_model_config_save_rejects_unknown_model(monkeypatch, tmp_path) -> None:
    isolate_runtime_secret_store(monkeypatch, tmp_path)
    enable_dev_header_auth(monkeypatch)
    client = TestClient(app)

    response = client.post(
        "/settings/models/config",
        json={
            "provider": "openai",
            "model": "gpt-made-up",
            "model_api_key": "sk-runtime-secret",
        },
        headers=authenticated({"X-RepoPilot-Intent": "save-model-provider"}),
    )

    assert response.status_code == 422
    assert not (tmp_path / "runtime-secrets.json").exists()


def test_model_config_save_requires_intent_header(monkeypatch, tmp_path) -> None:
    isolate_runtime_secret_store(monkeypatch, tmp_path)
    enable_dev_header_auth(monkeypatch)
    client = TestClient(app)

    response = client.post(
        "/settings/models/config",
        json={
            "provider": "openai",
            "model": "gpt-5.5",
            "model_api_key": "sk-runtime-secret",
        },
        headers=authenticated(),
    )

    assert response.status_code == 400
    assert not (tmp_path / "runtime-secrets.json").exists()


def test_model_provider_verify_requires_saved_api_key(monkeypatch, tmp_path) -> None:
    isolate_runtime_secret_store(monkeypatch, tmp_path)
    enable_dev_header_auth(monkeypatch)
    monkeypatch.setattr(settings, "model_provider", "openai")
    monkeypatch.setattr(settings, "model_name", "gpt-5.5")
    monkeypatch.setattr(settings, "model_api_key", None)
    client = TestClient(app)

    response = client.post("/settings/models/verify", headers=authenticated())

    assert response.status_code == 409
    assert "API key" in response.text


def test_model_provider_verify_is_rate_limited(monkeypatch, tmp_path) -> None:
    isolate_runtime_secret_store(monkeypatch, tmp_path)
    enable_dev_header_auth(monkeypatch)
    monkeypatch.setattr(settings, "rate_limit_expensive_per_minute", 1)
    monkeypatch.setattr(settings, "rate_limit_window_seconds", 60)
    monkeypatch.setattr(settings, "model_provider", "openai")
    monkeypatch.setattr(settings, "model_name", "gpt-5.5")
    monkeypatch.setattr(settings, "model_api_key", None)
    rate_limiter.clear()
    client = TestClient(app)

    try:
        first = client.post("/settings/models/verify", headers=authenticated())
        second = client.post("/settings/models/verify", headers=authenticated())
    finally:
        rate_limiter.clear()

    assert first.status_code == 409
    assert second.status_code == 429
    assert second.headers["Retry-After"]


def test_model_provider_verify_calls_provider_without_returning_secret(monkeypatch, tmp_path) -> None:
    isolate_runtime_secret_store(monkeypatch, tmp_path)
    enable_dev_header_auth(monkeypatch)
    monkeypatch.setattr(settings, "model_provider", "mock")
    monkeypatch.setattr(settings, "model_name", "mock-planner")
    monkeypatch.setattr(settings, "model_api_key", None)
    monkeypatch.setattr(settings, "model_base_url", None)
    client = TestClient(app)
    client.post(
        "/settings/models/config",
        json={
            "provider": "openai",
            "model": "gpt-5.5",
            "model_api_key": "sk-runtime-secret",
        },
        headers=authenticated({"X-RepoPilot-Intent": "save-model-provider"}),
    )

    async def fake_verify_model_provider(**kwargs):
        assert kwargs["api_key"] == "sk-runtime-secret"
        return type(
            "Result",
            (),
            {
                "ok": True,
                "checked_at": "2026-05-24T00:00:00+00:00",
                "as_dict": lambda self: {
                    "ok": True,
                    "provider": kwargs["provider"].id,
                    "model": kwargs["model"],
                    "detail": "Provider responded and selected model was present in the model list.",
                    "checked_at": "2026-05-24T00:00:00+00:00",
                    "latency_ms": 12,
                }
            },
        )()

    monkeypatch.setattr("app.api.routes.settings.verify_model_provider", fake_verify_model_provider)

    response = client.post("/settings/models/verify", headers=authenticated())

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["model"] == "gpt-5.5"
    assert "sk-runtime-secret" not in response.text


def test_settings_readiness_route_exposes_production_gates(monkeypatch) -> None:
    enable_dev_header_auth(monkeypatch)
    client = TestClient(app)

    response = client.get("/settings/readiness", headers=authenticated())

    assert response.status_code == 200
    body = response.json()
    assert "production_ready" in body
    assert body["local_record_mode"] is True
    assert any(item["name"] == "GitHub App installation credentials" for item in body["integrations"])


def test_eval_run_requires_admin_or_owner_role(monkeypatch) -> None:
    enable_dev_header_auth(monkeypatch)
    client = TestClient(app)

    response = client.post(
        "/evals/run",
        json={"benchmark_version": "v1-local", "task_count": 1},
        headers=authenticated({"X-RepoPilot-Role": "viewer"}),
    )

    assert response.status_code == 403


def test_webhook_route_rejects_bad_signature() -> None:
    client = TestClient(app)
    body = json.dumps({"zen": "nope"}).encode("utf-8")

    response = client.post(
        "/webhooks/github",
        content=body,
        headers={
            "X-GitHub-Event": "issues",
            "X-GitHub-Delivery": "delivery-1",
            "X-Hub-Signature-256": "sha256=bad",
        },
    )

    assert response.status_code == 401
