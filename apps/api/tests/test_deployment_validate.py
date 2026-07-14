from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from scripts.deployment_validate import DeploymentValidator, render_markdown


def write_valid_deployment_fixture(root: Path) -> None:
    root.joinpath("Docs/release-artifacts").mkdir(parents=True)
    root.joinpath("Docs/eval-reports").mkdir(parents=True)
    root.joinpath("Docs/ADRs").mkdir(parents=True)
    for doc in [
        "Docs/README.md",
        "Docs/ARCHITECTURE.md",
        "Docs/CREDENTIAL_HANDOFF.md",
        "Docs/DEMO_SCRIPT.md",
        "Docs/EVALS.md",
        "Docs/GITHUB_APP_SETUP.md",
        "Docs/MODEL_TESTING.md",
        "Docs/QUICKSTART.md",
        "Docs/RELEASE_CHECKLIST.md",
        "Docs/RELEASE_NOTES.md",
        "Docs/ROADMAP.md",
        "Docs/RUNBOOK.md",
        "Docs/SECURITY.md",
        "Docs/ADRs/0001-local-platform-stack.md",
    ]:
        root.joinpath(doc).write_text("# Public doc\n", encoding="utf-8")
    root.joinpath("Docs/DEPLOYMENT_GUIDE.md").write_text(
        """
# Deploy

## Local Docker Compose
docker compose up -d --build
docker compose -f docker-compose.ghcr.yml pull
alembic upgrade head

## Single-VM Deployment
Use TLS and reverse proxy.

## Managed Postgres And Redis
Use managed data services.

## Secrets
Keep GITHUB_WRITES_ENABLED=false before smoke proof.
Keep EMBEDDING_SOURCE_TRANSFER_ENABLED=false before source transfer approval.

## Provider Data Transfer
Live providers are explicit opt-in.

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
                "REPOPILOT_GITHUB_OWNER_LOGIN=octocat",
                "REPOPILOT_IMAGE_TAG=latest",
                "REPOPILOT_API_IMAGE=",
                "REPOPILOT_WEB_IMAGE=",
                "REPOPILOT_SANDBOX_IMAGE=",
                "SANDBOX_RUNNER_SOCKET=/run/repopilot-sandbox/runner.sock",
                "SANDBOX_RUNNER_TOKEN=test-sandbox-token-012345678901234567890123",
                "MODEL_PROVIDER=mock",
                "MODEL_NAME=mock-planner",
                "MODEL_API_KEY=",
                "EMBEDDING_SOURCE_TRANSFER_ENABLED=false",
                "GITHUB_WRITES_ENABLED=false",
                "GITHUB_WORKFLOW_LOG_MAX_BYTES=25000000",
                "WEBHOOK_DISPATCH_RETRY_INTERVAL_SECONDS=30",
                "WEBHOOK_DISPATCH_MAX_RETRIES=8",
                "REPOPILOT_REPOSITORY_ARCHIVE_MAX_BYTES=100000000",
                "REPOPILOT_REPOSITORY_ARCHIVE_MAX_UNPACKED_BYTES=500000000",
                "REPOPILOT_REPOSITORY_ARCHIVE_MAX_ENTRIES=20000",
                "REPOPILOT_ARTIFACT_STORE_ROOT=/tmp/repopilot-artifacts",
                "REPOPILOT_RUNTIME_SECRETS_KEY_PATH=/home/appuser/.repopilot/runtime-secrets.key",
                "REPOPILOT_RUNTIME_SECRETS_STORE_PATH=/home/appuser/.repopilot/runtime-secrets.json",
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
    healthcheck:
      test: ["CMD", "curl", "http://localhost:8000/health"]
    environment:
      REPOPILOT_RUNTIME_SECRETS_KEY_PATH: /home/appuser/.repopilot/runtime-secrets.key
      REPOPILOT_RUNTIME_SECRETS_STORE_PATH: /home/appuser/.repopilot/runtime-secrets.json
    volumes:
      - ./.local/repopilot-secrets:/home/appuser/.repopilot
      - agent_workspaces:/tmp/repopilot-agent-workspaces
      - repository_workspaces:/tmp/repopilot-repositories
      - agent_artifacts:/tmp/repopilot-artifacts
      - sandbox_control:/run/repopilot-sandbox:ro
  worker:
    environment:
      REPOPILOT_RUNTIME_SECRETS_KEY_PATH: /home/appuser/.repopilot/runtime-secrets.key
      REPOPILOT_RUNTIME_SECRETS_STORE_PATH: /home/appuser/.repopilot/runtime-secrets.json
    volumes:
      - ./.local/repopilot-secrets:/home/appuser/.repopilot
      - agent_workspaces:/tmp/repopilot-agent-workspaces
      - repository_workspaces:/tmp/repopilot-repositories
      - agent_artifacts:/tmp/repopilot-artifacts
      - sandbox_control:/run/repopilot-sandbox:ro
  storage-init:
    image: repopilot-sandbox:local
    user: "0:0"
    network_mode: none
    command: chown -R 10001:10001 /tmp/repopilot-agent-workspaces /tmp/repopilot-repositories /tmp/repopilot-artifacts /run/repopilot-sandbox
    volumes:
      - agent_workspaces:/tmp/repopilot-agent-workspaces
      - repository_workspaces:/tmp/repopilot-repositories
      - agent_artifacts:/tmp/repopilot-artifacts
      - sandbox_control:/run/repopilot-sandbox
  beat:
    environment:
      REPOPILOT_RUNTIME_SECRETS_KEY_PATH: /home/appuser/.repopilot/runtime-secrets.key
      REPOPILOT_RUNTIME_SECRETS_STORE_PATH: /home/appuser/.repopilot/runtime-secrets.json
    volumes:
      - ./.local/repopilot-secrets:/home/appuser/.repopilot
      - agent_workspaces:/tmp/repopilot-agent-workspaces
      - agent_artifacts:/tmp/repopilot-artifacts
  web:
    image: demo
  sandbox-runner:
    image: repopilot-sandbox:local
    network_mode: none
    read_only: true
    cap_drop: [ALL]
    security_opt: [no-new-privileges:true]
    pids_limit: 256
    volumes:
      - agent_workspaces:/tmp/repopilot-agent-workspaces
      - sandbox_control:/run/repopilot-sandbox
volumes:
  postgres_data:
  agent_workspaces:
  repository_workspaces:
  agent_artifacts:
  sandbox_control:
  web_node_modules:
  web_next:
""",
        encoding="utf-8",
    )
    root.joinpath("docker-compose.ghcr.yml").write_text(
        """
services:
  postgres:
    image: pgvector/pgvector:pg16
  redis:
    image: redis:7-alpine
  api:
    image: ghcr.io/harshalrane04/repopilot-api:latest
    volumes:
      - ./.local/repopilot-secrets:/home/appuser/.repopilot
      - agent_workspaces:/tmp/repopilot-agent-workspaces
      - agent_artifacts:/tmp/repopilot-artifacts
  worker:
    image: ghcr.io/harshalrane04/repopilot-api:latest
    volumes:
      - ./.local/repopilot-secrets:/home/appuser/.repopilot
      - agent_workspaces:/tmp/repopilot-agent-workspaces
      - agent_artifacts:/tmp/repopilot-artifacts
  storage-init:
    image: ghcr.io/harshalrane04/repopilot-sandbox:latest
    user: "0:0"
    network_mode: none
    command: chown -R 10001:10001 /tmp/repopilot-agent-workspaces /tmp/repopilot-repositories /tmp/repopilot-artifacts /run/repopilot-sandbox
    volumes:
      - agent_workspaces:/tmp/repopilot-agent-workspaces
      - repository_workspaces:/tmp/repopilot-repositories
      - agent_artifacts:/tmp/repopilot-artifacts
      - sandbox_control:/run/repopilot-sandbox
  beat:
    image: ghcr.io/harshalrane04/repopilot-api:latest
    volumes:
      - ./.local/repopilot-secrets:/home/appuser/.repopilot
      - agent_workspaces:/tmp/repopilot-agent-workspaces
      - agent_artifacts:/tmp/repopilot-artifacts
  web:
    image: ghcr.io/harshalrane04/repopilot-web:latest
  sandbox-runner:
    image: ghcr.io/harshalrane04/repopilot-sandbox:latest
    network_mode: none
    read_only: true
    cap_drop: [ALL]
    security_opt: [no-new-privileges:true]
    volumes:
      - sandbox_control:/run/repopilot-sandbox
volumes:
  postgres_data:
  agent_workspaces:
  agent_artifacts:
  sandbox_control:
""",
        encoding="utf-8",
    )

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


