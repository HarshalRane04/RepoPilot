from __future__ import annotations

import asyncio
from uuid import uuid4

import httpx
import pytest
from pydantic import BaseModel
from repopilot_contracts import LLMCallMode
from repopilot_llm_client import provider_catalog as package_provider_catalog

from app.core.config import settings
from app.db.models import AgentRun, LLMTrace
from app.services.model_catalog import provider_catalog
from app.services.model_gateway import (
    ModelGateway,
    _bounded_retry_count,
    _completion_request,
    _extract_provider_completion_content,
    _normalize_embedding,
    _post_json_with_retries,
)
from app.services.security_envelope import BudgetExceeded


class GatewayPayload(BaseModel):
    summary: str
    items: list[str]


class FakeGatewayDb:
    def __init__(self, run: AgentRun) -> None:
        self.run = run
        self.added: list[object] = []
        self.flushes = 0

    async def get(self, model, item_id):
        if model is AgentRun and item_id == self.run.id:
            return self.run
        return None

    async def scalar(self, _statement):
        return 0

    def add(self, item: object) -> None:
        self.added.append(item)

    async def flush(self) -> None:
        self.flushes += 1


class FakeRetryResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code

    def json(self) -> dict[str, object]:
        return {"ok": True}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("POST", "https://provider.example.test")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("provider error", request=request, response=response)


class FakeProviderResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.status_code = 200

    def json(self) -> dict[str, object]:
        return self.payload


class FakeRetryClient:
    def __init__(self, statuses: list[int]) -> None:
        self.statuses = statuses
        self.calls = 0

    async def post(self, *_args, **_kwargs) -> FakeRetryResponse:
        status = self.statuses[min(self.calls, len(self.statuses) - 1)]
        self.calls += 1
        return FakeRetryResponse(status)


def test_api_model_catalog_reexports_llm_client_package() -> None:
    assert provider_catalog() == package_provider_catalog()


def configure_mock_model(monkeypatch) -> None:
    monkeypatch.setattr(settings, "model_provider", "mock")
    monkeypatch.setattr(settings, "model_name", "mock-planner")
    monkeypatch.setattr(settings, "model_api_key", None)
    monkeypatch.setattr(settings, "embedding_provider", "mock")
    monkeypatch.setattr(settings, "embedding_model", "mock-embedding")
    monkeypatch.setattr(settings, "embedding_dimensions", 16)
    monkeypatch.setattr(settings, "max_llm_calls_per_run", 40)
    monkeypatch.setattr(settings, "max_tokens_per_run", 250_000)
    monkeypatch.setattr(settings, "max_cost_per_run", 5.0)


def test_model_gateway_mock_completion_records_trace(monkeypatch) -> None:
    configure_mock_model(monkeypatch)
    run = AgentRun(id=uuid4(), state="WAIT_FOR_APPROVAL", total_tokens=0, total_cost=0.0)
    db = FakeGatewayDb(run)

    response = asyncio.run(
        ModelGateway().complete(
            db,
            run_id=run.id,
            agent_name="planning",
            system_prompt="Return JSON.",
            user_prompt="Plan a docs update.",
        )
    )

    assert response.mode == LLMCallMode.MOCK
    assert response.prompt_hash
    assert response.response_hash
    assert run.total_tokens == response.tokens.total
    trace = next(item for item in db.added if isinstance(item, LLMTrace) and item.agent_name == "planning")
    assert trace.provider == "mock"
    assert trace.mode == "mock"
    assert trace.response_hash == response.response_hash
    assert trace.metadata_json == {"context_citations": []}
    assert db.flushes == 1


def test_model_gateway_complete_json_validates_schema(monkeypatch) -> None:
    configure_mock_model(monkeypatch)
    run = AgentRun(id=uuid4(), state="WAIT_FOR_APPROVAL", total_tokens=0, total_cost=0.0)
    db = FakeGatewayDb(run)

    result = asyncio.run(
        ModelGateway().complete_json(
            db,
            run_id=run.id,
            agent_name="triage",
            system_prompt="Return JSON.",
            user_prompt="Return a summary and items array.",
            response_model=GatewayPayload,
        )
    )

    assert result.summary == "Mock model response."
    assert result.items == []


