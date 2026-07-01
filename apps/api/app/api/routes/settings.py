from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, field_validator
from repopilot_contracts import RuntimeReadiness

from app.services.auth import CurrentUser, get_current_user
from app.services.github_app import GitHubAppTokenProvider, GitHubIntegrationError
from app.services.integration_readiness import IntegrationReadinessService
from app.services.model_catalog import (
    dynamic_model_by_id,
    dynamic_model_ids_for_provider,
    provider_by_id,
    provider_catalog_runtime,
)
from app.services.model_provider_verification import verify_model_provider
from app.services.policy import PolicyConfig
from app.services.runtime_secrets import (
    GITHUB_APP_RUNTIME_SECRET_FIELDS,
    GITHUB_OAUTH_RUNTIME_SECRET_FIELDS,
    MODEL_RUNTIME_SECRET_FIELDS,
    effective_settings,
    runtime_secret_store,
)
from app.services.security_envelope import rate_limit
from app.services.state_machine import ALLOWED_TRANSITIONS, TERMINAL_STATES
from app.services.url_safety import github_api_base_url as safe_github_api_base_url
from app.services.url_safety import github_web_base_url as safe_github_web_base_url
from app.services.url_safety import provider_base_url as safe_provider_base_url

router = APIRouter()


class GitHubOAuthConfigRequest(BaseModel):
    github_client_id: str = Field(min_length=1, max_length=256)
    github_client_secret: str = Field(min_length=1, max_length=2048)
    session_secret_key: str = Field(min_length=32, max_length=4096)
    github_oauth_callback_url: str = Field(min_length=1, max_length=2048)
    web_app_url: str = Field(min_length=1, max_length=2048)
    github_api_base_url: str = Field(default="https://api.github.com", min_length=1, max_length=2048)
    github_web_base_url: str = Field(default="https://github.com", min_length=1, max_length=2048)

    @field_validator("*", mode="before")
    @classmethod
    def strip_and_reject_control_chars(cls, value: object) -> object:
        if isinstance(value, str):
            cleaned = value.strip()
            if any(ord(char) < 32 for char in cleaned):
                raise ValueError("control characters are not allowed")
            return cleaned
        return value

    @field_validator("github_oauth_callback_url", "web_app_url", "github_api_base_url", "github_web_base_url")
    @classmethod
    def validate_http_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("must be an absolute http(s) URL")
        return value.rstrip("/")

    @field_validator("github_oauth_callback_url")
    @classmethod
    def validate_callback_path(cls, value: str) -> str:
        if not urlparse(value).path.endswith("/auth/github/callback"):
            raise ValueError("must point to /auth/github/callback")
        return value

    @field_validator("github_api_base_url")
    @classmethod
    def validate_github_api_base_url(cls, value: str) -> str:
        return safe_github_api_base_url(value)

    @field_validator("github_web_base_url")
    @classmethod
    def validate_github_web_base_url(cls, value: str) -> str:
        return safe_github_web_base_url(value)

    @field_validator("session_secret_key")
    @classmethod
    def validate_session_secret(cls, value: str) -> str:
        lowered = value.lower()
        if lowered.startswith("change-me") or lowered in {"placeholder", "todo", "secret"}:
            raise ValueError("must be a real high-entropy value")
        return value


