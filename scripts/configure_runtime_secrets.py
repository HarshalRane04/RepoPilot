#!/usr/bin/env python3
from __future__ import annotations

import argparse
import getpass
import sys
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

from app.services.runtime_secrets import (  # noqa: E402
    GITHUB_APP_RUNTIME_SECRET_FIELDS,
    GITHUB_OAUTH_RUNTIME_SECRET_FIELDS,
    MODEL_RUNTIME_SECRET_FIELDS,
    runtime_secret_store,
)


def _prompt(label: str, *, default: str | None = None, secret: bool = False, required: bool = False) -> str:
    suffix = f" [{default}]" if default else ""
    while True:
        if secret:
            value = getpass.getpass(f"{label}{suffix}: ")
        else:
            value = input(f"{label}{suffix}: ")
        value = value.strip() or (default or "")
        if value or not required:
            return value
        print(f"{label} is required.")


def _collect_model(args: argparse.Namespace) -> dict[str, str]:
    print("\nModel provider")
    values = {
        "MODEL_PROVIDER": _prompt("Provider", default=args.provider, required=True),
        "MODEL_NAME": _prompt("Model", default=args.model, required=True),
        "MODEL_BASE_URL": _prompt("Base URL", default=args.base_url),
    }
    api_key = _prompt("Provider API key", secret=True, required=True)
    if api_key:
        values["MODEL_API_KEY"] = api_key
    reasoning = _prompt("Reasoning level", default=args.reasoning_level)
    if reasoning:
        values["MODEL_REASONING_LEVEL"] = reasoning
    return values


def _collect_oauth(args: argparse.Namespace) -> dict[str, str]:
    print("\nGitHub OAuth")
    return {
        "GITHUB_CLIENT_ID": _prompt("GitHub Client ID", default=args.github_client_id, required=True),
        "GITHUB_CLIENT_SECRET": _prompt("GitHub Client Secret", secret=True, required=True),
        "GITHUB_OAUTH_CALLBACK_URL": _prompt(
            "OAuth Callback URL",
            default=args.github_oauth_callback_url,
            required=True,
        ),
        "WEB_APP_URL": _prompt("Web App URL", default=args.web_app_url, required=True),
        "SESSION_SECRET_KEY": _prompt("Session Secret Key", secret=True, required=True),
        "GITHUB_API_BASE_URL": _prompt("GitHub API Base URL", default=args.github_api_base_url, required=True),
        "GITHUB_WEB_BASE_URL": _prompt("GitHub Web Base URL", default=args.github_web_base_url, required=True),
    }


def _collect_github_app(args: argparse.Namespace) -> dict[str, str]:
    print("\nGitHub App")
    values = {
        "GITHUB_WEBHOOK_SECRET": _prompt("Webhook Secret", secret=True, required=True),
        "GITHUB_APP_ID": _prompt("GitHub App ID", default=args.github_app_id, required=True),
        "GITHUB_APP_SLUG": _prompt("GitHub App Slug", default=args.github_app_slug),
        "GITHUB_INSTALLATION_ID": _prompt("Installation ID", default=args.github_installation_id, required=True),
    }
    key_path = _prompt("Private Key Path", default=args.github_private_key_path)
    if key_path:
        values["GITHUB_PRIVATE_KEY_PATH"] = key_path
    else:
        print("Paste the PEM private key. Finish with Ctrl-D on a blank line:")
        private_key = sys.stdin.read().strip()
        if private_key:
            values["GITHUB_APP_PRIVATE_KEY"] = private_key
    return values


def _print_summary(title: str, fields: set[str]) -> None:
    summary = runtime_secret_store().summary(fields)
    print(f"\n{title}")
    print(f"Encrypted store: {'present' if summary['store_exists'] else 'missing'}")
    print(f"Store permissions OK: {summary['store_permissions_ok']}")
    print(f"Key permissions OK: {summary['key_permissions_ok']}")
    for field in summary["fields"]:
        state = "configured" if field["configured"] else "missing"
        source = field["source"]
        marker = "secret" if field["secret"] else "setting"
        print(f"- {field['name']}: {state} ({marker}, {source})")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write RepoPilot runtime credentials to the local encrypted secret store.",
    )
    parser.add_argument("--model-only", action="store_true", help="Configure only model provider secrets.")
    parser.add_argument("--oauth-only", action="store_true", help="Configure only GitHub OAuth secrets.")
    parser.add_argument("--github-app-only", action="store_true", help="Configure only GitHub App secrets.")
    parser.add_argument("--provider", default="openrouter")
    parser.add_argument("--model", default="gemma-4-31b-it:free")
    parser.add_argument("--base-url", default="https://openrouter.ai/api/v1")
    parser.add_argument("--reasoning-level", default="")
    parser.add_argument("--github-client-id", default="")
    parser.add_argument("--github-oauth-callback-url", default="http://localhost:8000/auth/github/callback")
    parser.add_argument("--web-app-url", default="http://localhost:3001")
    parser.add_argument("--github-api-base-url", default="https://api.github.com")
    parser.add_argument("--github-web-base-url", default="https://github.com")
    parser.add_argument("--github-app-id", default="")
    parser.add_argument("--github-app-slug", default="")
    parser.add_argument("--github-installation-id", default="")
    parser.add_argument("--github-private-key-path", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    modes = [args.model_only, args.oauth_only, args.github_app_only]
    selected_specific_mode = any(modes)
    values: dict[str, str] = {}

    if args.model_only or not selected_specific_mode:
        values.update(_collect_model(args))
    if args.oauth_only or not selected_specific_mode:
        values.update(_collect_oauth(args))
    if args.github_app_only or not selected_specific_mode:
        values.update(_collect_github_app(args))

    runtime_secret_store().save_values(values)
    if args.model_only:
        _print_summary("Model runtime secret status", set(MODEL_RUNTIME_SECRET_FIELDS))
    elif args.oauth_only:
        _print_summary("GitHub OAuth runtime secret status", set(GITHUB_OAUTH_RUNTIME_SECRET_FIELDS))
    elif args.github_app_only:
        _print_summary("GitHub App runtime secret status", set(GITHUB_APP_RUNTIME_SECRET_FIELDS))
    else:
        _print_summary("Model runtime secret status", set(MODEL_RUNTIME_SECRET_FIELDS))
        _print_summary("GitHub OAuth runtime secret status", set(GITHUB_OAUTH_RUNTIME_SECRET_FIELDS))
        _print_summary("GitHub App runtime secret status", set(GITHUB_APP_RUNTIME_SECRET_FIELDS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
