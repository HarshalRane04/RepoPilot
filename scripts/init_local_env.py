from __future__ import annotations

import argparse
import secrets
from pathlib import Path


LOCAL_DEFAULT_KEYS = {
    "POSTGRES_PASSWORD",
    "REDIS_PASSWORD",
    "GITHUB_WEBHOOK_SECRET",
    "SESSION_SECRET_KEY",
    "DEV_HEADER_AUTH_ENABLED",
    "GITHUB_WRITES_ENABLED",
    "MODEL_PROVIDER",
    "MODEL_NAME",
    "ALLOW_MODEL_FALLBACK",
    "REPOPILOT_RELEASE_PROFILE",
}

PLACEHOLDER_VALUES = {"", "placeholder", "change-me", "change-me-local-dev", "change-me-session-secret", "todo"}


def local_default_value(key: str) -> str:
    token = secrets.token_urlsafe(24)
    defaults = {
        "POSTGRES_PASSWORD": f"repopilot-local-postgres-{token}",
        "REDIS_PASSWORD": f"repopilot-local-redis-{token}",
        "GITHUB_WEBHOOK_SECRET": f"repopilot-local-webhook-{token}",
        "SESSION_SECRET_KEY": f"repopilot-local-session-{secrets.token_urlsafe(48)}",
        "DEV_HEADER_AUTH_ENABLED": "true",
        "GITHUB_WRITES_ENABLED": "false",
        "MODEL_PROVIDER": "mock",
        "MODEL_NAME": "mock-planner",
        "ALLOW_MODEL_FALLBACK": "false",
        "REPOPILOT_RELEASE_PROFILE": "oss-demo",
    }
    return defaults[key]


def parse_env_values(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def should_replace(value: str | None) -> bool:
    if value is None:
        return True
    lowered = value.strip().strip('"').strip("'").lower()
    return lowered in PLACEHOLDER_VALUES or lowered.startswith("change-me")


def render_env(template_text: str, existing_values: dict[str, str]) -> tuple[str, list[str], list[str]]:
    written: list[str] = []
    preserved: list[str] = []
    seen: set[str] = set()
    lines: list[str] = []

    for line in template_text.splitlines():
        if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
            lines.append(line)
            continue
        key, template_value = line.split("=", 1)
        key = key.strip()
        seen.add(key)
        if key in LOCAL_DEFAULT_KEYS:
            current = existing_values.get(key)
            if should_replace(current):
                lines.append(f"{key}={local_default_value(key)}")
                written.append(key)
            else:
                lines.append(f"{key}={current}")
                preserved.append(key)
        else:
            current = existing_values.get(key, template_value)
            lines.append(f"{key}={current}")

    missing_local_keys = sorted(LOCAL_DEFAULT_KEYS.difference(seen))
    if missing_local_keys:
        lines.extend(["", "# Added by make init-local-env for local Compose startup."])
        for key in missing_local_keys:
            current = existing_values.get(key)
            if should_replace(current):
                lines.append(f"{key}={local_default_value(key)}")
                written.append(key)
            else:
                lines.append(f"{key}={current}")
                preserved.append(key)

    extra_existing_keys = sorted(set(existing_values).difference(seen))
    if extra_existing_keys:
        lines.extend(["", "# Preserved existing local values not present in .env.example."])
        for key in extra_existing_keys:
            lines.append(f"{key}={existing_values[key]}")
            preserved.append(key)

    return "\n".join(lines).rstrip() + "\n", sorted(set(written)), sorted(set(preserved))


def initialize_env(*, template_path: Path, env_path: Path) -> dict[str, object]:
    if not template_path.is_file():
        raise FileNotFoundError(f"Template file not found: {template_path}")
    template_text = template_path.read_text(encoding="utf-8")
    existing_text = env_path.read_text(encoding="utf-8") if env_path.is_file() else ""
    existing_values = parse_env_values(existing_text)
    rendered, written, preserved = render_env(template_text, existing_values)
    env_path.write_text(rendered, encoding="utf-8")
    return {
        "env_path": str(env_path),
        "template_path": str(template_path),
        "created": not bool(existing_text),
        "written": written,
        "preserved": preserved,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or repair a local .env for RepoPilot Docker Compose demos.")
    parser.add_argument("--template", default=".env.example", help="Template env file to read.")
    parser.add_argument("--env-file", default=".env", help="Local env file to create or update.")
    args = parser.parse_args()

    result = initialize_env(template_path=Path(args.template), env_path=Path(args.env_file))
    action = "created" if result["created"] else "updated"
    print(f"{action} {result['env_path']} from {result['template_path']}")
    if result["written"]:
        print("wrote local-safe values for: " + ", ".join(result["written"]))
    if result["preserved"]:
        print("preserved existing values for: " + ", ".join(result["preserved"]))
    print("live GitHub/model credentials remain blank; save them through Settings or make configure-runtime-secrets.")


if __name__ == "__main__":
    main()
