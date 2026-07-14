from __future__ import annotations

import json
import os
import tempfile
import threading
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, ClassVar

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import Settings, settings


GITHUB_OAUTH_RUNTIME_SECRET_FIELDS = {
    "GITHUB_CLIENT_ID": "github_client_id",
    "GITHUB_CLIENT_SECRET": "github_client_secret",
    "REPOPILOT_GITHUB_OWNER_LOGIN": "github_owner_login",
    "GITHUB_OAUTH_CALLBACK_URL": "github_oauth_callback_url",
    "WEB_APP_URL": "web_app_url",
    "SESSION_SECRET_KEY": "session_secret_key",
    "GITHUB_API_BASE_URL": "github_api_base_url",
    "GITHUB_WEB_BASE_URL": "github_web_base_url",
}

GITHUB_APP_RUNTIME_SECRET_FIELDS = {
    "GITHUB_WEBHOOK_SECRET": "github_webhook_secret",
    "GITHUB_APP_ID": "github_app_id",
    "GITHUB_APP_SLUG": "github_app_slug",
    "GITHUB_APP_PRIVATE_KEY": "github_private_key",
    "GITHUB_PRIVATE_KEY_PATH": "github_private_key_path",
    "GITHUB_INSTALLATION_ID": "github_installation_id",
    "GITHUB_APP_VERIFIED_AT": "github_app_verified_at",
    "GITHUB_APP_VERIFIED_INSTALLATION_ID": "github_app_verified_installation_id",
    "GITHUB_WRITE_SMOKE_VERIFIED_AT": "github_write_smoke_verified_at",
}

GITHUB_RUNTIME_SECRET_FIELDS = {
    **GITHUB_OAUTH_RUNTIME_SECRET_FIELDS,
    **GITHUB_APP_RUNTIME_SECRET_FIELDS,
}

MODEL_RUNTIME_SECRET_FIELDS = {
    "MODEL_PROVIDER": "model_provider",
    "MODEL_NAME": "model_name",
    "MODEL_API_KEY": "model_api_key",
    "MODEL_API_KEY_PROVIDER": "model_api_key_provider",
    "MODEL_BASE_URL": "model_base_url",
    "MODEL_REASONING_LEVEL": "model_reasoning_level",
    "MODEL_PROVIDER_VERIFIED_AT": "model_provider_verified_at",
    "MODEL_PROVIDER_VERIFIED_MODEL": "model_provider_verified_model",
}

RUNTIME_SECRET_FIELDS = {
    **GITHUB_RUNTIME_SECRET_FIELDS,
    **MODEL_RUNTIME_SECRET_FIELDS,
}

SECRET_FIELD_NAMES = {
    "GITHUB_CLIENT_SECRET",
    "SESSION_SECRET_KEY",
    "GITHUB_WEBHOOK_SECRET",
    "GITHUB_APP_PRIVATE_KEY",
    "MODEL_API_KEY",
}
PLACEHOLDER_VALUES = {"", "placeholder", "todo", "secret", "change-me", "change_me"}


@dataclass(frozen=True)
class RuntimeSecretField:
    name: str
    configured: bool
    secret: bool
    source: str


