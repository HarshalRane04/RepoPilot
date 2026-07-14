from __future__ import annotations

import asyncio
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath
from uuid import UUID

import httpx
from repopilot_contracts import PolicyDecisionType, SandboxCommandRequest, SandboxCommandResult, ValidationStatus

from app.core.config import Settings, settings
from app.services.path_safety import UnsafePathError, exact_existing_directory
from app.services.policy import PolicyEngine
from app.services.security_envelope import redact_text

WORKSPACE_ROOT = Path("/tmp/repopilot-agent-workspaces")


class SandboxRunner:
    def __init__(
        self,
        policy_engine: PolicyEngine | None = None,
        *,
        backend: str | None = None,
        config: Settings | None = None,
    ) -> None:
        self.config = config or settings
        self.policy_engine = policy_engine or PolicyEngine()
        self.backend = backend or self.config.sandbox_backend

    def run_command(self, request: SandboxCommandRequest, *, run_id: UUID) -> SandboxCommandResult:
        policy = self.policy_engine.evaluate_command(request.command)
        if policy.decision != PolicyDecisionType.ALLOW:
            return SandboxCommandResult(
                command=request.command,
                status=ValidationStatus.BLOCKED,
                duration_ms=0,
                blocked_reason=policy.reason,
            )

        expected_workspace = WORKSPACE_ROOT / str(run_id)
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
        try:
            working_directory = self._working_directory(workspace, request.working_directory)
        except UnsafePathError as exc:
            return SandboxCommandResult(
                command=request.command,
                status=ValidationStatus.BLOCKED,
                duration_ms=0,
                blocked_reason=str(exc),
            )

        if self.backend == "remote":
            return self._run_remote(
                request=request,
                workspace=workspace,
                working_directory=working_directory,
                run_id=run_id,
            )
        if self.backend == "local":
            if self.config.environment != "local":
                return SandboxCommandResult(
                    command=request.command,
                    status=ValidationStatus.BLOCKED,
                    duration_ms=0,
                    blocked_reason="The local sandbox backend is only allowed when REPOPILOT_ENV=local.",
                )
            return self._run_local(request=request, working_directory=working_directory)

        return SandboxCommandResult(
            command=request.command,
            status=ValidationStatus.BLOCKED,
            duration_ms=0,
            blocked_reason=f"Unknown sandbox backend: {self.backend}",
        )

    async def run_command_async(self, request: SandboxCommandRequest, *, run_id: UUID) -> SandboxCommandResult:
        return await asyncio.to_thread(self.run_command, request, run_id=run_id)

    def healthcheck(self) -> tuple[bool, str]:
        token = self.config.sandbox_runner_token or ""
        if self.backend != "remote":
            return (self.config.environment == "local" and self.backend == "local", f"backend={self.backend}")
        if len(token) < 32:
            return False, "Sandbox runner token is missing or too short."
        try:
            with self._remote_client(timeout_seconds=3) as client:
                response = client.get("/health", headers={"Authorization": f"Bearer {token}"})
            if response.status_code != 200:
                return False, f"Sandbox runner health returned HTTP {response.status_code}."
            payload = response.json()
            return payload.get("status") == "ok", f"runner={payload.get('status', 'unknown')}"
        except (httpx.HTTPError, OSError, ValueError) as exc:
            return False, f"Sandbox runner is unreachable: {exc.__class__.__name__}."

    def _run_remote(
        self,
        *,
        request: SandboxCommandRequest,
        workspace: Path,
        working_directory: Path,
        run_id: UUID,
    ) -> SandboxCommandResult:
        started = time.monotonic()
        token = self.config.sandbox_runner_token or ""
        if len(token) < 32:
            return self._blocked(request.command, started, "Sandbox runner token is missing or too short.")
        try:
            with self._remote_client(timeout_seconds=request.timeout_seconds + 5) as client:
                response = client.post(
                    "/v1/execute",
                    headers={"Authorization": f"Bearer {token}"},
                    json={
                        "run_id": str(run_id),
                        "workspace_path": str(workspace),
                        "working_directory": working_directory.relative_to(workspace).as_posix() or ".",
                        "command": request.command,
                        "timeout_seconds": request.timeout_seconds,
                    },
                )
            payload = response.json()
            if isinstance(payload, dict) and {"command", "status", "duration_ms"} <= payload.keys():
                return SandboxCommandResult.model_validate(payload)
            detail = payload.get("detail") if isinstance(payload, dict) else None
            return self._blocked(
                request.command,
                started,
                str(detail or f"Sandbox runner returned HTTP {response.status_code}."),
            )
        except (httpx.HTTPError, OSError, ValueError) as exc:
            return self._blocked(
                request.command,
                started,
                f"Sandbox runner request failed: {exc.__class__.__name__}.",
            )

    def _remote_client(self, *, timeout_seconds: int) -> httpx.Client:
        transport = httpx.HTTPTransport(uds=self.config.sandbox_runner_socket, retries=0)
        return httpx.Client(
            transport=transport,
            base_url="http://sandbox-runner",
            timeout=httpx.Timeout(timeout_seconds, connect=min(timeout_seconds, 3)),
        )

    def _blocked(self, command: str, started: float, reason: str) -> SandboxCommandResult:
        return SandboxCommandResult(
            command=command,
            status=ValidationStatus.BLOCKED,
            duration_ms=max(0, int((time.monotonic() - started) * 1000)),
            blocked_reason=redact_text(reason),
        )

    def _run_local(self, *, request: SandboxCommandRequest, working_directory: Path) -> SandboxCommandResult:
        return self._execute(
            command=request.command,
            args=shlex.split(request.command),
            cwd=working_directory,
            timeout_seconds=request.timeout_seconds,
            env=self._safe_env(),
        )

    def _working_directory(self, workspace: Path, value: str) -> Path:
        relative = PurePosixPath(value.replace("\\", "/"))
        if relative.is_absolute() or ".." in relative.parts:
            raise UnsafePathError("Sandbox working directory must be relative to the run workspace.")
        candidate = (workspace / relative.as_posix()).resolve(strict=True)
        if candidate != workspace and not candidate.is_relative_to(workspace):
            raise UnsafePathError("Sandbox working directory escaped the run workspace.")
        if not candidate.is_dir() or candidate.is_symlink():
            raise UnsafePathError("Sandbox working directory must be an existing non-symlink directory.")
        return candidate

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