class GitHubAppConfigRequest(BaseModel):
    github_webhook_secret: str | None = Field(default=None, min_length=16, max_length=4096)
    github_app_id: str = Field(min_length=1, max_length=64)
    github_app_slug: str | None = Field(default=None, max_length=256)
    github_private_key: str | None = Field(default=None, max_length=20000)
    github_private_key_path: str | None = Field(default=None, max_length=2048)
    github_installation_id: str | None = Field(default=None, max_length=64)

    @field_validator(
        "github_webhook_secret",
        "github_app_id",
        "github_app_slug",
        "github_private_key_path",
        "github_installation_id",
        mode="before",
    )
    @classmethod
    def strip_and_reject_control_chars(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned == "":
                return None
            if any(ord(char) < 32 for char in cleaned):
                raise ValueError("control characters are not allowed")
            return cleaned
        return value

    @field_validator("github_private_key", mode="before")
    @classmethod
    def normalize_private_key(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned.replace("\\n", "\n") if cleaned else None
        return value

class ModelProviderConfigRequest(BaseModel):
    provider: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=256)
    model_api_key: str | None = Field(default=None, max_length=8192)
    model_base_url: str | None = Field(default=None, max_length=2048)
    model_reasoning_level: str | None = Field(default=None, max_length=32)

    @field_validator("*", mode="before")
    @classmethod
    def strip_and_reject_control_chars(cls, value: object) -> object:
        if isinstance(value, str):
            cleaned = value.strip()
            if any(ord(char) < 32 for char in cleaned):
                raise ValueError("control characters are not allowed")
            return cleaned
        return value

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, value: str) -> str:
        normalized = value.lower()
        if not provider_by_id(normalized):
            raise ValueError("unsupported model provider")
        return normalized

    @field_validator("model")
    @classmethod
    def reject_model_placeholders(cls, value: str) -> str:
        lowered = value.lower()
        if lowered in {"placeholder", "todo", "mock-planner"} or lowered.startswith("change-me"):
            raise ValueError("must be a real provider model id")
        return value

    @field_validator("model_api_key")
    @classmethod
    def validate_model_api_key(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        lowered = value.lower()
        if lowered in {"placeholder", "todo", "secret", "api-key"} or lowered.startswith("change-me"):
            raise ValueError("must be a real provider API key")
        return value

    @field_validator("model_base_url")
    @classmethod
    def validate_model_base_url(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("must be an absolute https URL")
        if parsed.username or parsed.password:
            raise ValueError("must not include credentials")
        return value.rstrip("/")

    @field_validator("model_reasoning_level")
    @classmethod
    def validate_reasoning_level_shape(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        normalized = value.lower()
        if normalized not in {"none", "off", "auto", "adaptive", "minimal", "low", "medium", "high", "max"}:
            raise ValueError("unsupported reasoning level")
        return normalized


@router.get("/readiness", response_model=RuntimeReadiness)
async def runtime_readiness() -> dict[str, object]:
    return IntegrationReadinessService().readiness().model_dump(mode="json")


@router.get("/github/oauth")
async def github_oauth_config_status(current_user: CurrentUser = Depends(get_current_user)) -> dict[str, object]:
    _require_owner(current_user)
    return runtime_secret_store().summary(set(GITHUB_OAUTH_RUNTIME_SECRET_FIELDS))


@router.post("/github/oauth")
async def save_github_oauth_config(
    request: GitHubOAuthConfigRequest,
    current_user: CurrentUser = Depends(get_current_user),
    x_repopilot_intent: str | None = Header(default=None),
) -> dict[str, object]:
    _require_owner(current_user)
    if x_repopilot_intent != "save-oauth-secrets":
        raise HTTPException(status_code=400, detail="Missing explicit secret-save intent header.")
    runtime_secret_store().save_values(
        {
            "GITHUB_CLIENT_ID": request.github_client_id,
            "GITHUB_CLIENT_SECRET": request.github_client_secret,
            "GITHUB_OAUTH_CALLBACK_URL": request.github_oauth_callback_url,
            "WEB_APP_URL": request.web_app_url,
            "SESSION_SECRET_KEY": request.session_secret_key,
            "GITHUB_API_BASE_URL": request.github_api_base_url,
            "GITHUB_WEB_BASE_URL": request.github_web_base_url,
        }
    )
    return runtime_secret_store().summary(set(GITHUB_OAUTH_RUNTIME_SECRET_FIELDS))


@router.get("/github/app")
async def github_app_config_status(current_user: CurrentUser = Depends(get_current_user)) -> dict[str, object]:
    _require_owner(current_user)
    return runtime_secret_store().summary(set(GITHUB_APP_RUNTIME_SECRET_FIELDS))


@router.post("/github/app")
async def save_github_app_config(
    request: GitHubAppConfigRequest,
    current_user: CurrentUser = Depends(get_current_user),
    x_repopilot_intent: str | None = Header(default=None),
) -> dict[str, object]:
    _require_owner(current_user)
    if x_repopilot_intent != "save-github-app-secrets":
        raise HTTPException(status_code=400, detail="Missing explicit GitHub App secret-save intent header.")
    values = {
        "GITHUB_APP_ID": request.github_app_id,
    }
    optional_values = {
        "GITHUB_WEBHOOK_SECRET": request.github_webhook_secret,
        "GITHUB_APP_SLUG": request.github_app_slug,
        "GITHUB_APP_PRIVATE_KEY": request.github_private_key,
        "GITHUB_PRIVATE_KEY_PATH": request.github_private_key_path,
        "GITHUB_INSTALLATION_ID": request.github_installation_id,
    }
    values.update({key: value for key, value in optional_values.items() if value})
    store = runtime_secret_store()
    store.delete_values({"GITHUB_APP_VERIFIED_AT", "GITHUB_APP_VERIFIED_INSTALLATION_ID", "GITHUB_WRITE_SMOKE_VERIFIED_AT"})
    store.save_values(values)
    return store.summary(set(GITHUB_APP_RUNTIME_SECRET_FIELDS))


@router.post("/github/app/verify")
async def verify_github_app_config(
    _rate_limit: None = Depends(rate_limit("github-app-verify", limit_attr="rate_limit_expensive_per_minute")),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, object]:
    _require_owner(current_user)
    effective = effective_settings()
    if not _configured_value(effective.github_app_id):
        raise HTTPException(status_code=409, detail="Save GITHUB_APP_ID before verification.")
    if not (_configured_value(effective.github_private_key) or _configured_value(effective.github_private_key_path)):
        raise HTTPException(status_code=409, detail="Save a GitHub App private key or private key path before verification.")
    if not _configured_value(effective.github_installation_id):
        raise HTTPException(status_code=409, detail="Save GITHUB_INSTALLATION_ID before verification.")
    try:
        token = await GitHubAppTokenProvider(effective).create_installation_access_token(effective.github_installation_id or "")
    except GitHubIntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    verified_at = datetime.now(UTC).isoformat()
    runtime_secret_store().save_values(
        {
            "GITHUB_APP_VERIFIED_AT": verified_at,
            "GITHUB_APP_VERIFIED_INSTALLATION_ID": effective.github_installation_id or "",
        }
    )
    return {
        "ok": True,
        "status": "verified",
        "checked_at": verified_at,
        "installation_id": effective.github_installation_id,
        "token_received": bool(token),
        "detail": "GitHub App installation token was created successfully.",
    }


@router.get("/models/catalog")
async def model_provider_catalog(current_user: CurrentUser = Depends(get_current_user)) -> dict[str, object]:
    _require_owner(current_user)
    effective = effective_settings()
    return await provider_catalog_runtime(
        timeout_seconds=effective.model_request_timeout_seconds,
        preferred_provider_id=effective.model_provider,
        preferred_api_key=effective.model_api_key,
        preferred_base_url=effective.model_base_url,
    )


@router.get("/models/config")
async def model_provider_config(current_user: CurrentUser = Depends(get_current_user)) -> dict[str, object]:
    _require_owner(current_user)
    # codeql[py/stack-trace-exposure]
    # lgtm[py/stack-trace-exposure]
    # _safe_model_provider_status converts provider/runtime failures into sanitized status fields.
    return await _safe_model_provider_status()


@router.post("/models/config")
async def save_model_provider_config(
    request: ModelProviderConfigRequest,
    current_user: CurrentUser = Depends(get_current_user),
    x_repopilot_intent: str | None = Header(default=None),
) -> dict[str, object]:
    _require_owner(current_user)
    if x_repopilot_intent != "save-model-provider":
        raise HTTPException(status_code=400, detail="Missing explicit model-provider save intent header.")
    provider = provider_by_id(request.provider)
    if not provider:
        raise HTTPException(status_code=422, detail="Unsupported model provider.")
    effective = effective_settings()
    try:
        model_base_url = _provider_base_url(provider=provider, value=request.model_base_url or provider.default_base_url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    available_models = await dynamic_model_ids_for_provider(
        provider_id=request.provider,
        timeout_seconds=effective.model_request_timeout_seconds,
        api_key=request.model_api_key or (effective.model_api_key if effective.model_provider == request.provider else None),
        base_url=model_base_url,
    )
    if request.model not in available_models:
        raise HTTPException(status_code=422, detail="Selected model is not available for the selected provider.")
    selected_model = await dynamic_model_by_id(
        provider_id=request.provider,
        model_id=request.model,
        timeout_seconds=effective.model_request_timeout_seconds,
        api_key=request.model_api_key or (effective.model_api_key if effective.model_provider == request.provider else None),
        base_url=model_base_url,
    )
    reasoning_levels = tuple(str(level) for level in (selected_model.get("reasoning_levels", ()) if selected_model else ()))
    if request.model_reasoning_level and request.model_reasoning_level not in reasoning_levels:
        raise HTTPException(status_code=422, detail="Selected reasoning level is not available for the selected model.")
    values = {
        "MODEL_PROVIDER": request.provider,
        "MODEL_NAME": request.model,
        "MODEL_BASE_URL": model_base_url,
    }
    if request.model_reasoning_level:
        values["MODEL_REASONING_LEVEL"] = request.model_reasoning_level
    if request.model_api_key:
        values["MODEL_API_KEY"] = request.model_api_key
    store = runtime_secret_store()
    store.delete_values({"MODEL_PROVIDER_VERIFIED_AT", "MODEL_PROVIDER_VERIFIED_MODEL"})
    store.save_values(values)
    # codeql[py/stack-trace-exposure]
    # lgtm[py/stack-trace-exposure]
    # _safe_model_provider_status converts provider/runtime failures into sanitized status fields.
    return await _safe_model_provider_status()


@router.post("/models/verify")
async def verify_model_provider_config(
    _rate_limit: None = Depends(rate_limit("model-verify", limit_attr="rate_limit_expensive_per_minute")),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, object]:
    _require_owner(current_user)
    effective = effective_settings()
    provider = provider_by_id(effective.model_provider)
    available_models = await dynamic_model_ids_for_provider(
        provider_id=effective.model_provider,
        timeout_seconds=effective.model_request_timeout_seconds,
        api_key=effective.model_api_key,
        base_url=effective.model_base_url or (provider.default_base_url if provider else None),
    )
    if not provider or effective.model_name not in available_models:
        raise HTTPException(status_code=409, detail="Select a supported provider and model before verification.")
    if not _configured_value(effective.model_api_key):
        raise HTTPException(status_code=409, detail="Save a provider API key before verification.")
    try:
        base_url = _provider_base_url(provider=provider, value=effective.model_base_url or provider.default_base_url)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    result = await verify_model_provider(
        provider=provider,
        model=effective.model_name,
        api_key=effective.model_api_key or "",
        base_url=base_url,
        timeout_seconds=effective.model_request_timeout_seconds,
    )
    if result.ok:
        runtime_secret_store().save_values(
            {
                "MODEL_PROVIDER_VERIFIED_AT": result.checked_at,
                "MODEL_PROVIDER_VERIFIED_MODEL": f"{provider.id}:{effective.model_name}",
            }
        )
    return result.as_dict()


@router.get("/policy")
async def runtime_policy() -> dict[str, object]:
    config = PolicyConfig()
    return {
        "max_files_changed_without_approval": config.max_files_changed_without_approval,
        "max_commands_without_approval": config.max_commands_without_approval,
        "high_risk_patterns": list(config.high_risk_patterns),
        "allowed_commands": list(config.allowed_commands),
        "blocked_command_fragments": list(config.blocked_command_fragments),
    }


@router.get("/state-machine")
async def state_machine() -> dict[str, object]:
    return {
        "allowed_transitions": {state: sorted(next_states) for state, next_states in ALLOWED_TRANSITIONS.items()},
        "terminal_states": sorted(TERMINAL_STATES),
    }


def _require_owner(current_user: CurrentUser) -> None:
    if current_user.role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Only workspace owners can manage runtime secrets.")


async def _model_provider_status() -> dict[str, object]:
    store = runtime_secret_store()
    summary = store.summary(set(MODEL_RUNTIME_SECRET_FIELDS))
    effective = effective_settings()
    provider = provider_by_id(effective.model_provider)
    selected_model: dict[str, object] | None = None
    catalog_available = True
    safe_base_url = effective.model_base_url or (provider.default_base_url if provider else None)
    try:
        selected_model = await dynamic_model_by_id(
            provider_id=effective.model_provider,
            model_id=effective.model_name,
            timeout_seconds=effective.model_request_timeout_seconds,
            api_key=effective.model_api_key,
            base_url=safe_base_url,
        )
    except Exception:  # noqa: BLE001 - settings status must not expose provider/backend exception detail.
        catalog_available = False
    configured_model = False
    if provider:
        try:
            available_models = await dynamic_model_ids_for_provider(
                provider_id=effective.model_provider,
                timeout_seconds=effective.model_request_timeout_seconds,
                api_key=effective.model_api_key,
                base_url=safe_base_url or provider.default_base_url,
            )
            configured_model = effective.model_name in available_models
        except Exception:  # noqa: BLE001 - settings status must not expose provider/backend exception detail.
            catalog_available = False
    api_key_configured = _configured_value(effective.model_api_key)
    reasoning_levels = [str(level) for level in (selected_model.get("reasoning_levels", ()) if selected_model else ())]
    reasoning_level = effective.model_reasoning_level if effective.model_reasoning_level in reasoning_levels else None
    return {
        "provider": effective.model_provider,
        "provider_name": provider.name if provider else effective.model_provider,
        "model": effective.model_name,
        "model_configured": configured_model,
        "api_key_configured": api_key_configured,
        "base_url": effective.model_base_url or (provider.default_base_url if provider else None),
        "reasoning_level": reasoning_level,
        "reasoning_levels": reasoning_levels,
        "reasoning_supported": bool(reasoning_levels),
        "docs_url": provider.docs_url if provider else None,
        "verified": (
            configured_model
            and api_key_configured
            and effective.model_provider_verified_model == f"{effective.model_provider}:{effective.model_name}"
            and _configured_value(effective.model_provider_verified_at)
        ),
        "verified_at": effective.model_provider_verified_at
        if effective.model_provider_verified_model == f"{effective.model_provider}:{effective.model_name}"
        else None,
        "status": "configured" if configured_model and api_key_configured else "missing",
        "catalog_available": catalog_available,
        "summary": summary,
    }


async def _safe_model_provider_status() -> dict[str, object]:
    try:
        return await _model_provider_status()
    except Exception:  # noqa: BLE001 - status endpoints must never expose provider/runtime stack traces.
        effective = effective_settings()
        provider = provider_by_id(effective.model_provider)
        return {
            "provider": effective.model_provider,
            "provider_name": provider.name if provider else effective.model_provider,
            "model": effective.model_name,
            "model_configured": False,
            "api_key_configured": _configured_value(effective.model_api_key),
            "base_url": effective.model_base_url or (provider.default_base_url if provider else None),
            "reasoning_level": None,
            "reasoning_levels": [],
            "reasoning_supported": False,
            "docs_url": provider.docs_url if provider else None,
            "verified": False,
            "verified_at": None,
            "status": "unavailable",
            "catalog_available": False,
            "summary": {"fields": [], "store_exists": False, "store_permissions_ok": False, "key_permissions_ok": False},
        }


def _configured_value(value: str | None) -> bool:
    if value is None:
        return False
    normalized = str(value).strip().lower()
    return bool(normalized) and normalized not in {"placeholder", "todo", "secret"} and not normalized.startswith("change-me")


def _provider_base_url(*, provider: object, value: str) -> str:
    return safe_provider_base_url(
        value,
        default_base_url=str(getattr(provider, "default_base_url", "")),
        provider_id=str(getattr(provider, "id", "model provider")),
    )