class RuntimeSecretStore:
    _value_cache: ClassVar[dict[tuple[object, ...], dict[str, str]]] = {}
    _cache_lock: ClassVar[threading.RLock] = threading.RLock()

    def __init__(self, config: Settings | None = None) -> None:
        self.config = config or settings

    def load_values(self) -> dict[str, str]:
        cache_key = self._cache_signature()
        with self._cache_lock:
            cached = self._value_cache.get(cache_key)
            if cached is not None:
                return dict(cached)
        data = self._read_store()
        encrypted_values = data.get("values", {})
        if not isinstance(encrypted_values, dict):
            encrypted_values = {}
        cleared_values = data.get("cleared", [])
        cleared = {
            key
            for key in cleared_values
            if isinstance(key, str) and key in RUNTIME_SECRET_FIELDS
        } if isinstance(cleared_values, list) else set()
        fernet = self._fernet()
        values: dict[str, str] = {}
        for key, encrypted in encrypted_values.items():
            if key not in RUNTIME_SECRET_FIELDS or not isinstance(encrypted, str):
                continue
            try:
                values[key] = fernet.decrypt(encrypted.encode("utf-8")).decode("utf-8")
            except (InvalidToken, ValueError):
                continue
        for key in cleared:
            values.setdefault(key, "")
        with self._cache_lock:
            if len(self._value_cache) >= 32:
                self._value_cache.clear()
            self._value_cache[cache_key] = dict(values)
        return values

    def save_values(self, values: dict[str, str]) -> None:
        clean_values = {key: value.strip() for key, value in values.items() if key in RUNTIME_SECRET_FIELDS and value.strip()}
        current = self.load_values()
        current.update(clean_values)
        cleared = self._cleared_values() - set(clean_values)
        self._write_values(current, cleared=cleared)

    def delete_values(self, keys: set[str]) -> None:
        valid_keys = {key for key in keys if key in RUNTIME_SECRET_FIELDS}
        if not valid_keys:
            return
        current = self.load_values()
        for key in valid_keys:
            current.pop(key, None)
        self._write_values(current, cleared=self._cleared_values() | valid_keys)

    def _write_values(self, values: dict[str, str], *, cleared: set[str] | None = None) -> None:
        clean_values = {key: value.strip() for key, value in values.items() if key in RUNTIME_SECRET_FIELDS and value.strip()}
        clean_cleared = sorted((cleared or set()) - set(clean_values))
        fernet = self._fernet()
        encrypted = {
            key: fernet.encrypt(value.encode("utf-8")).decode("utf-8")
            for key, value in sorted(clean_values.items())
        }
        payload = {
            "version": 1,
            "updated_at": datetime.now(UTC).isoformat(),
            "values": encrypted,
        }
        if clean_cleared:
            payload["cleared"] = clean_cleared
        self._atomic_write(self._store_path(), json.dumps(payload, sort_keys=True, indent=2).encode("utf-8"))
        self._invalidate_cache()

    def summary(self, field_names: set[str] | None = None) -> dict[str, Any]:
        stored = self.load_values()
        fields = []
        effective = effective_settings(self.config)
        selected_fields = field_names or set(RUNTIME_SECRET_FIELDS)
        for env_name, attr_name in RUNTIME_SECRET_FIELDS.items():
            if env_name not in selected_fields:
                continue
            value = getattr(effective, attr_name)
            stored_configured = bool(stored.get(env_name))
            fields.append(
                RuntimeSecretField(
                    name=env_name,
                    configured=self._configured_value(value),
                    secret=env_name in SECRET_FIELD_NAMES,
                    source="encrypted_store" if stored_configured else "environment",
                ).__dict__
            )
        store_path = self._store_path()
        key_path = self._key_path()
        return {
            "fields": fields,
            "encrypted": True,
            "store_exists": store_path.exists(),
            "key_source": "environment" if self.config.runtime_secrets_key else "managed_file",
            "store_permissions_ok": self._permissions_ok(store_path) if store_path.exists() else True,
            "key_permissions_ok": True if self.config.runtime_secrets_key or not key_path.exists() else self._permissions_ok(key_path),
            "updated_at": self._read_store().get("updated_at"),
        }

    def _read_store(self) -> dict[str, Any]:
        path = self._store_path()
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _cleared_values(self) -> set[str]:
        cleared = self._read_store().get("cleared", [])
        if not isinstance(cleared, list):
            return set()
        return {key for key in cleared if isinstance(key, str) and key in RUNTIME_SECRET_FIELDS}

    def _fernet(self) -> Fernet:
        return Fernet(self._key_material())

    def _key_material(self) -> bytes:
        if self.config.runtime_secrets_key:
            return self.config.runtime_secrets_key.encode("utf-8")
        path = self._key_path()
        if path.exists():
            key = path.read_bytes().strip()
            self._harden_permissions(path)
            return key
        key = Fernet.generate_key()
        self._atomic_write(path, key + b"\n")
        return key

    def _store_path(self) -> Path:
        return Path(self.config.runtime_secrets_store_path).expanduser()

    def _key_path(self) -> Path:
        return Path(self.config.runtime_secrets_key_path).expanduser()

    def _cache_signature(self) -> tuple[object, ...]:
        store_path = self._store_path()
        key_path = self._key_path()
        key_digest = sha256((self.config.runtime_secrets_key or "").encode("utf-8")).hexdigest()
        return (
            str(store_path.resolve(strict=False)),
            *_file_signature(store_path),
            str(key_path.resolve(strict=False)),
            *_file_signature(key_path),
            key_digest,
        )

    def _invalidate_cache(self) -> None:
        store_path = str(self._store_path().resolve(strict=False))
        with self._cache_lock:
            stale = [key for key in self._value_cache if key and key[0] == store_path]
            for key in stale:
                self._value_cache.pop(key, None)

    def _atomic_write(self, path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temp_name, 0o600)
            os.replace(temp_name, path)
            self._harden_permissions(path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def _harden_permissions(self, path: Path) -> None:
        with suppress(OSError):
            os.chmod(path, 0o600)

    def _permissions_ok(self, path: Path) -> bool:
        if os.name == "nt":
            return True
        try:
            return (path.stat().st_mode & 0o077) == 0
        except OSError:
            return False

    def _configured_value(self, value: str | None) -> bool:
        if value is None:
            return False
        normalized = str(value).strip().lower()
        return bool(normalized) and normalized not in PLACEHOLDER_VALUES and not normalized.startswith("change-me")


def runtime_secret_store(config: Settings | None = None) -> RuntimeSecretStore:
    return RuntimeSecretStore(config or settings)


def model_api_key_for_provider(provider_id: str, config: Settings | None = None) -> str | None:
    base = config or settings
    stored = _load_runtime_values(base)
    return _configured_model_api_keys(base, stored).get(_normalized_provider_id(provider_id))


def configured_model_api_key_providers(config: Settings | None = None) -> tuple[str, ...]:
    base = config or settings
    stored = _load_runtime_values(base)
    return tuple(sorted(_configured_model_api_keys(base, stored)))


def effective_settings(config: Settings | None = None) -> Settings:
    base = config or settings
    stored = _load_runtime_values(base)
    updates = {
        attr_name: stored[env_name]
        for env_name, attr_name in RUNTIME_SECRET_FIELDS.items()
        if env_name in stored
    }
    configured_keys = _configured_model_api_keys(base, stored)
    active_provider = _normalized_provider_id(updates.get("model_provider", base.model_provider))
    updates["model_api_key"] = configured_keys.get(active_provider)
    updates["model_api_key_provider"] = next(iter(configured_keys), None)
    return base.model_copy(update=updates)


def _load_runtime_values(config: Settings) -> dict[str, str]:
    try:
        return RuntimeSecretStore(config).load_values()
    except Exception:
        return {}


def _configured_model_api_keys(config: Settings, stored: dict[str, str]) -> dict[str, str]:
    if "MODEL_API_KEY" in stored:
        api_key = stored.get("MODEL_API_KEY")
        provider_id = (
            stored.get("MODEL_API_KEY_PROVIDER")
            or stored.get("MODEL_PROVIDER")
            or config.model_api_key_provider
            or config.model_provider
        )
    else:
        api_key = config.model_api_key
        provider_id = stored.get("MODEL_API_KEY_PROVIDER") or config.model_api_key_provider or config.model_provider
    normalized_provider = _normalized_provider_id(provider_id)
    if not normalized_provider or not _configured_runtime_value(api_key):
        return {}
    return {normalized_provider: str(api_key).strip()}


def _normalized_provider_id(value: object) -> str:
    return str(value or "").strip().lower()


def _configured_runtime_value(value: object) -> bool:
    normalized = str(value or "").strip().lower()
    return bool(normalized) and normalized not in PLACEHOLDER_VALUES and not normalized.startswith("change-me")


def _file_signature(path: Path) -> tuple[int, int]:
    try:
        stat = path.stat()
    except OSError:
        return 0, 0
    return stat.st_mtime_ns, stat.st_size
