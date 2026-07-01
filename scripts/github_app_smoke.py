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
from app.services.github_app import GitHubAppTokenProvider, GitHubIntegrationError  # noqa: E402
from app.services.runtime_secrets import GITHUB_APP_RUNTIME_SECRET_FIELDS, effective_settings, runtime_secret_store  # noqa: E402
from app.services.security_envelope import redact_text  # noqa: E402


@dataclass(frozen=True)
class GitHubAppSmoke:
    generated_at: str
    ok: bool
    status: str
    app_id_configured: bool
    private_key_configured: bool
    installation_id_configured: bool
    webhook_secret_configured: bool
    store_exists: bool
    store_permissions_ok: bool
    key_permissions_ok: bool
    verified_at: str | None
    installation_id: str | None
    token_received: bool
    detail: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _configured_value(value: str | None) -> bool:
    if value is None:
        return False
    normalized = str(value).strip().lower()
    return bool(normalized) and normalized not in {"placeholder", "todo", "secret", "change-me", "change_me"} and not normalized.startswith("change-me")


async def capture_github_app_smoke() -> GitHubAppSmoke:
    generated_at = datetime.now(UTC).isoformat()
    effective = effective_settings(settings)
    store = runtime_secret_store()
    store_summary = store.summary(set(GITHUB_APP_RUNTIME_SECRET_FIELDS))
    app_id_configured = _configured_value(effective.github_app_id)
    private_key_configured = _configured_value(effective.github_private_key) or _configured_value(effective.github_private_key_path)
    installation_id_configured = _configured_value(effective.github_installation_id)
    webhook_secret_configured = _configured_value(effective.github_webhook_secret)

    common = {
        "generated_at": generated_at,
        "app_id_configured": app_id_configured,
        "private_key_configured": private_key_configured,
        "installation_id_configured": installation_id_configured,
        "webhook_secret_configured": webhook_secret_configured,
        "store_exists": bool(store_summary["store_exists"]),
        "store_permissions_ok": bool(store_summary["store_permissions_ok"]),
        "key_permissions_ok": bool(store_summary["key_permissions_ok"]),
        "installation_id": effective.github_installation_id if installation_id_configured else None,
    }
    missing: list[str] = []
    if not app_id_configured:
        missing.append("GITHUB_APP_ID")
    if not private_key_configured:
        missing.append("GITHUB_APP_PRIVATE_KEY or GITHUB_PRIVATE_KEY_PATH")
    if not installation_id_configured:
        missing.append("GITHUB_INSTALLATION_ID")
    if missing:
        return GitHubAppSmoke(
            **common,
            ok=False,
            status="blocked",
            verified_at=None,
            token_received=False,
            detail=f"Missing required GitHub App credential(s): {', '.join(missing)}.",
        )

    try:
        token = await GitHubAppTokenProvider(effective).create_installation_access_token(effective.github_installation_id or "")
    except GitHubIntegrationError as exc:
        return GitHubAppSmoke(
            **common,
            ok=False,
            status="failed",
            verified_at=None,
            token_received=False,
            detail=redact_text(str(exc))[:300],
        )

    verified_at = datetime.now(UTC).isoformat()
    store.save_values(
        {
            "GITHUB_APP_VERIFIED_AT": verified_at,
            "GITHUB_APP_VERIFIED_INSTALLATION_ID": effective.github_installation_id or "",
        }
    )
    store_summary = store.summary(set(GITHUB_APP_RUNTIME_SECRET_FIELDS))
    return GitHubAppSmoke(
        generated_at=generated_at,
        ok=True,
        status="passed",
        app_id_configured=True,
        private_key_configured=True,
        installation_id_configured=True,
        webhook_secret_configured=webhook_secret_configured,
        store_exists=bool(store_summary["store_exists"]),
        store_permissions_ok=bool(store_summary["store_permissions_ok"]),
        key_permissions_ok=bool(store_summary["key_permissions_ok"]),
        verified_at=verified_at,
        installation_id=effective.github_installation_id,
        token_received=bool(token),
        detail="GitHub App installation token was created successfully.",
    )


def render_markdown(smoke: GitHubAppSmoke) -> str:
    return "\n".join(
        [
            "# RepoPilot GitHub App Smoke",
            "",
            f"- Generated at: `{smoke.generated_at}`",
            f"- Status: `{smoke.status}`",
            f"- App ID configured: `{smoke.app_id_configured}`",
            f"- Private key configured: `{smoke.private_key_configured}`",
            f"- Installation ID configured: `{smoke.installation_id_configured}`",
            f"- Webhook secret configured: `{smoke.webhook_secret_configured}`",
            f"- Runtime store exists: `{smoke.store_exists}`",
            f"- Store permissions OK: `{smoke.store_permissions_ok}`",
            f"- Key permissions OK: `{smoke.key_permissions_ok}`",
            f"- Verified at: `{smoke.verified_at or ''}`",
            f"- Installation ID: `{smoke.installation_id or ''}`",
            f"- Token received: `{smoke.token_received}`",
            "",
            "## Detail",
            "",
            smoke.detail,
            "",
        ]
    )


def write_outputs(*, smoke: GitHubAppSmoke, json_out: Path | None, md_out: Path | None) -> None:
    if json_out:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps(smoke.as_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if md_out:
        md_out.parent.mkdir(parents=True, exist_ok=True)
        md_out.write_text(render_markdown(smoke), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify GitHub App installation-token creation using RepoPilot's local encrypted runtime secret store.")
    parser.add_argument("--json-out", type=Path, default=Path("Docs/release-artifacts/github-app-smoke.json"))
    parser.add_argument("--md-out", type=Path, default=Path("Docs/release-artifacts/github-app-smoke.md"))
    parser.add_argument("--allow-blocked", action="store_true", help="Exit successfully when credentials are missing and a blocked artifact was written.")
    return parser


async def async_main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    smoke = await capture_github_app_smoke()
    write_outputs(smoke=smoke, json_out=args.json_out, md_out=args.md_out)
    print(redact_text(render_markdown(smoke)))
    if smoke.ok or (args.allow_blocked and smoke.status == "blocked"):
        return 0
    return 1


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
