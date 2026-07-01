from __future__ import annotations

import os
import shlex
import subprocess
import sys
import time
from pathlib import Path
from uuid import UUID

from repopilot_contracts import PolicyDecisionType, SandboxCommandRequest, SandboxCommandResult, ValidationStatus

from app.core.config import settings
from app.services.path_safety import UnsafePathError, exact_existing_directory
from app.services.policy import PolicyEngine
from app.services.security_envelope import redact_text

WORKSPACE_ROOT = Path("/tmp/repopilot-agent-workspaces")


class SandboxRunner:
    def __init__(self, policy_engine: PolicyEngine | None = None, *, backend: str | None = None) -> None:
        self.policy_engine = policy_engine or PolicyEngine()
        self.backend = backend or settings.sandbox_backend

    def run_command(self, request: SandboxCommandRequest, *, run_id: UUID) -> SandboxCommandResult:
        policy = self.policy_engine.evaluate_command(request.command)
        if policy.decision != PolicyDecisionType.ALLOW:
            return SandboxCommandResult(
                command=request.command,
                status=ValidationStatus.BLOCKED,
                duration_ms=0,
                blocked_reason=policy.reason,
            )

        expected_workspace = (WORKSPACE_ROOT / str(run_id)).resolve()
        try:
            workspace = exact_existing_directory(
                request.workspace_path,
                expected=expected_workspace,
                label="Sandbox workspace",
            )
        except UnsafePathError as exc:
            return SandboxCommandResult(
                command=request.command,
                status=ValidationStatus.BLOCKED,
                duration_ms=0,
                blocked_reason=str(exc),
            )

        if self.backend == "docker":
            return self._run_docker(request=request, workspace=workspace)
        if self.backend == "local":
            if settings.environment != "local":
                return SandboxCommandResult(
                    command=request.command,
                    status=ValidationStatus.BLOCKED,
                    duration_ms=0,
                    blocked_reason="The local sandbox backend is only allowed when REPOPILOT_ENV=local.",
                )
            return self._run_local(request=request, workspace=workspace)

        return SandboxCommandResult(
            command=request.command,
            status=ValidationStatus.BLOCKED,
            duration_ms=0,
            blocked_reason=f"Unknown sandbox backend: {self.backend}",
        )

    def _run_docker(self, *, request: SandboxCommandRequest, workspace: Path) -> SandboxCommandResult:
        docker_command = [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--memory",
            settings.sandbox_memory_limit,
            "--cpus",
            settings.sandbox_cpus,
            "--pids-limit",
            str(settings.sandbox_pids_limit),
            "--workdir",
            "/workspace",
            "--volume",
            f"{workspace}:/workspace:rw",
        ]
        for key, value in self._safe_env().items():
            docker_command.extend(["--env", f"{key}={value}"])
        docker_command.extend([settings.sandbox_docker_image, *shlex.split(request.command)])

        return self._execute(command=request.command, args=docker_command, cwd=workspace, timeout_seconds=request.timeout_seconds)

    def _run_local(self, *, request: SandboxCommandRequest, workspace: Path) -> SandboxCommandResult:
        return self._execute(
            command=request.command,
            args=shlex.split(request.command),
            cwd=workspace,
            timeout_seconds=request.timeout_seconds,
            env=self._safe_env(),
        )

    def _execute(
        self,
        *,
        command: str,
        args: list[str],
        cwd: Path,
        timeout_seconds: int,
        env: dict[str, str] | None = None,
    ) -> SandboxCommandResult:
        started = time.monotonic()
        try:
            completed = subprocess.run(
                args,
                cwd=cwd,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                shell=False,
                check=False,
            )
        except FileNotFoundError as exc:
            return SandboxCommandResult(
                command=command,
                status=ValidationStatus.BLOCKED,
                duration_ms=int((time.monotonic() - started) * 1000),
                blocked_reason=f"Sandbox backend executable not found: {exc.filename}",
            )
        except subprocess.TimeoutExpired as exc:
            return SandboxCommandResult(
                command=command,
                status=ValidationStatus.FAILED,
                exit_code=None,
                duration_ms=int((time.monotonic() - started) * 1000),
                stdout=redact_text(_decode_output(exc.stdout)),
                stderr=redact_text(_decode_output(exc.stderr) or "Command timed out."),
            )

        return SandboxCommandResult(
            command=command,
            status=ValidationStatus.PASSED if completed.returncode == 0 else ValidationStatus.FAILED,
            exit_code=completed.returncode,
            duration_ms=int((time.monotonic() - started) * 1000),
            stdout=redact_text(completed.stdout)[-8000:],
            stderr=redact_text(completed.stderr)[-8000:],
        )

    def _safe_env(self) -> dict[str, str]:
        allowed = {"LANG", "LC_ALL"}
        safe_env = {key: value for key, value in os.environ.items() if key in allowed}
        runtime_bin = str(Path(sys.executable).parent)
        safe_env["PATH"] = f"{runtime_bin}:/usr/local/bin:/usr/bin:/bin:/usr/local/sbin:/usr/sbin:/sbin"
        safe_env["HOME"] = "/tmp"
        safe_env["TMPDIR"] = "/tmp"
        safe_env["PYTHONDONTWRITEBYTECODE"] = "1"
        return safe_env


def _decode_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore")
    return value
