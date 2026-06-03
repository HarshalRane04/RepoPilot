from __future__ import annotations

import hashlib
import json
import re
import time
from collections import defaultdict, deque
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import AgentRun, LLMTrace
from app.services.auth import CurrentUser, get_current_user

SECRET_KEY_PATTERN = re.compile(r"(?i)(api[_-]?key|authorization|client[_-]?secret|password|private[_-]?key|secret|session[_-]?secret|token)")
SECRET_VALUE_PATTERNS = (
    re.compile(r"ghp_[A-Za-z0-9_]{20,}", re.IGNORECASE),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}", re.IGNORECASE),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY-----"),
    re.compile(r"sk-[A-Za-z0-9][A-Za-z0-9_-]{12,}"),
)


def stable_json_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def redact_text(value: str) -> str:
    redacted = value
    for pattern in SECRET_VALUE_PATTERNS:
        redacted = pattern.sub("[REDACTED_SECRET]", redacted)
    redacted = re.sub(
        r"(?i)(api[_-]?key|password|secret|token)\s*=\s*['\"][^'\"]+['\"]",
        r"\1=[REDACTED_SECRET]",
        redacted,
    )
    return redacted


def redact_data(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if SECRET_KEY_PATTERN.search(key_text):
                redacted[key_text] = "[REDACTED_SECRET]"
            else:
                redacted[key_text] = redact_data(item)
        return redacted
    if isinstance(value, list):
        return [redact_data(item) for item in value]
    if isinstance(value, tuple):
        return [redact_data(item) for item in value]
    return value


@dataclass(frozen=True)
class BudgetSnapshot:
    run_id: UUID
    llm_call_count: int
    total_tokens: int
    total_cost: float


class BudgetExceeded(ValueError):
    pass


class BudgetGuard:
    async def snapshot(self, db: AsyncSession, *, run_id: UUID) -> BudgetSnapshot:
        run = await db.get(AgentRun, run_id)
        if run is None:
            raise ValueError(f"Agent run not found: {run_id}")
        llm_calls = await db.scalar(select(func.count()).select_from(LLMTrace).where(LLMTrace.agent_run_id == run_id)) or 0
        trace_tokens = await db.scalar(select(func.coalesce(func.sum(LLMTrace.tokens), 0)).where(LLMTrace.agent_run_id == run_id)) or 0
        trace_cost = await db.scalar(select(func.coalesce(func.sum(LLMTrace.cost), 0.0)).where(LLMTrace.agent_run_id == run_id)) or 0.0
        return BudgetSnapshot(
            run_id=run_id,
            llm_call_count=int(llm_calls),
            total_tokens=max(int(run.total_tokens or 0), int(trace_tokens or 0)),
            total_cost=max(float(run.total_cost or 0.0), float(trace_cost or 0.0)),
        )

    async def enforce(self, db: AsyncSession, *, run_id: UUID) -> BudgetSnapshot:
        snapshot = await self.snapshot(db, run_id=run_id)
        if snapshot.llm_call_count >= settings.max_llm_calls_per_run:
            raise BudgetExceeded("Run exceeded the maximum number of LLM calls.")
        if snapshot.total_tokens >= settings.max_tokens_per_run:
            raise BudgetExceeded("Run exceeded the maximum token budget.")
        if snapshot.total_cost >= settings.max_cost_per_run:
            raise BudgetExceeded("Run exceeded the maximum cost budget.")
        return snapshot


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._events: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    def allow(self, *, bucket: str, identity: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        now = time.monotonic()
        key = (bucket, identity)
        events = self._events[key]
        while events and now - events[0] > window_seconds:
            events.popleft()
        if len(events) >= limit:
            retry_after = max(1, int(window_seconds - (now - events[0]))) if events else window_seconds
            return False, retry_after
        events.append(now)
        return True, 0

    def clear(self) -> None:
        self._events.clear()


rate_limiter = InMemoryRateLimiter()


def rate_limit(bucket: str, *, limit_attr: str = "rate_limit_state_changes_per_minute"):
    async def dependency(
        request: Request,
        current_user: CurrentUser = Depends(get_current_user),
    ) -> None:
        limit = int(getattr(settings, limit_attr))
        window_seconds = int(settings.rate_limit_window_seconds)
        identity = current_user.github_user_id or current_user.username or (request.client.host if request.client else "unknown")
        allowed, retry_after = rate_limiter.allow(
            bucket=bucket,
            identity=str(identity),
            limit=limit,
            window_seconds=window_seconds,
        )
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded for {bucket}.",
                headers={"Retry-After": str(retry_after)},
            )

    return dependency
