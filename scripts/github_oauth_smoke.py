from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse


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
from app.services.github_oauth import GitHubOAuthError, GitHubOAuthService  # noqa: E402
from app.services.runtime_secrets import GITHUB_OAUTH_RUNTIME_SECRET_FIELDS, effective_settings, runtime_secret_store  # noqa: E402
from app.services.security_envelope import redact_text  # noqa: E402
from app.services.url_safety import github_api_base_url as safe_github_api_base_url  # noqa: E402
from app.services.url_safety import github_web_base_url as safe_github_web_base_url  # noqa: E402


@dataclass(frozen=True)
class GitHubOAuthSmoke:
    generated_at: str
    ok: bool
    status: str
    client_id_configured: bool
    client_secret_configured: bool
    callback_url_configured: bool
    web_app_url_configured: bool
    session_secret_configured: bool
    github_base_urls_configured: bool
    authorization_url_generated: bool
    store_exists: bool
    store_permissions_ok: bool
    key_permissions_ok: bool
    detail: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _configured_value(value: str | None) -> bool:
    if value is None:
        return False
    normalized = str(value).strip().lower()
    return bool(normalized) and normalized not in {"placeholder", "todo", "secret", "change-me", "change_me"} and not normalized.startswith("change-me")


def _valid_url(value: str | None, *, allow_http_localhost: bool = True) -> bool:
    if not _configured_value(value):
        return False
    parsed = urlparse(str(value))
    if parsed.scheme == "https" and parsed.netloc:
        return True
    if allow_http_localhost and parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"}:
        return True
    return False


def capture_github_oauth_smoke() -> GitHubOAuthSmoke:
    generated_at = datetime.now(UTC).isoformat()
    effective = effective_settings(settings)
    store_summary = runtime_secret_store().summary(set(GITHUB_OAUTH_RUNTIME_SECRET_FIELDS))

    client_id_configured = _configured_value(effective.github_client_id)
    client_secret_configured = _configured_value(effective.github_client_secret)
    callback_url_configured = _valid_url(effective.github_oauth_callback_url)
    web_app_url_configured = _valid_url(effective.web_app_url)
    session_secret_configured = _configured_value(effective.session_secret_key)
    github_base_urls_configured = _valid_github_base_urls(
        api_base_url=effective.github_api_base_url,
        web_base_url=effective.github_web_base_url,
    )

    common = {
        "generated_at": generated_at,
        "client_id_configured": client_id_configured,
        "client_secret_configured": client_secret_configured,
        "callback_url_configured": callback_url_configured,
        "web_app_url_configured": web_app_url_configured,
        "session_secret_configured": session_secret_configured,
        "github_base_urls_configured": github_base_urls_configured,
        "store_exists": bool(store_summary["store_exists"]),
        "store_permissions_ok": bool(store_summary["store_permissions_ok"]),
        "key_permissions_ok": bool(store_summary["key_permissions_ok"]),
    }

    missing: list[str] = []
    if not client_id_configured:
        missing.append("GITHUB_CLIENT_ID")
    if not client_secret_configured:
        missing.append("GITHUB_CLIENT_SECRET")
    if not callback_url_configured:
        missing.append("GITHUB_OAUTH_CALLBACK_URL")
    if not web_app_url_configured:
        missing.append("WEB_APP_URL")
    if not session_secret_configured:
        missing.append("SESSION_SECRET_KEY")
    if not github_base_urls_configured:
        missing.append("GITHUB_API_BASE_URL/GITHUB_WEB_BASE_URL")

    if missing:
        return GitHubOAuthSmoke(
            **common,
            ok=False,
            status="blocked",
            authorization_url_generated=False,
            detail=f"Missing or invalid GitHub OAuth setting(s): {', '.join(missing)}.",
        )

    try:
        authorization_url = GitHubOAuthService(effective).authorization_url(state="repopilot-smoke-state")
    except GitHubOAuthError as exc:
        return GitHubOAuthSmoke(
            **common,
            ok=False,
            status="failed",
            authorization_url_generated=False,
            detail=redact_text(str(exc))[:300],
        )

    parsed = urlparse(authorization_url)
    generated = parsed.scheme == "https" and parsed.hostname == "github.com" and parsed.path == "/login/oauth/authorize"
    return GitHubOAuthSmoke(
        **common,
        ok=generated,
        status="passed" if generated else "failed",
        authorization_url_generated=generated,
        detail="GitHub OAuth authorization URL generated successfully." if generated else "Generated authorization URL did not match expected GitHub authorize endpoint.",
    )


def render_markdown(smoke: GitHubOAuthSmoke) -> str:
    return "\n".join(
        [
            "# RepoPilot GitHub OAuth Smoke",
            "",
            f"- Generated at: `{smoke.generated_at}`",
            f"- Status: `{smoke.status}`",
            f"- Client ID configured: `{smoke.client_id_configured}`",
            f"- Client secret configured: `{smoke.client_secret_configured}`",
            f"- Callback URL configured: `{smoke.callback_url_configured}`",
            f"- Web app URL configured: `{smoke.web_app_url_configured}`",
            f"- Session secret configured: `{smoke.session_secret_configured}`",
            f"- GitHub base URLs configured: `{smoke.github_base_urls_configured}`",
            f"- Authorization URL generated: `{smoke.authorization_url_generated}`",
            f"- Runtime store exists: `{smoke.store_exists}`",
            f"- Store permissions OK: `{smoke.store_permissions_ok}`",
            f"- Key permissions OK: `{smoke.key_permissions_ok}`",
            "",
            "## Detail",
            "",
            smoke.detail,
            "",
        ]
    )


def _valid_github_base_urls(*, api_base_url: str | None, web_base_url: str | None) -> bool:
    try:
        safe_github_api_base_url(api_base_url or "")
        safe_github_web_base_url(web_base_url or "")
    except ValueError:
        return False
    return True


def write_outputs(*, smoke: GitHubOAuthSmoke, json_out: Path | None, md_out: Path | None) -> None:
    if json_out:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps(smoke.as_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if md_out:
        md_out.parent.mkdir(parents=True, exist_ok=True)
        md_out.write_text(render_markdown(smoke), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify GitHub OAuth/session configuration using RepoPilot's local encrypted runtime secret store.")
    parser.add_argument("--json-out", type=Path, default=Path("Docs/release-artifacts/github-oauth-smoke.json"))
    parser.add_argument("--md-out", type=Path, default=Path("Docs/release-artifacts/github-oauth-smoke.md"))
    parser.add_argument("--allow-blocked", action="store_true", help="Exit successfully when credentials are missing and a blocked artifact was written.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    smoke = capture_github_oauth_smoke()
    write_outputs(smoke=smoke, json_out=args.json_out, md_out=args.md_out)
    print("GitHub OAuth smoke completed; redacted artifacts were written.")
    if smoke.ok or (args.allow_blocked and smoke.status == "blocked"):
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
