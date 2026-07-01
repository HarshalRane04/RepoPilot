from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from time import monotonic
from typing import Any
from urllib.parse import urlparse

import httpx
from repopilot_llm_client import (
    MODEL_PROVIDERS,
    ModelOption,
    ModelProviderOption,
    model_by_id,
    model_ids_for_provider,
    provider_by_id,
    provider_catalog,
)

from app.services.url_safety import provider_base_url as safe_provider_base_url

OPENROUTER_PROVIDER_ID = "openrouter"
DYNAMIC_MODEL_CACHE_TTL_SECONDS = 300

_dynamic_cache_lock = asyncio.Lock()
_dynamic_model_cache: dict[tuple[str, bool, str], dict[str, object]] = {}


async def provider_catalog_runtime(
    *,
    timeout_seconds: int = 10,
    preferred_provider_id: str | None = None,
    preferred_api_key: str | None = None,
    preferred_base_url: str | None = None,
) -> dict[str, object]:
    providers = [asdict(provider) for provider in MODEL_PROVIDERS]
    preferred_provider = (preferred_provider_id or "").strip().lower()
    tasks = [
        _provider_catalog_entry(
            provider=provider,
            timeout_seconds=timeout_seconds,
            api_key=preferred_api_key if provider.id == preferred_provider else None,
            base_url=preferred_base_url if provider.id == preferred_provider else None,
        )
        for provider in MODEL_PROVIDERS
    ]
    resolved = await asyncio.gather(*tasks)
    resolved_by_id = {item["id"]: item for item in resolved}

    for provider in providers:
        provider_id = str(provider.get("id", ""))
        item = resolved_by_id.get(provider_id)
        if not item:
            continue
        provider["models"] = item["models"]
        provider["model_source"] = item["source"]
        provider["models_fetched_at"] = item["fetched_at"]
        if item.get("error"):
            provider["model_fetch_error"] = item["error"]

    return {"providers": providers}


async def dynamic_model_ids_for_provider(
    *,
    provider_id: str,
    timeout_seconds: int = 10,
    api_key: str | None = None,
    base_url: str | None = None,
) -> set[str]:
    models, _, _ = await get_dynamic_models_for_provider(
        provider_id=provider_id,
        timeout_seconds=timeout_seconds,
        api_key=api_key,
        base_url=base_url,
    )
    if models:
        return {str(model.get("id", "")).strip() for model in models if str(model.get("id", "")).strip()}
    return model_ids_for_provider(provider_id)


async def dynamic_model_by_id(
    *,
    provider_id: str,
    model_id: str,
    timeout_seconds: int = 10,
    api_key: str | None = None,
    base_url: str | None = None,
) -> dict[str, object] | None:
    normalized_model_id = model_id.strip()
    models, _, _ = await get_dynamic_models_for_provider(
        provider_id=provider_id,
        timeout_seconds=timeout_seconds,
        api_key=api_key,
        base_url=base_url,
    )
    if models:
        return next((model for model in models if str(model.get("id", "")).strip() == normalized_model_id), None)
    static_model = model_by_id(provider_id, normalized_model_id)
    return asdict(static_model) if static_model else None


async def get_dynamic_models_for_provider(
    *,
    provider_id: str,
    timeout_seconds: int = 10,
    api_key: str | None = None,
    base_url: str | None = None,
) -> tuple[list[dict[str, object]], str | None, str | None]:
    normalized_provider_id = provider_id.strip().lower()
    provider = provider_by_id(normalized_provider_id)
    if not provider:
        return [], None, "provider_not_found"

    try:
        resolved_base_url = safe_provider_base_url(
            base_url or provider.default_base_url,
            default_base_url=provider.default_base_url,
            provider_id=provider.id,
        )
    except ValueError as exc:
        return [], None, f"{exc.__class__.__name__}: {exc}"
    cache_key = (provider.id, bool(api_key), resolved_base_url)
    now = monotonic()
    cached = _dynamic_model_cache.get(cache_key)
    if cached and now < float(cached["expires_at"]):
        return list(cached["models"]), cached.get("fetched_at"), cached.get("error")

    async with _dynamic_cache_lock:
        now = monotonic()
        cached = _dynamic_model_cache.get(cache_key)
        if cached and now < float(cached["expires_at"]):
            return list(cached["models"]), cached.get("fetched_at"), cached.get("error")

        fetched_at = datetime.now(UTC).isoformat()
        try:
            models = await fetch_provider_models(
                provider_id=provider.id,
                timeout_seconds=timeout_seconds,
                api_key=api_key,
                base_url=resolved_base_url,
            )
            cache_entry = {
                "models": tuple(models),
                "fetched_at": fetched_at,
                "error": None,
                "expires_at": monotonic() + DYNAMIC_MODEL_CACHE_TTL_SECONDS,
            }
        except Exception as exc:
            cache_entry = {
                "models": tuple(),
                "fetched_at": fetched_at,
                "error": f"{exc.__class__.__name__}: {exc}",
                "expires_at": monotonic() + min(DYNAMIC_MODEL_CACHE_TTL_SECONDS, 60),
            }

        _dynamic_model_cache[cache_key] = cache_entry
        return list(cache_entry["models"]), cache_entry.get("fetched_at"), cache_entry.get("error")