def test_deployment_validator_blocks_unsafe_embedding_transfer_default(tmp_path: Path) -> None:
    write_valid_deployment_fixture(tmp_path)
    env_text = tmp_path.joinpath(".env.example").read_text(encoding="utf-8")
    tmp_path.joinpath(".env.example").write_text(env_text.replace("EMBEDDING_SOURCE_TRANSFER_ENABLED=false", "EMBEDDING_SOURCE_TRANSFER_ENABLED=true"), encoding="utf-8")

    report = DeploymentValidator(root=tmp_path).validate()

    assert report.failed is True
    assert any(
        finding.check == "env_example_safe_default" and finding.target == "EMBEDDING_SOURCE_TRANSFER_ENABLED"
        for finding in report.findings
    )


def test_deployment_validator_reports_missing_public_doc(tmp_path: Path) -> None:
    write_valid_deployment_fixture(tmp_path)
    tmp_path.joinpath("Docs/ROADMAP.md").unlink()

    report = DeploymentValidator(root=tmp_path).validate()

    assert report.failed is True
    assert any(finding.check == "public_doc" and finding.target == "Docs/ROADMAP.md" for finding in report.findings)


def test_deployment_validator_blocks_dev_only_ghcr_compose(tmp_path: Path) -> None:
    write_valid_deployment_fixture(tmp_path)
    tmp_path.joinpath("docker-compose.ghcr.yml").write_text(
        """
services:
  postgres:
    image: pgvector/pgvector:pg16
  redis:
    image: redis:7-alpine
  api:
    build: .
    command: uvicorn app.main:app --reload
    volumes:
      - ./apps/api:/app/apps/api
  worker:
    image: ghcr.io/harshalrane04/repopilot-api:latest
  beat:
    image: ghcr.io/harshalrane04/repopilot-api:latest
  web:
    image: ghcr.io/harshalrane04/repopilot-web:latest
    command: npm run dev
    volumes:
      - ./apps/web:/app/apps/web
      - web_node_modules:/app/apps/web/node_modules
      - web_next:/app/apps/web/.next
  sandbox-image:
    image: ghcr.io/harshalrane04/repopilot-sandbox:latest
volumes:
  postgres_data:
  agent_workspaces:
  agent_artifacts:
  web_node_modules:
  web_next:
""",
        encoding="utf-8",
    )

    report = DeploymentValidator(root=tmp_path).validate()

    assert report.failed is True
    assert any(finding.check == "ghcr_compose_release_boundary" and finding.target == "build:" for finding in report.findings)
    assert any(finding.check == "ghcr_compose_release_boundary" and finding.target == "npm run dev" for finding in report.findings)


