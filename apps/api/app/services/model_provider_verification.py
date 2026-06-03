from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

import httpx

from app.services.model_catalog import ModelProviderOption


@dataclass(frozen=True)
class ModelProviderVerificationResult:
    ok: bool
    provider: str
    model: str
    detail: str
    checked_at: str
    latency_ms: int

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "provider": self.provider,
            "model": self.model,
            "detail": self.detail,
            "checked_at": self.checked_at,
            "latency_ms": self.latency_ms,
        }


async def verify_model_provider(
    *,
    provider: ModelProviderOption,
    model: str,
    api_key: str,
    base_url: str,
    timeout_seconds: int,
) -> ModelProviderVerificationResult:
    started = perf_counter()
    checked_at = datetime.now(UTC).isoformat()
    endpoint = _models_endpoint(provider_id=provider.id, base_url=base_url)
    headers = _headers(provider_id=provider.id, api_key=api_key)
    params = {"key": api_key} if provider.id == "google" else None

    try:
        async with httpx.AsyncClient(timeout=min(max(timeout_seconds, 5), 30)) as client:
            response = await client.get(endpoint, headers=headers, params=params)
    except httpx.HTTPError as exc:
        return _result(False, provider.id, model, f"Provider request failed: {exc.__class__.__name__}", checked_at, started)

    if response.status_code in {401, 403}:
        return _result(False, provider.id, model, "Provider rejected the API key.", checked_at, started)
    if response.status_code >= 400:
        return _result(False, provider.id, model, f"Provider returned HTTP {response.status_code}.", checked_at, started)

    found = _response_mentions_model(response=response, model=model)
    detail = "Provider responded and selected model was present in the model list." if found else "Provider responded; model list did not explicitly include the selected model."
    return _result(True, provider.id, model, detail, checked_at, started)


def _models_endpoint(*, provider_id: str, base_url: str) -> str:
    clean = base_url.rstrip("/")
    if provider_id == "google":
        return f"{clean}/v1beta/models"
    return f"{clean}/models"


def _headers(*, provider_id: str, api_key: str) -> dict[str, str]:
    if provider_id == "google":
        return {"Accept": "application/json"}
    if provider_id == "anthropic":
        return {
            "Accept": "application/json",
            "anthropic-version": "2023-06-01",
            "x-api-key": api_key,
        }
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
    }


def _response_mentions_model(*, response: httpx.Response, model: str) -> bool:
    try:
        payload = response.json()
    except ValueError:
        return model in response.text
    return _contains_model(payload, model)


def _contains_model(value: Any, model: str) -> bool:
    if isinstance(value, str):
        return value == model or value.endswith(f"/{model}")
    if isinstance(value, dict):
        return any(_contains_model(item, model) for item in value.values())
    if isinstance(value, list):
        return any(_contains_model(item, model) for item in value)
    return False


def _result(
    ok: bool,
    provider: str,
    model: str,
    detail: str,
    checked_at: str,
    started: float,
) -> ModelProviderVerificationResult:
    return ModelProviderVerificationResult(
        ok=ok,
        provider=provider,
        model=model,
        detail=detail,
        checked_at=checked_at,
        latency_ms=max(0, round((perf_counter() - started) * 1000)),
    )
