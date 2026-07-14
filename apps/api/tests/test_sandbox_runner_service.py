from __future__ import annotations

import sys
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from repopilot_contracts import SandboxCommandRequest

from app.core.config import settings
from app.services import sandbox as sandbox_service
from services.sandbox_runner import server as runner_server


def test_runner_rejects_workspace_escape_before_execution(monkeypatch, tmp_path: Path) -> None:
    run_id = uuid4()
    workspace_root = tmp_path / "workspaces"
    workspace_root.mkdir()
    (workspace_root / str(run_id)).mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.setattr(runner_server, "WORKSPACE_ROOT", workspace_root)

    status_code, result = runner_server.execute_request(
        {
            "run_id": str(run_id),
            "workspace_path": str(outside),
            "command": "python -m pytest",
            "timeout_seconds": 10,
        }
    )

    assert status_code == 403
    assert result["status"] == "blocked"
    assert "exactly match" in result["blocked_reason"]


def test_runner_rechecks_command_policy(monkeypatch, tmp_path: Path) -> None:
    run_id = uuid4()
    workspace_root = tmp_path / "workspaces"
    workspace_root.mkdir()
    workspace = workspace_root / str(run_id)
    workspace.mkdir()
    monkeypatch.setattr(runner_server, "WORKSPACE_ROOT", workspace_root)

    status_code, result = runner_server.execute_request(
        {
            "run_id": str(run_id),
            "workspace_path": str(workspace),
            "command": "curl https://example.com",
            "timeout_seconds": 10,
        }
    )

    assert status_code == 403
    assert result["status"] == "blocked"
    assert result["blocked_reason"] == "Command is not allowlisted."


def test_runner_kills_timed_out_process_group(tmp_path: Path) -> None:
    started = time.monotonic()

    result = runner_server.run_process(
        command="python -m pytest",
        args=[sys.executable, "-c", "import time; time.sleep(5)"],
        working_directory=tmp_path,
        timeout_seconds=0.1,  # type: ignore[arg-type]
        started=started,
    )

    assert result["status"] == "failed"
    assert result["exit_code"] is None
    assert result["stderr"] == "Command timed out."
    assert time.monotonic() - started < 2


def test_runner_redacts_secret_shaped_output() -> None:
    assert "sk-live-secret-value" not in runner_server.redact("token=sk-live-secret-value-1234567890")
    assert "[REDACTED" in runner_server.redact("token=sk-live-secret-value-1234567890")


def test_runner_executes_inside_bounded_nested_working_directory(monkeypatch, tmp_path: Path) -> None:
    run_id = uuid4()
    workspace_root = tmp_path / "workspaces"
    workspace = workspace_root / str(run_id)
    project = workspace / "apps" / "api"
    project.mkdir(parents=True)
    monkeypatch.setattr(runner_server, "WORKSPACE_ROOT", workspace_root)
    monkeypatch.setattr(
        runner_server,
        "safe_environment",
        lambda: {"PATH": str(Path(sys.executable).parent), "HOME": "/tmp", "TMPDIR": "/tmp"},
    )

    status_code, result = runner_server.execute_request(
        {
            "run_id": str(run_id),
            "workspace_path": str(workspace),
            "working_directory": "apps/api",
            "command": "python -m pytest --version",
            "timeout_seconds": 10,
        }
    )

    assert status_code == 200
    assert result["status"] == "passed"
    assert "pytest" in result["stdout"]


def test_runner_rejects_working_directory_escape(monkeypatch, tmp_path: Path) -> None:
    run_id = uuid4()
    workspace_root = tmp_path / "workspaces"
    workspace = workspace_root / str(run_id)
    workspace.mkdir(parents=True)
    monkeypatch.setattr(runner_server, "WORKSPACE_ROOT", workspace_root)

    status_code, result = runner_server.execute_request(
        {
            "run_id": str(run_id),
            "workspace_path": str(workspace),
            "working_directory": "../outside",
            "command": "python -m pytest",
            "timeout_seconds": 10,
        }
    )

    assert status_code == 403
    assert result["status"] == "blocked"
    assert "relative" in result["blocked_reason"]


class FakeRunnerClient:
    def __init__(self, response_payload: dict[str, object]) -> None:
        self.response_payload = response_payload
        self.request: dict[str, object] | None = None

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def post(self, path: str, *, headers: dict[str, str], json: dict[str, object]):
        self.request = {"path": path, "headers": headers, "json": json}
        return SimpleNamespace(status_code=200, json=lambda: self.response_payload)


def test_api_remote_backend_sends_bounded_run_request(monkeypatch, tmp_path: Path) -> None:
    run_id = uuid4()
    workspace_root = tmp_path / "workspaces"
    workspace = workspace_root / str(run_id)
    workspace.mkdir(parents=True)
    monkeypatch.setattr(sandbox_service, "WORKSPACE_ROOT", workspace_root)
    monkeypatch.setattr(settings, "sandbox_runner_token", "test-token-012345678901234567890123456789")
    client = FakeRunnerClient(
        {
            "command": "python -m pytest",
            "status": "passed",
            "exit_code": 0,
            "duration_ms": 12,
            "stdout": "1 passed",
            "stderr": "",
            "blocked_reason": None,
        }
    )
    runner = sandbox_service.SandboxRunner(backend="remote")
    monkeypatch.setattr(runner, "_remote_client", lambda **_kwargs: client)

    result = runner.run_command(
        SandboxCommandRequest(
            workspace_path=str(workspace),
            command="python -m pytest",
            timeout_seconds=30,
        ),
        run_id=run_id,
    )

    assert result.status == "passed"
    assert client.request is not None
    assert client.request["path"] == "/v1/execute"
    assert client.request["json"] == {
        "run_id": str(run_id),
        "workspace_path": str(workspace),
        "working_directory": ".",
        "command": "python -m pytest",
        "timeout_seconds": 30,
    }
