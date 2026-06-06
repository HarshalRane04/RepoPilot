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
    ROOT,
    ROOT / "apps" / "api",
    ROOT / "packages" / "shared_contracts",
    ROOT / "packages" / "evals",
    ROOT / "packages" / "policy_engine",
    ROOT / "packages" / "llm_client",
    ROOT / "packages" / "github_client",
):
    sys.path.insert(0, str(path))

from scripts.github_app_smoke import GitHubAppSmoke, capture_github_app_smoke  # noqa: E402
from scripts.github_oauth_smoke import GitHubOAuthSmoke, capture_github_oauth_smoke  # noqa: E402
from scripts.model_provider_smoke import ModelProviderSmoke, capture_model_provider_smoke  # noqa: E402


@dataclass(frozen=True)
class CredentialSmokeSummary:
    generated_at: str
    ok: bool
    status: str
    github_oauth_status: str
    github_app_status: str
    model_provider_status: str
    github_oauth_ok: bool
    github_app_ok: bool
    model_provider_ok: bool
    github_oauth_detail: str
    github_app_detail: str
    model_provider_detail: str
    next_step: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def summarize_credentials(
    *,
    generated_at: str,
    github_oauth: GitHubOAuthSmoke,
    github_app: GitHubAppSmoke,
    model_provider: ModelProviderSmoke,
) -> CredentialSmokeSummary:
    statuses = (github_oauth.status, github_app.status, model_provider.status)
    ok = github_oauth.ok and github_app.ok and model_provider.ok
    if ok:
        status = "passed"
        next_step = "Run credentialed repository sync, webhook delivery, collaborator permission, provider eval, and draft-PR smoke tests."
    elif "failed" in statuses:
        status = "failed"
        next_step = "Fix the failed credential smoke item before enabling GitHub writes or live provider release claims."
    else:
        status = "blocked"
        next_step = "Save missing runtime secrets through the dashboard or make configure-runtime-secrets, then rerun make credential-smoke."

    return CredentialSmokeSummary(
        generated_at=generated_at,
        ok=ok,
        status=status,
        github_oauth_status=github_oauth.status,
        github_app_status=github_app.status,
        model_provider_status=model_provider.status,
        github_oauth_ok=github_oauth.ok,
        github_app_ok=github_app.ok,
        model_provider_ok=model_provider.ok,
        github_oauth_detail=github_oauth.detail,
        github_app_detail=github_app.detail,
        model_provider_detail=model_provider.detail,
        next_step=next_step,
    )


async def capture_credential_smoke_summary() -> CredentialSmokeSummary:
    generated_at = datetime.now(UTC).isoformat()
    github_oauth = capture_github_oauth_smoke()
    github_app = await capture_github_app_smoke()
    model_provider = await capture_model_provider_smoke()
    return summarize_credentials(
        generated_at=generated_at,
        github_oauth=github_oauth,
        github_app=github_app,
        model_provider=model_provider,
    )


def render_markdown(summary: CredentialSmokeSummary) -> str:
    return "\n".join(
        [
            "# RepoPilot Credential Smoke Summary",
            "",
            f"- Generated at: `{summary.generated_at}`",
            f"- Status: `{summary.status}`",
            f"- GitHub OAuth: `{summary.github_oauth_status}`",
            f"- GitHub App: `{summary.github_app_status}`",
            f"- Model provider: `{summary.model_provider_status}`",
            "",
            "## Details",
            "",
            "| Gate | OK | Status | Detail |",
            "|---|---|---|---|",
            f"| GitHub OAuth | `{summary.github_oauth_ok}` | `{summary.github_oauth_status}` | {summary.github_oauth_detail} |",
            f"| GitHub App | `{summary.github_app_ok}` | `{summary.github_app_status}` | {summary.github_app_detail} |",
            f"| Model provider | `{summary.model_provider_ok}` | `{summary.model_provider_status}` | {summary.model_provider_detail} |",
            "",
            "## Next Step",
            "",
            summary.next_step,
            "",
        ]
    )


def write_outputs(*, summary: CredentialSmokeSummary, json_out: Path | None, md_out: Path | None) -> None:
    if json_out:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps(summary.as_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if md_out:
        md_out.parent.mkdir(parents=True, exist_ok=True)
        md_out.write_text(render_markdown(summary), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run RepoPilot's redacted GitHub OAuth, GitHub App, and model-provider smoke checks.")
    parser.add_argument("--json-out", type=Path, default=Path("Docs/release-artifacts/credential-smoke-summary.json"))
    parser.add_argument("--md-out", type=Path, default=Path("Docs/release-artifacts/credential-smoke-summary.md"))
    parser.add_argument("--allow-blocked", action="store_true", help="Exit successfully when credentials are missing and a blocked artifact was written.")
    return parser


async def async_main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = await capture_credential_smoke_summary()
    write_outputs(summary=summary, json_out=args.json_out, md_out=args.md_out)
    print(render_markdown(summary))
    if summary.ok or (args.allow_blocked and summary.status == "blocked"):
        return 0
    return 1


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
