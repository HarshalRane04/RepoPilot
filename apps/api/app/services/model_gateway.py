from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from typing import Any, TypeVar
from uuid import UUID

import httpx
from pydantic import BaseModel, ValidationError
from repopilot_contracts import EmbeddingResponse, LLMCallMode, LLMResponse, TokenUsage
from repopilot_llm_client import build_completion_request, extract_completion_content, extract_completion_usage
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import AgentRun, LLMTrace
from app.services.model_catalog import provider_by_id
from app.services.runtime_secrets import effective_settings
from app.services.security_envelope import BudgetGuard, redact_data, stable_json_hash

StructuredModel = TypeVar("StructuredModel", bound=BaseModel)
TRANSIENT_PROVIDER_STATUSES = {408, 409, 425, 429, 500, 502, 503, 504}
MAX_PROVIDER_RETRIES = 3


class ModelGateway:
    """Provider-agnostic model gateway with deterministic mock behavior for tests."""

    async def complete(
        self,
        db: AsyncSession,
        *,
        run_id: UUID | None,
        agent_name: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        context_citations: list[str] | None = None,
    ) -> LLMResponse:
        config = effective_settings(settings)
        started = time.perf_counter()
        prompt_payload = {
            "system": system_prompt,
            "user": user_prompt,
            "context_citations": context_citations or [],
        }
        prompt_hash = stable_json_hash(redact_data(prompt_payload))

        if run_id is not None:
            await BudgetGuard().enforce(db, run_id=run_id)

        provider = provider_by_id(config.model_provider)
        should_mock = config.model_provider == "mock" or not config.model_api_key or provider is None
        if should_mock:
            if config.model_provider != "mock" and not _model_fallback_allowed(config):
                raise RuntimeError("Live model provider is not fully configured and model fallback is disabled.")
            response = self._mock_completion(
                model=config.model_name,
                prompt_hash=prompt_hash,
                started=started,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        else:
            response = await self._complete_live_or_fallback(
                provider_id=config.model_provider,
                model=config.model_name,
                api_key=config.model_api_key or "",
                base_url=config.model_base_url or (provider.default_base_url if provider else ""),
                prompt_hash=prompt_hash,
                started=started,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout_seconds=config.model_request_timeout_seconds,
                max_retries=config.model_request_max_retries,
                retry_backoff_seconds=config.model_request_retry_backoff_seconds,
                allow_fallback=_model_fallback_allowed(config),
            )

        await self._record_trace(
            db,
            run_id=run_id,
            agent_name=agent_name,
            prompt_hash=prompt_hash,
            response=response,
            provider_id=config.model_provider,
            metadata={"context_citations": context_citations or []},
        )
        return response

    async def complete_json(
        self,
        db: AsyncSession,
        *,
        run_id: UUID | None,
        agent_name: str,
        system_prompt: str,
        user_prompt: str,
        response_model: type[StructuredModel],
        fallback: Callable[[], StructuredModel] | None = None,
        context_citations: list[str] | None = None,
    ) -> StructuredModel:
        response = await self.complete(
            db,
            run_id=run_id,
            agent_name=agent_name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            context_citations=context_citations,
        )
        parsed = self._parse_json_response(response.content, response_model=response_model)
        if parsed is not None:
            return parsed

        repair_response = await self.complete(
            db,
            run_id=run_id,
            agent_name=f"{agent_name}.repair",
            system_prompt="Return only valid JSON matching the requested schema.",
            user_prompt=f"Repair this invalid response into schema-valid JSON:\n{response.content}",
            context_citations=context_citations,
        )
        repaired = self._parse_json_response(repair_response.content, response_model=response_model)
        if repaired is not None:
            return repaired

        if fallback is not None:
            return fallback()
        raise ValueError(f"Model response could not be parsed as {response_model.__name__}.")

    async def embed(
        self,
        db: AsyncSession,
        *,
        run_id: UUID | None,
        texts: list[str],
        agent_name: str = "embedding",
        allow_live: bool = True,
    ) -> EmbeddingResponse:
        config = effective_settings(settings)
        if run_id is not None:
            await BudgetGuard().enforce(db, run_id=run_id)
        started = time.perf_counter()
        dimensions = max(1, int(config.embedding_dimensions))
        tokens = TokenUsage(prompt=sum(_estimate_tokens(text) for text in texts), completion=0, total=sum(_estimate_tokens(text) for text in texts))
        embedding_provider = provider_by_id(config.embedding_provider)
        live_blocked_by_policy = config.embedding_provider != "mock" and not allow_live
        should_mock = config.embedding_provider == "mock" or not config.model_api_key or embedding_provider is None or live_blocked_by_policy
        if should_mock:
            if config.embedding_provider != "mock" and not live_blocked_by_policy and not _model_fallback_allowed(config):
                raise RuntimeError("Live embedding provider is not fully configured and model fallback is disabled.")
            response = EmbeddingResponse(
                embeddings=[self._mock_embedding(text, dimensions=dimensions) for text in texts],
                provider="mock" if live_blocked_by_policy else config.embedding_provider,
                model="mock-embedding" if live_blocked_by_policy else config.embedding_model,
                dimensions=dimensions,
                tokens=tokens,
                cost=0.0,
                latency_ms=_elapsed_ms(started),
                mode=LLMCallMode.MOCK if config.embedding_provider == "mock" else LLMCallMode.FALLBACK,
            )
        else:
            response = await self._embed_live_or_fallback(
                provider_id=config.embedding_provider,
                model=config.embedding_model,
                api_key=config.model_api_key,
                base_url=config.model_base_url or embedding_provider.default_base_url,
                texts=texts,
                dimensions=dimensions,
                started=started,
                fallback_tokens=tokens,
                timeout_seconds=config.model_request_timeout_seconds,
                max_retries=config.model_request_max_retries,
                retry_backoff_seconds=config.model_request_retry_backoff_seconds,
                allow_fallback=_model_fallback_allowed(config),
            )
        await self._record_trace(
            db,
            run_id=run_id,
            agent_name=agent_name,
            prompt_hash=stable_json_hash(redact_data({"texts": texts})),
            response=LLMResponse(
                content=f"{len(texts)} embeddings",
                model=response.model,
                tokens=response.tokens,
                cost=response.cost,
                latency_ms=response.latency_ms,
                mode=response.mode,
                prompt_hash=stable_json_hash(redact_data({"texts": texts})),
                response_hash=stable_json_hash({"embedding_count": len(texts), "dimensions": dimensions}),
            ),
            provider_id=config.embedding_provider,
            metadata={
                "embedding_dimensions": response.dimensions,
                "embedding_count": len(texts),
                "embedding_mode": response.mode.value,
                "live_embedding_allowed": allow_live,
                "live_embedding_blocked_by_policy": live_blocked_by_policy,
            },
        )
        return response

    async def _embed_live_or_fallback(
        self,
        *,
        provider_id: str,
        model: str,
        api_key: str,
        base_url: str,
        texts: list[str],
        dimensions: int,
        started: float,
        fallback_tokens: TokenUsage,
        timeout_seconds: int,
        max_retries: int,
        retry_backoff_seconds: float,
        allow_fallback: bool = True,
    ) -> EmbeddingResponse:
        openai_compatible = provider_id in {"openai", "mistral", "groq", "xai", "deepseek", "perplexity", "together", "cerebras"}
        if not openai_compatible:
            if not allow_fallback:
                raise RuntimeError(f"{provider_id} does not support live embeddings and model fallback is disabled.")
            return EmbeddingResponse(
                embeddings=[self._mock_embedding(text, dimensions=dimensions) for text in texts],
                provider=provider_id,
                model=model,
                dimensions=dimensions,
                tokens=fallback_tokens,
                cost=0.0,
                latency_ms=_elapsed_ms(started),
                mode=LLMCallMode.FALLBACK,
            )
        try:
            async with httpx.AsyncClient(timeout=min(max(timeout_seconds, 5), 60)) as client:
                response = await _post_json_with_retries(
                    client,
                    url=f"{base_url.rstrip('/')}/embeddings",
                    headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
                    json_payload={"model": model, "input": texts},
                    max_retries=max_retries,
                    retry_backoff_seconds=retry_backoff_seconds,
                )
        except httpx.HTTPError as exc:
            if not allow_fallback:
                raise RuntimeError(f"Provider embedding call failed and model fallback is disabled: {exc.__class__.__name__}.") from exc
            return EmbeddingResponse(
                embeddings=[self._mock_embedding(text, dimensions=dimensions) for text in texts],
                provider=provider_id,
                model=model,
                dimensions=dimensions,
                tokens=fallback_tokens,
                cost=0.0,
                latency_ms=_elapsed_ms(started),
                mode=LLMCallMode.FALLBACK,
            )

        payload = response.json()
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            embeddings = [self._mock_embedding(text, dimensions=dimensions) for text in texts]
            mode = LLMCallMode.FALLBACK
        else:
            embeddings = [
                _normalize_embedding(item.get("embedding") if isinstance(item, dict) else None, dimensions=dimensions)
                for item in data[: len(texts)]
            ]
            if len(embeddings) < len(texts):
                embeddings.extend(self._mock_embedding(text, dimensions=dimensions) for text in texts[len(embeddings) :])
            mode = LLMCallMode.LIVE
        usage = _usage_from_payload(payload.get("usage") if isinstance(payload, dict) else None)
        if usage.total == 0:
            usage = fallback_tokens
        return EmbeddingResponse(
            embeddings=embeddings,
            provider=provider_id,
            model=model,
            dimensions=dimensions,
            tokens=usage,
            cost=0.0,
            latency_ms=_elapsed_ms(started),
            mode=mode,
        )

    def _mock_completion(
        self,
        *,
        model: str,
        prompt_hash: str,
        started: float,
        system_prompt: str,
        user_prompt: str,
    ) -> LLMResponse:
        lowered = f"{system_prompt}\n{user_prompt}".lower()
        if "json" in lowered:
            content = json.dumps({"summary": "Mock model response.", "items": []})
        else:
            content = "Mock model response."
        return LLMResponse(
            content=content,
            model=model,
            tokens=TokenUsage(prompt=_estimate_tokens(system_prompt) + _estimate_tokens(user_prompt), completion=_estimate_tokens(content), total=_estimate_tokens(system_prompt) + _estimate_tokens(user_prompt) + _estimate_tokens(content)),
            cost=0.0,
            latency_ms=_elapsed_ms(started),
            mode=LLMCallMode.MOCK,
            prompt_hash=prompt_hash,
            response_hash=stable_json_hash(redact_data({"content": content})),
        )

    async def _complete_live_or_fallback(
        self,
        *,
        provider_id: str,
        model: str,
        api_key: str,
        base_url: str,
        prompt_hash: str,
        started: float,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
        timeout_seconds: int,
        max_retries: int,
        retry_backoff_seconds: float,
        allow_fallback: bool = True,
    ) -> LLMResponse:
        if provider_id == "cohere":
            if not allow_fallback:
                raise RuntimeError(f"{provider_id} requires a provider-specific live adapter and model fallback is disabled.")
            return self._fallback_completion(model=model, prompt_hash=prompt_hash, started=started, reason=f"{provider_id} requires a provider-specific live adapter; deterministic fallback was used.")
        try:
            request = _completion_request(
                provider_id=provider_id,
                model=model,
                api_key=api_key,
                base_url=base_url,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            async with httpx.AsyncClient(timeout=min(max(timeout_seconds, 5), 60)) as client:
                response = await _post_json_with_retries(
                    client,
                    url=request["url"],
                    headers=request["headers"],
                    json_payload=request["json_payload"],
                    max_retries=max_retries,
                    retry_backoff_seconds=retry_backoff_seconds,
                )
        except httpx.HTTPError as exc:
            if not allow_fallback:
                raise RuntimeError(f"Provider call failed and model fallback is disabled: {exc.__class__.__name__}.") from exc
            return self._fallback_completion(model=model, prompt_hash=prompt_hash, started=started, reason=f"Provider call failed: {exc.__class__.__name__}.")

        payload = response.json()
        content = _extract_provider_completion_content(provider_id=provider_id, payload=payload)
        usage = extract_completion_usage(provider_id=provider_id, payload=payload)
        tokens = TokenUsage(prompt=usage["prompt"], completion=usage["completion"], total=usage["total"])
        return LLMResponse(
            content=content,
            model=model,
            tokens=tokens,
            cost=0.0,
            latency_ms=_elapsed_ms(started),
            mode=LLMCallMode.LIVE,
            prompt_hash=prompt_hash,
            response_hash=stable_json_hash(redact_data({"content": content})),
        )

    def _fallback_completion(self, *, model: str, prompt_hash: str, started: float, reason: str) -> LLMResponse:
        content = json.dumps({"summary": "Deterministic fallback response.", "items": [], "fallback_reason": reason})
        return LLMResponse(
            content=content,
            model=model,
            tokens=TokenUsage(prompt=0, completion=_estimate_tokens(content), total=_estimate_tokens(content)),
            cost=0.0,
            latency_ms=_elapsed_ms(started),
            mode=LLMCallMode.FALLBACK,
            prompt_hash=prompt_hash,
            response_hash=stable_json_hash(redact_data({"content": content})),
        )

    def _parse_json_response(self, content: str, *, response_model: type[StructuredModel]) -> StructuredModel | None:
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            return None
        try:
            return response_model.model_validate(payload)
        except ValidationError:
            return None

    def _mock_embedding(self, text: str, *, dimensions: int) -> list[float]:
        vector = [0.0] * dimensions
        words = [word for word in re_split_words(text) if word]
        if not words:
            return vector
        for word in words:
            bucket = int(stable_json_hash(word)[:8], 16) % dimensions
            vector[bucket] += 1.0
        norm = sum(value * value for value in vector) ** 0.5 or 1.0
        return [round(value / norm, 6) for value in vector]

    async def _record_trace(
        self,
        db: AsyncSession,
        *,
        run_id: UUID | None,
        agent_name: str,
        prompt_hash: str,
        response: LLMResponse,
        provider_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if run_id is None:
            return
        db.add(
            LLMTrace(
                agent_run_id=run_id,
                agent_name=agent_name,
                prompt_hash=prompt_hash,
                response_hash=response.response_hash,
                provider=provider_id,
                model=response.model,
                mode=response.mode.value,
                tokens=response.tokens.total,
                cost=response.cost,
                latency_ms=response.latency_ms,
                metadata_json=redact_data(metadata or {}),
            )
        )
        run = await db.get(AgentRun, run_id)
        if run is not None:
            run.total_tokens = int(run.total_tokens or 0) + response.tokens.total
            run.total_cost = float(run.total_cost or 0.0) + response.cost
        await db.flush()


def re_split_words(text: str) -> list[str]:
    cleaned = "".join(char.lower() if char.isalnum() or char == "_" else " " for char in text)
    return cleaned.split()


def _model_fallback_allowed(config: Any) -> bool:
    return bool(getattr(config, "allow_model_fallback", False)) or (
        str(getattr(config, "environment", "")).strip().lower() == "local"
    )


async def _post_json_with_retries(
    client: Any,
    *,
    url: str,
    headers: dict[str, str],
    json_payload: dict[str, Any],
    max_retries: int,
    retry_backoff_seconds: float,
) -> httpx.Response:
    attempts = _bounded_retry_count(max_retries) + 1
    last_error: httpx.HTTPError | None = None
    for attempt in range(attempts):
        try:
            response = await client.post(url, headers=headers, json=json_payload)
            if response.status_code in TRANSIENT_PROVIDER_STATUSES and attempt < attempts - 1:
                await _sleep_before_retry(retry_backoff_seconds, attempt)
                continue
            response.raise_for_status()
            return response
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_error = exc
            if attempt >= attempts - 1:
                raise
            await _sleep_before_retry(retry_backoff_seconds, attempt)
    if last_error is not None:
        raise last_error
    raise RuntimeError("provider request retry loop exited without a response")


def _bounded_retry_count(max_retries: int) -> int:
    return min(max(int(max_retries), 0), MAX_PROVIDER_RETRIES)


async def _sleep_before_retry(retry_backoff_seconds: float, attempt: int) -> None:
    delay = max(float(retry_backoff_seconds), 0.0) * (2**attempt)
    if delay > 0:
        await asyncio.sleep(min(delay, 5.0))


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4) if text else 0


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1000))


