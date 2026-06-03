from __future__ import annotations

import asyncio

from app.services import model_catalog
from app.services.model_catalog import _is_free_openrouter_model


def test_openrouter_free_flag_is_derived_from_zero_pricing() -> None:
    assert _is_free_openrouter_model(
        model_id="google/gemma-3-27b-it",
        pricing={"prompt": "0", "completion": "0", "request": "0"},
    )


def test_openrouter_free_flag_rejects_nonzero_pricing() -> None:
    assert not _is_free_openrouter_model(
        model_id="google/gemini-2.5-pro",
        pricing={"prompt": "0.00000125", "completion": "0.000005", "request": "0"},
    )


def test_openrouter_free_flag_falls_back_to_suffix_when_request_pricing_missing() -> None:
    assert _is_free_openrouter_model(
        model_id="meta-llama/llama-3.3-70b-instruct:free",
        pricing={"prompt": "0", "completion": "0"},
    )


def test_openrouter_free_flag_accepts_zero_token_pricing_without_request_field() -> None:
    assert _is_free_openrouter_model(
        model_id="custom/provider-model",
        pricing={"prompt": "0", "completion": "0"},
    )


def test_dynamic_model_ids_uses_live_provider_models(monkeypatch) -> None:
    model_catalog._dynamic_model_cache.clear()

    async def fake_fetch_provider_models(
        *,
        provider_id: str,
        timeout_seconds: int = 10,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> list[dict[str, object]]:
        assert provider_id == "openai"
        assert api_key == "sk-test"
        assert timeout_seconds == 9
        assert base_url == "https://api.openai.com/v1"
        return [
            {
                "id": "gpt-live-only",
                "name": "GPT Live",
                "context_window": "128K",
                "capabilities": (),
                "reasoning_levels": (),
            }
        ]

    monkeypatch.setattr(model_catalog, "fetch_provider_models", fake_fetch_provider_models)

    model_ids = asyncio.run(
        model_catalog.dynamic_model_ids_for_provider(
            provider_id="openai",
            timeout_seconds=9,
            api_key="sk-test",
            base_url="https://api.openai.com/v1",
        )
    )

    assert model_ids == {"gpt-live-only"}


def test_provider_catalog_runtime_falls_back_to_static_on_fetch_error(monkeypatch) -> None:
    model_catalog._dynamic_model_cache.clear()

    async def fake_fetch_provider_models(
        *,
        provider_id: str,
        timeout_seconds: int = 10,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> list[dict[str, object]]:
        if provider_id == "openai":
            return [
                {
                    "id": "gpt-live-only",
                    "name": "GPT Live",
                    "context_window": "128K",
                    "capabilities": ("tools",),
                    "reasoning_levels": (),
                }
            ]
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(model_catalog, "fetch_provider_models", fake_fetch_provider_models)

    catalog = asyncio.run(
        model_catalog.provider_catalog_runtime(
            timeout_seconds=8,
            preferred_provider_id="openai",
            preferred_api_key="sk-test",
            preferred_base_url="https://api.openai.com/v1",
        )
    )
    providers = {provider["id"]: provider for provider in catalog["providers"]}

    assert providers["openai"]["model_source"] == "dynamic_live"
    assert any(model["id"] == "gpt-live-only" for model in providers["openai"]["models"])
    assert providers["anthropic"]["model_source"] == "static_fallback"
    assert providers["anthropic"]["models"]