async def fetch_provider_models(
    *,
    provider_id: str,
    timeout_seconds: int = 10,
    api_key: str | None = None,
    base_url: str | None = None,
) -> list[dict[str, object]]:
    normalized_provider_id = provider_id.strip().lower()
    provider = provider_by_id(normalized_provider_id)
    if not provider:
        raise ValueError(f"Unsupported provider: {provider_id}")

    if normalized_provider_id == OPENROUTER_PROVIDER_ID:
        return await fetch_openrouter_models(timeout_seconds=timeout_seconds, base_url=base_url)

    resolved_base_url = safe_provider_base_url(
        base_url or provider.default_base_url,
        default_base_url=provider.default_base_url,
        provider_id=provider.id,
    )
    headers, params = _provider_request_auth(provider_id=normalized_provider_id, api_key=api_key)
    endpoints = _provider_model_endpoints(provider_id=normalized_provider_id, base_url=resolved_base_url)
    timeout = min(max(timeout_seconds, 5), 20)

    last_error: Exception | None = None
    async with httpx.AsyncClient(timeout=timeout) as client:
        for endpoint in endpoints:
            try:
                response = await client.get(endpoint, headers=headers, params=params)
                response.raise_for_status()
                payload = response.json()
                records = _extract_model_records(payload) or []
                return [_normalize_generic_model(item) for item in records if isinstance(item, dict)]
            except Exception as exc:
                last_error = exc
                continue

    if last_error:
        raise last_error
    return []


async def fetch_openrouter_models(*, timeout_seconds: int = 10, base_url: str | None = None) -> list[dict[str, object]]:
    provider = provider_by_id(OPENROUTER_PROVIDER_ID)
    if not provider:
        raise ValueError("openrouter provider is not configured in the provider catalog")

    resolved_base_url = safe_provider_base_url(
        base_url or provider.default_base_url,
        default_base_url=provider.default_base_url,
        provider_id=provider.id,
    )
    endpoint = f"{resolved_base_url}/models"
    timeout = min(max(timeout_seconds, 5), 30)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(endpoint, headers={"Accept": "application/json"})
    response.raise_for_status()
    payload = response.json()
    records = _extract_model_records(payload) or []

    normalized: list[dict[str, object]] = []
    for item in records:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id", "")).strip()
        if not model_id:
            continue
        pricing = item.get("pricing") if isinstance(item.get("pricing"), dict) else {}
        normalized.append(
            {
                "id": model_id,
                "name": str(item.get("name", model_id)),
                "context_window": _context_window_label(item.get("context_length")),
                "capabilities": _model_capabilities(item),
                "reasoning_levels": (),
                "is_free": _is_free_openrouter_model(model_id=model_id, pricing=pricing),
                "pricing": _normalized_pricing(pricing),
            }
        )

    normalized.sort(key=lambda model: (not bool(model.get("is_free")), str(model.get("name", "")).lower(), str(model.get("id", "")).lower()))
    return normalized