def test_model_gateway_mock_embeddings_are_deterministic(monkeypatch) -> None:
    configure_mock_model(monkeypatch)
    run = AgentRun(id=uuid4(), state="RETRIEVE_CONTEXT", total_tokens=0, total_cost=0.0)
    db = FakeGatewayDb(run)

    first = asyncio.run(ModelGateway().embed(db, run_id=run.id, texts=["dashboard pagination bug"]))
    second = asyncio.run(ModelGateway().embed(db, run_id=run.id, texts=["dashboard pagination bug"]))

    assert first.mode == LLMCallMode.MOCK
    assert first.dimensions == 16
    assert first.embeddings == second.embeddings
    trace = next(item for item in db.added if isinstance(item, LLMTrace) and item.agent_name == "embedding")
    assert trace.provider == "mock"
    assert trace.mode == "mock"
    assert trace.response_hash
    assert trace.metadata_json == {"embedding_count": 1, "embedding_dimensions": 16, "embedding_mode": "mock"}


def test_model_gateway_normalizes_live_embedding_dimensions() -> None:
    vector = _normalize_embedding([3, 4, 0, 99], dimensions=3)

    assert vector == [0.6, 0.8, 0.0]
    assert _normalize_embedding([1], dimensions=3) == [1.0, 0.0, 0.0]


def test_model_gateway_builds_anthropic_messages_request() -> None:
    request = _completion_request(
        provider_id="anthropic",
        model="claude-sonnet-4-6",
        api_key="sk-test",
        base_url="https://api.anthropic.com",
        system_prompt="Return JSON.",
        user_prompt="Plan a focused patch.",
        temperature=0.1,
        max_tokens=512,
    )

    assert request["url"] == "https://api.anthropic.com/v1/messages"
    assert request["headers"]["x-api-key"] == "sk-test"
    assert request["headers"]["anthropic-version"] == "2023-06-01"
    assert request["json_payload"]["system"] == "Return JSON."
    assert request["json_payload"]["messages"] == [
        {"role": "user", "content": [{"type": "text", "text": "Plan a focused patch."}]}
    ]


def test_model_gateway_builds_gemini_generate_content_request() -> None:
    request = _completion_request(
        provider_id="google",
        model="gemini-2.5-pro",
        api_key="gemini-test",
        base_url="https://generativelanguage.googleapis.com",
        system_prompt="Return JSON.",
        user_prompt="Plan a focused patch.",
        temperature=0.2,
        max_tokens=768,
    )

    assert request["url"] == "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent"
    assert request["headers"]["x-goog-api-key"] == "gemini-test"
    assert request["json_payload"]["systemInstruction"] == {"parts": [{"text": "Return JSON."}]}
    assert request["json_payload"]["contents"] == [{"role": "user", "parts": [{"text": "Plan a focused patch."}]}]
    assert request["json_payload"]["generationConfig"] == {"temperature": 0.2, "maxOutputTokens": 768}


def test_model_gateway_extracts_anthropic_and_gemini_content() -> None:
    assert (
        _extract_provider_completion_content(
            provider_id="anthropic",
            payload={"content": [{"type": "text", "text": "First "}, {"type": "text", "text": "second."}]},
        )
        == "First second."
    )
    assert (
        _extract_provider_completion_content(
            provider_id="google",
            payload={"candidates": [{"content": {"parts": [{"text": "First "}, {"text": "second."}]}}]},
        )
        == "First second."
    )


