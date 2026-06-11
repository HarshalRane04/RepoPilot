from __future__ import annotations

from pathlib import Path

from scripts.init_local_env import initialize_env, parse_env_values


def write_template(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "POSTGRES_PASSWORD=",
                "REDIS_PASSWORD=",
                "GITHUB_WEBHOOK_SECRET=",
                "SESSION_SECRET_KEY=",
                "DEV_HEADER_AUTH_ENABLED=false",
                "GITHUB_WRITES_ENABLED=false",
                "MODEL_PROVIDER=mock",
                "MODEL_NAME=mock-planner",
                "MODEL_API_KEY=",
                "GITHUB_APP_ID=",
                "GITHUB_CLIENT_SECRET=",
                "REPOPILOT_RELEASE_PROFILE=oss-demo",
                "ALLOW_MODEL_FALLBACK=false",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_init_local_env_creates_local_safe_env_without_live_credentials(tmp_path: Path) -> None:
    template = tmp_path / ".env.example"
    env_file = tmp_path / ".env"
    write_template(template)

    result = initialize_env(template_path=template, env_path=env_file)
    values = parse_env_values(env_file.read_text(encoding="utf-8"))

    assert result["created"] is True
    assert values["POSTGRES_PASSWORD"].startswith("repopilot-local-postgres-")
    assert values["REDIS_PASSWORD"].startswith("repopilot-local-redis-")
    assert values["GITHUB_WEBHOOK_SECRET"].startswith("repopilot-local-webhook-")
    assert values["SESSION_SECRET_KEY"].startswith("repopilot-local-session-")
    assert values["DEV_HEADER_AUTH_ENABLED"] == "true"
    assert values["GITHUB_WRITES_ENABLED"] == "false"
    assert values["MODEL_PROVIDER"] == "mock"
    assert values["MODEL_NAME"] == "mock-planner"
    assert values["ALLOW_MODEL_FALLBACK"] == "false"
    assert values["REPOPILOT_RELEASE_PROFILE"] == "oss-demo"
    assert values["MODEL_API_KEY"] == ""
    assert values["GITHUB_APP_ID"] == ""
    assert values["GITHUB_CLIENT_SECRET"] == ""


def test_init_local_env_preserves_existing_non_placeholder_values(tmp_path: Path) -> None:
    template = tmp_path / ".env.example"
    env_file = tmp_path / ".env"
    write_template(template)
    env_file.write_text(
        "\n".join(
            [
                "POSTGRES_PASSWORD=custom-postgres",
                "REDIS_PASSWORD=placeholder",
                "SESSION_SECRET_KEY=custom-session",
                "GITHUB_WEBHOOK_SECRET=",
                "MODEL_API_KEY=sk-existing-provider-key",
                "CUSTOM_LOCAL_SETTING=keep-me",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = initialize_env(template_path=template, env_path=env_file)
    values = parse_env_values(env_file.read_text(encoding="utf-8"))

    assert "POSTGRES_PASSWORD" in result["preserved"]
    assert "SESSION_SECRET_KEY" in result["preserved"]
    assert values["POSTGRES_PASSWORD"] == "custom-postgres"
    assert values["SESSION_SECRET_KEY"] == "custom-session"
    assert values["MODEL_API_KEY"] == "sk-existing-provider-key"
    assert values["CUSTOM_LOCAL_SETTING"] == "keep-me"
    assert values["REDIS_PASSWORD"].startswith("repopilot-local-redis-")
    assert values["GITHUB_WEBHOOK_SECRET"].startswith("repopilot-local-webhook-")
