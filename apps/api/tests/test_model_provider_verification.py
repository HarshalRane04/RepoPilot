from __future__ import annotations

import asyncio

import httpx

from app.services.model_catalog import provider_by_id
from app.services.model_provider_verification import verify_model_provider


class FakeAsyncClient:
    def __init__(self, *args, **kwargs) -> None:
        self.request = httpx.Request("GET", "https://api.openai.com/v1/models")

    async def __aenter__(self) -> "FakeAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def get(self, *_args, **_kwargs) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"id": "gpt-5.4"}]}, request=self.request)


def test_model_provider_verification_fails_when_model_is_not_confirmed(monkeypatch) -> None:
    provider = provider_by_id("openai")
    assert provider is not None
    monkeypatch.setattr("app.services.model_provider_verification.httpx.AsyncClient", FakeAsyncClient)

    result = asyncio.run(
        verify_model_provider(
            provider=provider,
            model="gpt-5.5",
            api_key="sk-test",
            base_url="https://api.openai.com/v1",
            timeout_seconds=10,
        )
    )

    assert result.ok is False
    assert "did not explicitly include" in result.detail
