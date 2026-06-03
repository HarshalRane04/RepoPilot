from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from app.api.router import api_router
from app.core.config import settings
from app.services.runtime_secrets import effective_settings
from app.services.workspace_cleanup import WorkspaceCleanupService
from app.telemetry.logging import configure_logging

MAX_REQUEST_BODY_BYTES = 1_000_000


def create_app() -> FastAPI:
    configure_logging()
    config = effective_settings(settings)
    allowed_origins = {
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3002",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:3002",
        config.web_app_url.rstrip("/"),
    }

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        WorkspaceCleanupService(max_age_seconds=settings.workspace_cleanup_max_age_seconds).cleanup_stale_workspaces()
        yield

    app = FastAPI(
        title="RepoPilot AI API",
        version="0.1.0",
        description="Local platform skeleton for RepoPilot AI.",
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def request_body_limit(request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                declared_length = int(content_length)
            except ValueError:
                return JSONResponse({"detail": "Invalid content length."}, status_code=400)
            if declared_length > MAX_REQUEST_BODY_BYTES:
                return JSONResponse({"detail": "Request body too large."}, status_code=413)

        received = 0
        original_receive = request.receive

        async def limited_receive():
            nonlocal received
            message = await original_receive()
            if message.get("type") == "http.request":
                received += len(message.get("body", b""))
                if received > MAX_REQUEST_BODY_BYTES:
                    raise RequestBodyTooLarge
            return message

        try:
            limited_request = Request(request.scope, limited_receive)
            return await call_next(limited_request)
        except RequestBodyTooLarge:
            return JSONResponse({"detail": "Request body too large."}, status_code=413)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(allowed_origins),
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router)

    if settings.enable_otel:
        FastAPIInstrumentor.instrument_app(app)

    return app


class RequestBodyTooLarge(Exception):
    pass


app = create_app()
