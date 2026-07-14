from __future__ import annotations

import json

from app.core.config import Settings
from app.services.runtime_secrets import (
    RuntimeSecretStore,
    configured_model_api_key_providers,
    effective_settings,
    model_api_key_for_provider,
)


def test_runtime_secret_cache_avoids_repeated_decryption_and_invalidates_on_write(tmp_path, monkeypatch) -> None:
    config = Settings(
        REPOPILOT_RUNTIME_SECRETS_STORE_PATH=str(tmp_path / "runtime-secrets.json"),
        REPOPILOT_RUNTIME_SECRETS_KEY_PATH=str(tmp_path / "runtime-secrets.key"),
    )
    store = RuntimeSecretStore(config)
    RuntimeSecretStore._value_cache.clear()
    store.save_values({"GITHUB_CLIENT_SECRET": "client-secret-value"})
    persisted = json.loads((tmp_path / "runtime-secrets.json").read_text(encoding="utf-8"))
    assert "client-secret-value" not in json.dumps(persisted)

    RuntimeSecretStore._value_cache.clear()
    calls = 0
    original_read = store._read_store

    def counted_read():
        nonlocal calls
        calls += 1
        return original_read()

    monkeypatch.setattr(store, "_read_store", counted_read)
    assert store.load_values()["GITHUB_CLIENT_SECRET"] == "client-secret-value"
    assert store.load_values()["GITHUB_CLIENT_SECRET"] == "client-secret-value"
    assert calls == 1

    store.delete_values({"GITHUB_CLIENT_SECRET"})
    assert store.load_values()["GITHUB_CLIENT_SECRET"] == ""
    assert (tmp_path / "runtime-secrets.json").stat().st_mode & 0o077 == 0
    assert (tmp_path / "runtime-secrets.key").stat().st_mode & 0o077 == 0


def test_model_api_key_is_available_only_to_its_bound_provider(tmp_path) -> None:
    config = Settings(
        MODEL_PROVIDER="openrouter",
        MODEL_NAME="openrouter/free",
        REPOPILOT_RUNTIME_SECRETS_STORE_PATH=str(tmp_path / "runtime-secrets.json"),
        REPOPILOT_RUNTIME_SECRETS_KEY_PATH=str(tmp_path / "runtime-secrets.key"),
    )
    store = RuntimeSecretStore(config)
    store.save_values(
        {
            "MODEL_PROVIDER": "openrouter",
            "MODEL_NAME": "openrouter/free",
            "MODEL_API_KEY": "sk-openrouter-runtime-key",
            "MODEL_API_KEY_PROVIDER": "openrouter",
        }
    )

    assert model_api_key_for_provider("openrouter", config) == "sk-openrouter-runtime-key"
    assert model_api_key_for_provider("anthropic", config) is None
    assert configured_model_api_key_providers(config) == ("openrouter",)
    assert effective_settings(config).model_api_key == "sk-openrouter-runtime-key"

    store.save_values({"MODEL_PROVIDER": "anthropic", "MODEL_NAME": "claude-sonnet-4-6"})
    switched = effective_settings(config)

    assert switched.model_provider == "anthropic"
    assert switched.model_api_key is None
    assert switched.model_api_key_provider == "openrouter"
    assert model_api_key_for_provider("openrouter", config) == "sk-openrouter-runtime-key"
