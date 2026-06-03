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
from app.services.model_gateway import ModelGateway, _bounded_retry_count, _normalize_embedding, _post_json_with_retries
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
