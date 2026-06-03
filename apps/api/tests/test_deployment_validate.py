from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from scripts.deployment_validate import DeploymentValidator, render_markdown


def write_valid_deployment_fixture(root: Path) -> None:
    root.joinpath("Docs/release-artifacts").mkdir(parents=True)
    root.joinpath("Docs/eval-reports").mkdir(parents=True)
    root.joinpath("Docs/DEPLOYMENT_GUIDE.md").write_text(
        """
# Deploy

## Local Docker Compose
docker compose up -d --build
alembic upgrade head

## Single-VM Deployment
Use TLS and reverse proxy.

## Managed Postgres And Redis
Use managed data services.

## Secrets
Keep GITHUB_WRITES_ENABLED=false before smoke proof.

## Storage And Cleanup
Use named volumes.

## Backups
Back up Postgres and secrets.

## Observability
Set OTEL_EXPORTER_OTLP_ENDPOINT.

## Rollback
Disable writes and revert image.

## Production Readiness Gate
Require eval and smoke proof.
""",
        encoding="utf-8",
    )
    root.joinpath(".env.example").write_text(
        "\n".join(
            [
                "POSTGRES_PASSWORD=",
                "REDIS_PASSWORD=",
                "GITHUB_WEBHOOK_SECRET=",
                "SESSION_SECRET_KEY=",
                "GITHUB_APP_ID=",
                "GITHUB_INSTALLATION_ID=",
                "GITHUB_CLIENT_ID=",
                "GITHUB_CLIENT_SECRET=",
                "MODEL_PROVIDER=mock",
                "MODEL_NAME=mock-planner",
                "MODEL_API_KEY=",
                "GITHUB_WRITES_ENABLED=false",
                "REPOPILOT_ARTIFACT_STORE_ROOT=/tmp/repopilot-artifacts",
                "OTEL_EXPORTER_OTLP_ENDPOINT=",
            ]
        ),
        encoding="utf-8",
    )
    root.joinpath("docker-compose.yml").write_text(
        """
services:
  postgres:
    image: pgvector/pgvector:pg16
    healthcheck:
      test: ["CMD", "pg_isready"]
  redis:
    image: redis:7-alpine
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
  api:
    volumes:
      - agent_workspaces:/tmp/repopilot-agent-workspaces
      - agent_artifacts:/tmp/repopilot-artifacts
  worker:
    volumes:
      - agent_workspaces:/tmp/repopilot-agent-workspaces
      - agent_artifacts:/tmp/repopilot-artifacts
  beat:
    volumes:
      - agent_workspaces:/tmp/repopilot-agent-workspaces
      - agent_artifacts:/tmp/repopilot-artifacts
  web:
    image: demo
volumes:
  postgres_data:
  agent_workspaces:
  agent_artifacts:
  web_node_modules:
  web_next:
""",
        encoding="utf-8",
    )
    for artifact in [
        "Docs/release-artifacts/source-boundary-hygiene.md",
        "Docs/release-artifacts/source-boundary-hygiene.json",
        "Docs/release-artifacts/source-boundary-manifest.md",
        "Docs/release-artifacts/source-boundary-manifest.json",
        "Docs/release-artifacts/release-gifs.md",
        "Docs/release-artifacts/release-gifs.json",
        "Docs/release-artifacts/deployment-runtime-smoke.md",
        "Docs/release-artifacts/deployment-runtime-smoke.json",
        "Docs/release-artifacts/credential-readiness-snapshot.md",
        "Docs/release-artifacts/credential-readiness-snapshot.json",
        "Docs/release-artifacts/security-scanner-snapshot.md",
        "Docs/release-artifacts/security-scanner-snapshot.json",
        "Docs/eval-reports/v1-local-latest.md",
        "Docs/eval-reports/v1-local-latest.json",
    ]:
        root.joinpath(artifact).write_text("{}", encoding="utf-8")
    for index in range(6):
        root.joinpath(f"Docs/release-artifacts/operator-console-{index}.png").write_bytes(b"png")
    for index in range(2):
        root.joinpath(f"Docs/release-artifacts/operator-console-flow-{index}.gif").write_bytes(b"gif")


def test_deployment_validator_passes_complete_static_fixture(tmp_path: Path) -> None:
    write_valid_deployment_fixture(tmp_path)

    report = DeploymentValidator(root=tmp_path).validate()

    assert report.failed is False
    assert report.warning_count == 0
    assert "Deployment Validation Report" in render_markdown(report)