def test_deployment_validator_requires_generated_evidence_directories(tmp_path: Path) -> None:
    write_valid_deployment_fixture(tmp_path)
    tmp_path.joinpath("Docs/release-artifacts").rmdir()

    report = DeploymentValidator(root=tmp_path).validate()

    assert report.failed is True
    assert any(finding.check == "generated_evidence_dir" and finding.target == "Docs/release-artifacts" for finding in report.findings)


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
    assert "http://127.0.0.1:8000/ready" in requested_urls
    assert "http://127.0.0.1:3001/" in requested_urls


def test_deployment_validator_runtime_check_reports_unreachable_local_url(tmp_path: Path, monkeypatch) -> None:
    write_valid_deployment_fixture(tmp_path)

    def fake_run(command: list[str], capture_output: bool, check: bool, text: bool) -> SimpleNamespace:
        return SimpleNamespace(returncode=7, stdout="000", stderr="connection refused")

    monkeypatch.setattr("scripts.deployment_validate.shutil.which", lambda name: "/usr/bin/curl")
    monkeypatch.setattr("scripts.deployment_validate.subprocess.run", fake_run)

    report = DeploymentValidator(root=tmp_path).validate(check_runtime=True)

    assert report.failed is True
    assert any(finding.check == "runtime_http" and finding.target == "api_ready" for finding in report.findings)


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
