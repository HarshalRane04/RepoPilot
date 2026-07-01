from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
for path in (
    ROOT / "apps" / "api",
    ROOT / "packages" / "shared_contracts",
    ROOT / "packages" / "evals",
    ROOT / "packages" / "policy_engine",
    ROOT / "packages" / "llm_client",
    ROOT / "packages" / "github_client",
):
    sys.path.insert(0, str(path))

from app.core.config import settings  # noqa: E402
from app.services.model_catalog import dynamic_model_ids_for_provider, provider_by_id  # noqa: E402
from app.services.model_provider_verification import verify_model_provider  # noqa: E402
from app.services.runtime_secrets import MODEL_RUNTIME_SECRET_FIELDS, effective_settings, runtime_secret_store  # noqa: E402
from app.services.security_envelope import redact_text  # noqa: E402


@dataclass(frozen=True)
class ModelProviderSmoke:
    generated_at: str
    ok: bool
    status: str
    provider: str
    model: str
    api_key_configured: bool
    model_available: bool
    store_exists: bool
    store_permissions_ok: bool
    key_permissions_ok: bool
    verified_at: str | None
    latency_ms: int | None
    detail: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _configured_value(value: str | None) -> bool:
    if value is None:
        return False
    normalized = str(value).strip().lower()
    return bool(normalized) and normalized not in {"placeholder", "todo", "secret", "change-me", "change_me"} and not normalized.startswith("change-me")


async def capture_model_provider_smoke() -> ModelProviderSmoke:
    generated_at = datetime.now(UTC).isoformat()
    effective = effective_settings(settings)
    store_summary = runtime_secret_store().summary(set(MODEL_RUNTIME_SECRET_FIELDS))
    provider = provider_by_id(effective.model_provider)
    api_key_configured = _configured_value(effective.model_api_key)

    if effective.model_provider == "mock":
        return ModelProviderSmoke(
            generated_at=generated_at,
            ok=False,
            status="blocked",
            provider=effective.model_provider,
            model=effective.model_name,
            api_key_configured=api_key_configured,
            model_available=False,
            store_exists=bool(store_summary["store_exists"]),
            store_permissions_ok=bool(store_summary["store_permissions_ok"]),
            key_permissions_ok=bool(store_summary["key_permissions_ok"]),
            verified_at=None,
            latency_ms=None,
            detail="Configure a live model provider before running provider smoke verification.",
        )

    if provider is None:
        return ModelProviderSmoke(
            generated_at=generated_at,
            ok=False,
            status="blocked",
            provider=effective.model_provider,
            model=effective.model_name,
            api_key_configured=api_key_configured,
            model_available=False,
            store_exists=bool(store_summary["store_exists"]),
            store_permissions_ok=bool(store_summary["store_permissions_ok"]),
            key_permissions_ok=bool(store_summary["key_permissions_ok"]),
            verified_at=None,
            latency_ms=None,
            detail="Configured provider is not supported by the model catalog.",
        )

    if not api_key_configured:
        return ModelProviderSmoke(
            generated_at=generated_at,
            ok=False,
            status="blocked",
            provider=provider.id,
            model=effective.model_name,
            api_key_configured=False,
            model_available=False,
            store_exists=bool(store_summary["store_exists"]),
            store_permissions_ok=bool(store_summary["store_permissions_ok"]),
            key_permissions_ok=bool(store_summary["key_permissions_ok"]),
            verified_at=None,
            latency_ms=None,
            detail="MODEL_API_KEY is not configured in the effective runtime settings.",
        )

    base_url = effective.model_base_url or provider.default_base_url
    available_models = await dynamic_model_ids_for_provider(
        provider_id=provider.id,
        timeout_seconds=effective.model_request_timeout_seconds,
        api_key=effective.model_api_key,
        base_url=base_url,
    )
    model_available = effective.model_name in available_models
    if not model_available:
        return ModelProviderSmoke(
            generated_at=generated_at,
            ok=False,
            status="blocked",
            provider=provider.id,
            model=effective.model_name,
            api_key_configured=True,
            model_available=False,
            store_exists=bool(store_summary["store_exists"]),
            store_permissions_ok=bool(store_summary["store_permissions_ok"]),
            key_permissions_ok=bool(store_summary["key_permissions_ok"]),
            verified_at=None,
            latency_ms=None,
            detail="Selected model is not available for the configured provider.",
        )

    result = await verify_model_provider(
        provider=provider,
        model=effective.model_name,
        api_key=effective.model_api_key or "",
        base_url=base_url,
        timeout_seconds=effective.model_request_timeout_seconds,
    )
    if result.ok:
        runtime_secret_store().save_values(
            {
                "MODEL_PROVIDER_VERIFIED_AT": result.checked_at,
                "MODEL_PROVIDER_VERIFIED_MODEL": f"{provider.id}:{effective.model_name}",
            }
        )
        store_summary = runtime_secret_store().summary(set(MODEL_RUNTIME_SECRET_FIELDS))

    return ModelProviderSmoke(
        generated_at=generated_at,
        ok=result.ok,
        status="passed" if result.ok else "failed",
        provider=provider.id,
        model=effective.model_name,
        api_key_configured=True,
        model_available=True,
        store_exists=bool(store_summary["store_exists"]),
        store_permissions_ok=bool(store_summary["store_permissions_ok"]),
        key_permissions_ok=bool(store_summary["key_permissions_ok"]),
        verified_at=result.checked_at if result.ok else None,
        latency_ms=result.latency_ms,
        detail=result.detail,
    )


def render_markdown(smoke: ModelProviderSmoke) -> str:
    return "\n".join(
        [
            "# RepoPilot Model Provider Smoke",
            "",
            f"- Generated at: `{smoke.generated_at}`",
            f"- Status: `{smoke.status}`",
            f"- Provider: `{smoke.provider}`",
            f"- Model: `{smoke.model}`",
            f"- API key configured: `{smoke.api_key_configured}`",
            f"- Model available: `{smoke.model_available}`",
            f"- Runtime store exists: `{smoke.store_exists}`",
            f"- Store permissions OK: `{smoke.store_permissions_ok}`",
            f"- Key permissions OK: `{smoke.key_permissions_ok}`",
            f"- Verified at: `{smoke.verified_at or ''}`",
            f"- Latency ms: `{smoke.latency_ms if smoke.latency_ms is not None else ''}`",
            "",
            "## Detail",
            "",
            smoke.detail,
            "",
        ]
    )


def write_outputs(*, smoke: ModelProviderSmoke, json_out: Path | None, md_out: Path | None) -> None:
    if json_out:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps(smoke.as_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if md_out:
        md_out.parent.mkdir(parents=True, exist_ok=True)
        md_out.write_text(render_markdown(smoke), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify the configured model provider using RepoPilot's local encrypted runtime secret store.")
    parser.add_argument("--json-out", type=Path, default=Path("Docs/release-artifacts/model-provider-smoke.json"))
    parser.add_argument("--md-out", type=Path, default=Path("Docs/release-artifacts/model-provider-smoke.md"))
    parser.add_argument("--allow-blocked", action="store_true", help="Exit successfully when credentials are missing and a blocked artifact was written.")
    return parser


async def async_main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    smoke = await capture_model_provider_smoke()
    write_outputs(smoke=smoke, json_out=args.json_out, md_out=args.md_out)
    print(redact_text(render_markdown(smoke)))
    if smoke.ok or (args.allow_blocked and smoke.status == "blocked"):
        return 0
    return 1


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
