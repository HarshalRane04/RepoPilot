import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.services.sandbox import SandboxRunner

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    service: str
    environment: str
    timestamp: datetime


class ReadinessResponse(BaseModel):
    status: str
    checks: dict[str, str]
    timestamp: datetime


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="repopilot-api",
        environment=settings.environment,
        timestamp=datetime.now(UTC),
    )


@router.get("/ready", response_model=ReadinessResponse)
async def ready(
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> ReadinessResponse:
    checks: dict[str, str] = {}
    try:
        await asyncio.wait_for(db.execute(text("SELECT 1")), timeout=3)
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"unavailable:{exc.__class__.__name__}"

    redis_client = Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
    try:
        await asyncio.wait_for(redis_client.ping(), timeout=3)
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"unavailable:{exc.__class__.__name__}"
    finally:
        await redis_client.aclose()

    sandbox_ok, sandbox_detail = await asyncio.to_thread(SandboxRunner().healthcheck)
    checks["sandbox"] = "ok" if sandbox_ok else sandbox_detail
    checks["repository_storage"] = _writable_directory_status(settings.repository_workspace_root)
    checks["artifact_storage"] = _writable_directory_status(settings.artifact_store_root)
    ready_status = all(value == "ok" for value in checks.values())
    if not ready_status:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(
        status="ready" if ready_status else "not_ready",
        checks=checks,
        timestamp=datetime.now(UTC),
    )


def _writable_directory_status(path_value: str) -> str:
    path = Path(path_value).expanduser()
    return "ok" if path.is_dir() and os.access(path, os.R_OK | os.W_OK | os.X_OK) else "unavailable"
