from __future__ import annotations

from app.core.config import Settings
from app.services.integration_readiness import IntegrationReadinessService


def production_ready_settings(**overrides):
    values = {
        "environment": "production",
        "release_profile": "production",
        "github_webhook_secret": "live-webhook-secret",
        "github_app_id": "12345",
        "github_private_key": "runtime-private-key",
        "github_installation_id": "67890",
        "github_app_verified_at": "2026-06-11T00:00:00+00:00",
        "github_app_verified_installation_id": "67890",
        "github_writes_enabled": True,
        "github_write_smoke_verified_at": "2026-06-11T00:00:00+00:00",
        "github_client_id": "client-id",
        "github_client_secret": "client-secret",
        "session_secret_key": "session-secret-session-secret-session-secret",
        "runtime_secrets_key": "runtime-secret-key-material",
        "model_provider": "openai",
        "model_name": "gpt-5.5",
        "model_api_key": "provider-key",
        "model_provider_verified_model": "openai:gpt-5.5",
        "model_provider_verified_at": "2026-06-11T00:00:00+00:00",
        "semgrep_enabled": True,
        "codeql_enabled": True,
        "dependency_audit_enabled": True,
    }
    values.update(overrides)
    return Settings().model_copy(update=values)


def integration_mode(readiness, name: str) -> str | None:
    return next(item.mode for item in readiness.integrations if item.name == name)


def integration(readiness, name: str):
    return next(item for item in readiness.integrations if item.name == name)


def test_production_profile_blocks_local_record_mode() -> None:
    readiness = IntegrationReadinessService(
        production_ready_settings(github_writes_enabled=False, github_write_smoke_verified_at=None)
    ).readiness()

    assert readiness.production_ready is False
    assert readiness.release_profile == "production"
    assert readiness.local_record_mode is True
    assert integration_mode(readiness, "GitHub write mode") == "local_record_mode"
    assert any("GitHub write mode" in blocker for blocker in readiness.blockers)


def test_nonlocal_readiness_blocks_managed_runtime_secret_key() -> None:
    readiness = IntegrationReadinessService(production_ready_settings(runtime_secrets_key=None)).readiness()

    assert readiness.production_ready is False
    assert integration_mode(readiness, "Runtime secret key") == "managed_file_key_nonlocal"
    assert any("Runtime secret key" in blocker for blocker in readiness.blockers)


def test_local_readiness_allows_managed_runtime_secret_key() -> None:
    readiness = IntegrationReadinessService(
        production_ready_settings(environment="local", runtime_secrets_key=None)
    ).readiness()

    runtime_secret = next(item for item in readiness.integrations if item.name == "Runtime secret key")
    assert runtime_secret.mode == "managed_file_allowed_local"
    assert runtime_secret.required_for_production is False
    assert "Runtime secret key" not in " ".join(readiness.blockers)


def test_nonlocal_readiness_blocks_enabled_model_fallback() -> None:
    readiness = IntegrationReadinessService(production_ready_settings(allow_model_fallback=True)).readiness()

    assert readiness.production_ready is False
    assert integration_mode(readiness, "Model fallback policy") == "fallback_enabled_nonlocal"
    assert any("Model fallback policy" in blocker for blocker in readiness.blockers)


def test_live_embedding_source_transfer_disabled_is_visible_but_not_a_blocker() -> None:
    readiness = IntegrationReadinessService(
        production_ready_settings(
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
            embedding_source_transfer_enabled=False,
        )
    ).readiness()

    policy = integration(readiness, "Embedding source transfer policy")
    assert policy.mode == "source_transfer_disabled"
    assert policy.required_for_production is False
    assert "source chunks stay local" in policy.detail
    assert not any("Embedding source transfer policy" in blocker for blocker in readiness.blockers)


def test_live_embedding_source_transfer_opt_in_is_visible() -> None:
    readiness = IntegrationReadinessService(
        production_ready_settings(
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
            embedding_source_transfer_enabled=True,
        )
    ).readiness()

    policy = integration(readiness, "Embedding source transfer policy")
    assert policy.mode == "source_transfer_enabled"
    assert policy.required_for_production is False
    assert "may send repository file paths" in policy.detail