async def _provider_catalog_entry(
    *,
    provider: ModelProviderOption,
    timeout_seconds: int,
    api_key: str | None,
    base_url: str | None,
) -> dict[str, object]:
    models, fetched_at, error = await get_dynamic_models_for_provider(
        provider_id=provider.id,
        timeout_seconds=timeout_seconds,
        api_key=api_key,
        base_url=base_url,
    )
    if models:
        return {
            "id": provider.id,
            "models": models,
            "source": "dynamic_live",
            "fetched_at": fetched_at,
            "error": error,
        }
    return {
        "id": provider.id,
        "models": [asdict(model) for model in provider.models],
        "source": "static_fallback",
        "fetched_at": fetched_at,
        "error": error,
    }


def _provider_request_auth(*, provider_id: str, api_key: str | None) -> tuple[dict[str, str], dict[str, str] | None]:
    if provider_id == "google":
        headers = {"Accept": "application/json"}
        if api_key:
            headers["x-goog-api-key"] = api_key
        return headers, None
    if provider_id == "anthropic":
        headers = {"Accept": "application/json", "anthropic-version": "2023-06-01"}
        if api_key:
            headers["x-api-key"] = api_key
        return headers, None
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers, None


def _provider_model_endpoints(*, provider_id: str, base_url: str) -> list[str]:
    clean = base_url.rstrip("/")
    if provider_id == "google":
        return [f"{clean}/v1beta/models"]

    parsed = urlparse(clean)
    root = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else clean
    candidates = [f"{clean}/models"]
    for suffix in ("/v1/models", "/v2/models", "/models"):
        endpoint = f"{root}{suffix}"
        if endpoint not in candidates:
            candidates.append(endpoint)
    return candidates


def _extract_model_records(payload: Any) -> list[Any] | None:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return None
    for key in ("data", "models", "items", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return None


def _normalize_generic_model(item: dict[str, Any]) -> dict[str, object]:
    model_id = str(item.get("id", "")).strip()
    model_name = str(item.get("name", model_id or "unknown")).strip() or model_id
    context_window = item.get("context_window")
    if context_window is None:
        context_window = item.get("context_length")
    return {
        "id": model_id,
        "name": model_name,
        "context_window": _context_window_label(context_window),
        "capabilities": _model_capabilities(item),
        "reasoning_levels": (),
    }


def _model_capabilities(item: dict[str, Any]) -> tuple[str, ...]:
    capabilities: list[str] = []
    architecture = item.get("architecture")
    if isinstance(architecture, dict):
        inputs = architecture.get("input_modalities")
        if isinstance(inputs, list):
            for modality in inputs:
                label = str(modality).strip().lower()
                if label and label not in capabilities:
                    capabilities.append(label)
    params = item.get("supported_parameters")
    if isinstance(params, list):
        if any(str(param).strip().lower() in {"reasoning", "include_reasoning"} for param in params):
            capabilities.append("reasoning")
        if any(str(param).strip().lower() == "tools" for param in params):
            capabilities.append("tools")
        if any(str(param).strip().lower() in {"web_search", "web_search_options"} for param in params):
            capabilities.append("web search")
    return tuple(capabilities)


def _context_window_label(value: Any) -> str:
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, str):
        return value
    return "N/A"


def _normalized_pricing(pricing: dict[str, Any]) -> dict[str, str]:
    output: dict[str, str] = {}
    for key in ("prompt", "completion", "request", "image", "web_search"):
        value = pricing.get(key)
        if value is None:
            continue
        output[key] = str(value)
    return output


def _is_free_openrouter_model(*, model_id: str, pricing: dict[str, Any]) -> bool:
    prompt_price = _decimal_or_none(pricing.get("prompt"))
    completion_price = _decimal_or_none(pricing.get("completion"))
    request_price = _decimal_or_none(pricing.get("request"))
    if prompt_price is not None and completion_price is not None:
        if prompt_price == 0 and completion_price == 0 and (request_price is None or request_price == 0):
            return True
    return model_id.endswith(":free")


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


__all__ = [
    "MODEL_PROVIDERS",
    "ModelOption",
    "ModelProviderOption",
    "OPENROUTER_PROVIDER_ID",
    "provider_catalog",
    "provider_catalog_runtime",
    "provider_by_id",
    "model_ids_for_provider",
    "model_by_id",
    "dynamic_model_ids_for_provider",
    "dynamic_model_by_id",
    "get_dynamic_models_for_provider",
    "fetch_provider_models",
    "fetch_openrouter_models",
]