def test_model_gateway_anthropic_live_completion_uses_native_adapter(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    async def fake_post_json_with_retries(_client, **kwargs) -> FakeProviderResponse:
        calls.append(kwargs)
        return FakeProviderResponse(
            {
                "content": [{"type": "text", "text": '{"summary":"Claude plan","items":["edit"]}'}],
                "usage": {"input_tokens": 11, "output_tokens": 7},
            }
        )

    monkeypatch.setattr("app.services.model_gateway._post_json_with_retries", fake_post_json_with_retries)

    response = asyncio.run(
        ModelGateway()._complete_live_or_fallback(
            provider_id="anthropic",
            model="claude-sonnet-4-6",
            api_key="sk-test",
            base_url="https://api.anthropic.com",
            prompt_hash="prompt-hash",
            started=0.0,
            system_prompt="Return JSON.",
            user_prompt="Plan a patch.",
            temperature=0.0,
            max_tokens=1024,
            timeout_seconds=10,
            max_retries=0,
            retry_backoff_seconds=0,
        )
    )

    assert calls[0]["url"] == "https://api.anthropic.com/v1/messages"
    assert calls[0]["headers"]["x-api-key"] == "sk-test"
    assert response.mode == LLMCallMode.LIVE
    assert response.content == '{"summary":"Claude plan","items":["edit"]}'
    assert response.tokens.prompt == 11
    assert response.tokens.completion == 7
    assert response.tokens.total == 18


def test_model_gateway_google_live_completion_uses_generate_content(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    async def fake_post_json_with_retries(_client, **kwargs) -> FakeProviderResponse:
        calls.append(kwargs)
        return FakeProviderResponse(
            {
                "candidates": [{"content": {"parts": [{"text": '{"summary":"Gemini plan","items":["test"]}'}]}}],
                "usageMetadata": {"promptTokenCount": 13, "candidatesTokenCount": 9, "totalTokenCount": 22},
            }
        )

    monkeypatch.setattr("app.services.model_gateway._post_json_with_retries", fake_post_json_with_retries)

    response = asyncio.run(
        ModelGateway()._complete_live_or_fallback(
            provider_id="google",
            model="gemini-2.5-pro",
            api_key="gemini-test",
            base_url="https://generativelanguage.googleapis.com",
            prompt_hash="prompt-hash",
            started=0.0,
            system_prompt="Return JSON.",
            user_prompt="Plan a patch.",
            temperature=0.0,
            max_tokens=1024,
            timeout_seconds=10,
            max_retries=0,
            retry_backoff_seconds=0,
        )
    )

    assert calls[0]["url"] == "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent"
    assert calls[0]["headers"]["x-goog-api-key"] == "gemini-test"
    assert response.mode == LLMCallMode.LIVE
    assert response.content == '{"summary":"Gemini plan","items":["test"]}'
    assert response.tokens.prompt == 13
    assert response.tokens.completion == 9
    assert response.tokens.total == 22


def test_provider_retry_helper_retries_transient_status() -> None:
    client = FakeRetryClient([429, 200])

    response = asyncio.run(
        _post_json_with_retries(
            client,
            url="https://provider.example.test/chat/completions",
            headers={},
            json_payload={"model": "mock"},
            max_retries=1,
            retry_backoff_seconds=0,
        )
    )

    assert response.status_code == 200
    assert client.calls == 2


def test_provider_retry_helper_caps_configured_retry_count() -> None:
    client = FakeRetryClient([503, 503, 503, 503, 200])

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(
            _post_json_with_retries(
                client,
                url="https://provider.example.test/chat/completions",
                headers={},
                json_payload={"model": "mock"},
                max_retries=99,
                retry_backoff_seconds=0,
            )
        )

    assert _bounded_retry_count(99) == 3
    assert client.calls == 4


def test_model_gateway_enforces_run_budget(monkeypatch) -> None:
    configure_mock_model(monkeypatch)
    monkeypatch.setattr(settings, "max_llm_calls_per_run", 0)
    run = AgentRun(id=uuid4(), state="WAIT_FOR_APPROVAL", total_tokens=0, total_cost=0.0)
    db = FakeGatewayDb(run)

    with pytest.raises(BudgetExceeded):
        asyncio.run(
            ModelGateway().complete(
                db,
                run_id=run.id,
                agent_name="planning",
                system_prompt="Return JSON.",
                user_prompt="Plan a docs update.",
            )
        )