def _usage_from_payload(usage: Any) -> TokenUsage:
    if not isinstance(usage, dict):
        return TokenUsage()
    prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or usage.get("promptTokenCount") or 0)
    completion = int(usage.get("completion_tokens") or usage.get("output_tokens") or usage.get("candidatesTokenCount") or 0)
    total = int(usage.get("total_tokens") or usage.get("totalTokenCount") or prompt + completion)
    return TokenUsage(prompt=prompt, completion=completion, total=total)


def _completion_request(
    *,
    provider_id: str,
    model: str,
    api_key: str,
    base_url: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    max_tokens: int,
) -> dict[str, Any]:
    request = build_completion_request(
        provider_id=provider_id,
        model=model,
        api_key=api_key,
        base_url=base_url,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return {"url": request.url, "headers": request.headers, "json_payload": request.json_payload}


def _normalize_embedding(value: Any, *, dimensions: int) -> list[float]:
    if not isinstance(value, list):
        return [0.0] * dimensions
    vector = [float(item) if isinstance(item, (int, float)) else 0.0 for item in value[:dimensions]]
    if len(vector) < dimensions:
        vector.extend([0.0] * (dimensions - len(vector)))
    norm = sum(item * item for item in vector) ** 0.5
    if norm == 0:
        return vector
    return [round(item / norm, 6) for item in vector]


def _extract_openai_compatible_content(payload: Any) -> str:
    return extract_completion_content(provider_id="openai", payload=payload)


def _extract_provider_completion_content(*, provider_id: str, payload: Any) -> str:
    return extract_completion_content(provider_id=provider_id, payload=payload)
