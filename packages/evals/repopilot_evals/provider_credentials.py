from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from repopilot_llm_client import provider_by_id


RUNTIME_SECRET_STORE_ENV = "REPOPILOT_RUNTIME_SECRETS_STORE_PATH"
RUNTIME_SECRET_KEY_ENV = "REPOPILOT_RUNTIME_SECRETS_KEY"
RUNTIME_SECRET_KEY_PATH_ENV = "REPOPILOT_RUNTIME_SECRETS_KEY_PATH"


@dataclass(frozen=True)
class ProviderCredentialResolution:
    api_key: str | None
    base_url: str
    source: str


def resolve_provider_credentials(
    *,
    provider: str,
    api_key_env: str | None = None,
    base_url: str | None = None,
    allow_runtime_store: bool = True,
) -> ProviderCredentialResolution:
    normalized_provider = provider.strip().lower()
    selected_api_key_env = api_key_env or default_provider_api_key_env(normalized_provider)
    env_api_key = os.environ.get(selected_api_key_env)
    if env_api_key:
        return ProviderCredentialResolution(
            api_key=env_api_key,
            base_url=base_url or default_provider_base_url(normalized_provider),
            source=f"environment:{selected_api_key_env}",
        )

    runtime_values = load_runtime_secret_values() if allow_runtime_store else {}
    stored_provider = str(runtime_values.get("MODEL_PROVIDER") or "").strip().lower()
    store_matches_provider = not stored_provider or stored_provider == normalized_provider
    runtime_api_key = str(runtime_values.get("MODEL_API_KEY") or "").strip() if store_matches_provider else ""
    runtime_base_url = str(runtime_values.get("MODEL_BASE_URL") or "").strip() if store_matches_provider else ""
    return ProviderCredentialResolution(
        api_key=runtime_api_key or None,
        base_url=base_url or runtime_base_url or default_provider_base_url(normalized_provider),
        source="runtime_secret_store" if runtime_api_key else "missing",
    )


def load_runtime_secret_values() -> dict[str, str]:
    store_path = _expanded_path(os.environ.get(RUNTIME_SECRET_STORE_ENV) or "~/.repopilot/runtime-secrets.json")
    if not store_path.exists():
        return {}
    key = _runtime_secret_key()
    if not key:
        return {}
    try:
        payload = json.loads(store_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    encrypted_values = payload.get("values")
    if not isinstance(encrypted_values, dict):
        return {}
    try:
        from cryptography.fernet import Fernet, InvalidToken
    except ImportError:
        return {}
    fernet = Fernet(key)
    values: dict[str, str] = {}
    for name, encrypted in encrypted_values.items():
        if not isinstance(name, str) or not isinstance(encrypted, str):
            continue
        try:
            values[name] = fernet.decrypt(encrypted.encode("utf-8")).decode("utf-8")
        except (InvalidToken, ValueError):
            continue
    return values


def _runtime_secret_key() -> bytes | None:
    env_key = os.environ.get(RUNTIME_SECRET_KEY_ENV)
    if env_key:
        return env_key.encode("utf-8")
    key_path = _expanded_path(os.environ.get(RUNTIME_SECRET_KEY_PATH_ENV) or "~/.repopilot/runtime-secrets.key")
    if not key_path.exists():
        return None
    try:
        return key_path.read_bytes().strip()
    except OSError:
        return None


def _expanded_path(value: str) -> Path:
    return Path(value).expanduser()


def default_provider_base_url(provider: str) -> str:
    provider_option = provider_by_id(provider)
    if provider_option:
        return provider_option.default_base_url
    return "https://openrouter.ai/api/v1"


def default_provider_api_key_env(provider: str) -> str:
    normalized = provider.strip().lower()
    if normalized == "anthropic":
        return "ANTHROPIC_API_KEY"
    if normalized == "google":
        return "GEMINI_API_KEY"
    if normalized == "openrouter":
        return "OPENROUTER_API_KEY"
    return "MODEL_API_KEY"
