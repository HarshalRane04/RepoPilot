from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
MAKEFILE = ROOT / "Makefile"


def makefile_text() -> str:
    return MAKEFILE.read_text(encoding="utf-8")


def target_body(text: str, target: str) -> str:
    lines = text.splitlines()
    header = f"{target}:"
    for index, line in enumerate(lines):
        if line.startswith(header):
            body: list[str] = []
            for body_line in lines[index + 1 :]:
                if body_line and not body_line.startswith(("\t", " ")):
                    break
                if body_line.strip():
                    body.append(body_line.strip())
            return "\n".join(body)
    raise AssertionError(f"Missing Makefile target: {target}")


def target_dependencies(text: str, target: str) -> list[str]:
    header_prefix = f"{target}:"
    for line in text.splitlines():
        if line.startswith(header_prefix):
            return line.removeprefix(header_prefix).split()
    raise AssertionError(f"Missing Makefile target: {target}")


def assert_no_allow_flags(body: str) -> None:
    assert "--allow-blocked" not in body
    assert "--allow-warnings" not in body
    assert "--allow-failures" not in body


def test_credential_smoke_strict_runs_without_blocked_placeholder_flag() -> None:
    body = target_body(makefile_text(), "credential-smoke-strict")

    assert "scripts/credential_smoke.py" in body
    assert "--allow-blocked" not in body


def test_init_local_env_target_runs_bootstrap_script() -> None:
    body = target_body(makefile_text(), "init-local-env")

    assert "scripts/init_local_env.py" in body


def test_up_target_starts_compose_detached() -> None:
    body = target_body(makefile_text(), "up")

    assert "up -d --build" in body


def test_ghcr_targets_use_released_image_compose_file() -> None:
    text = makefile_text()

    assert "COMPOSE_GHCR ?= $(COMPOSE) -f docker-compose.ghcr.yml" in text
    assert "$(COMPOSE_GHCR) pull" in target_body(text, "ghcr-pull")
    assert "$(COMPOSE_GHCR) up -d" in target_body(text, "ghcr-up")
    assert "$(COMPOSE_GHCR) exec api alembic upgrade head" in target_body(text, "ghcr-migrate")


def test_release_hygiene_strict_runs_without_warning_or_failure_placeholder_flags() -> None:
    body = target_body(makefile_text(), "release-hygiene-strict")

    assert "scripts/release_hygiene.py" in body
    assert "--allow-warnings" not in body
    assert "--allow-failures" not in body


def test_deployment_validate_strict_runs_without_allow_flags() -> None:
    body = target_body(makefile_text(), "deployment-validate-strict")

    assert "scripts/deployment_validate.py" in body
    assert_no_allow_flags(body)


def test_deployment_smoke_strict_checks_runtime_without_allow_flags() -> None:
    body = target_body(makefile_text(), "deployment-smoke-strict")

    assert "scripts/deployment_validate.py" in body
    assert "--check-runtime" in body
    assert_no_allow_flags(body)


def test_release_verify_depends_on_all_strict_release_targets() -> None:
    dependencies = target_dependencies(makefile_text(), "release-verify")

    assert dependencies == [
        "source-boundary-manifest",
        "release-hygiene-strict",
        "credential-smoke-strict",
        "security-scanner-snapshot-strict",
        "deployment-validate-strict",
        "deployment-smoke-strict",
    ]