def test_deployment_validator_reports_missing_compose_service_and_env_key(tmp_path: Path) -> None:
    write_valid_deployment_fixture(tmp_path)
    tmp_path.joinpath(".env.example").write_text("POSTGRES_PASSWORD=\n", encoding="utf-8")
    tmp_path.joinpath("docker-compose.yml").write_text("services:\n  api:\n    volumes: []\nvolumes:\n  agent_workspaces:\n", encoding="utf-8")

    report = DeploymentValidator(root=tmp_path).validate()

    assert report.failed is True
    assert any(finding.check == "compose_service" and finding.target == "redis" for finding in report.findings)
    assert any(finding.check == "env_example_key" and finding.target == "MODEL_API_KEY" for finding in report.findings)


def test_deployment_validator_reports_missing_release_artifacts(tmp_path: Path) -> None:
    write_valid_deployment_fixture(tmp_path)
    tmp_path.joinpath("Docs/eval-reports/v1-local-latest.md").unlink()

    report = DeploymentValidator(root=tmp_path).validate()

    assert report.failed is True
    assert any(finding.check == "release_artifact" and finding.target == "Docs/eval-reports/v1-local-latest.md" for finding in report.findings)


def test_deployment_validator_requires_release_gifs(tmp_path: Path) -> None:
    write_valid_deployment_fixture(tmp_path)
    for gif_path in tmp_path.glob("Docs/release-artifacts/*.gif"):
        gif_path.unlink()

    report = DeploymentValidator(root=tmp_path).validate()

    assert report.failed is True
    assert any(finding.check == "release_artifact" and "release GIFs" in finding.detail for finding in report.findings)


def test_deployment_validator_runtime_check_passes_when_local_urls_respond(tmp_path: Path, monkeypatch) -> None:
    write_valid_deployment_fixture(tmp_path)
    requested_urls: list[str] = []

    def fake_run(command: list[str], capture_output: bool, check: bool, text: bool) -> SimpleNamespace:
        requested_urls.append(command[-1])
        assert "--max-time" in command
        assert capture_output is True
        assert check is False
        assert text is True
        return SimpleNamespace(returncode=0, stdout="200", stderr="")

    monkeypatch.setattr("scripts.deployment_validate.shutil.which", lambda name: "/usr/bin/curl")
    monkeypatch.setattr("scripts.deployment_validate.subprocess.run", fake_run)

    report = DeploymentValidator(root=tmp_path).validate(check_runtime=True)

    assert report.failed is False
    assert "http://127.0.0.1:8000/health" in requested_urls
    assert "http://127.0.0.1:3001/" in requested_urls


def test_deployment_validator_runtime_check_reports_unreachable_local_url(tmp_path: Path, monkeypatch) -> None:
    write_valid_deployment_fixture(tmp_path)

    def fake_run(command: list[str], capture_output: bool, check: bool, text: bool) -> SimpleNamespace:
        return SimpleNamespace(returncode=7, stdout="000", stderr="connection refused")

    monkeypatch.setattr("scripts.deployment_validate.shutil.which", lambda name: "/usr/bin/curl")
    monkeypatch.setattr("scripts.deployment_validate.subprocess.run", fake_run)

    report = DeploymentValidator(root=tmp_path).validate(check_runtime=True)

    assert report.failed is True
    assert any(finding.check == "runtime_http" and finding.target == "api_health" for finding in report.findings)


def test_deployment_validator_runtime_check_reports_curl_timeout(tmp_path: Path, monkeypatch) -> None:
    write_valid_deployment_fixture(tmp_path)

    def fake_run(command: list[str], capture_output: bool, check: bool, text: bool) -> SimpleNamespace:
        return SimpleNamespace(returncode=28, stdout="000", stderr="timed out")

    monkeypatch.setattr("scripts.deployment_validate.shutil.which", lambda name: "/usr/bin/curl")
    monkeypatch.setattr("scripts.deployment_validate.subprocess.run", fake_run)

    report = DeploymentValidator(root=tmp_path).validate(check_runtime=True)

    assert report.failed is True
    assert any(finding.check == "runtime_http" and "timed out" in finding.detail for finding in report.findings)


def test_deployment_validator_runtime_check_reports_missing_curl(tmp_path: Path, monkeypatch) -> None:
    write_valid_deployment_fixture(tmp_path)
    monkeypatch.setattr("scripts.deployment_validate.shutil.which", lambda name: None)

    report = DeploymentValidator(root=tmp_path).validate(check_runtime=True)

    assert report.failed is True
    assert any(finding.check == "runtime_http" and "curl is required" in finding.detail for finding in report.findings)
