from __future__ import annotations

import argparse
import hmac
import json
import os
import re
import shlex
import signal
import socket
import socketserver
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import UUID

from repopilot_contracts import PolicyDecisionType
from repopilot_policy_engine import PolicyEngine


MAX_REQUEST_BYTES = 64 * 1024
MAX_COMMAND_CHARS = 500
MAX_OUTPUT_BYTES = 8_000
MAX_TIMEOUT_SECONDS = 900
WORKSPACE_ROOT = Path(os.getenv("REPOPILOT_SANDBOX_WORKSPACE_ROOT", "/tmp/repopilot-agent-workspaces"))
SOCKET_PATH = Path(os.getenv("SANDBOX_RUNNER_SOCKET", "/run/repopilot-sandbox/runner.sock"))
TOKEN = os.getenv("SANDBOX_RUNNER_TOKEN", "")
EXECUTION_SLOTS = threading.BoundedSemaphore(max(1, min(int(os.getenv("SANDBOX_RUNNER_MAX_CONCURRENCY", "1")), 4)))
SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*(?:bearer\s+)?)[^\s,;]+"),
    re.compile(r"(?i)((?:api[_-]?key|token|secret|password)\s*[:=]\s*)[^\s,;]+"),
    re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{16,})\b"),
)


class ThreadingUnixHTTPServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


class SandboxRequestHandler(BaseHTTPRequestHandler):
    server_version = "RepoPilotSandbox/1"

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/health":
            self._json_response(404, {"status": "not_found"})
            return
        if not self._authorized():
            self._json_response(401, {"status": "unauthorized"})
            return
        self._json_response(200, {"status": "ok", "version": 1, "backend": "isolated-process"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/execute":
            self._json_response(404, {"status": "not_found"})
            return
        if not self._authorized():
            self._json_response(401, {"status": "unauthorized"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._json_response(400, {"status": "invalid_request", "detail": "Invalid Content-Length."})
            return
        if length <= 0 or length > MAX_REQUEST_BYTES:
            self._json_response(413, {"status": "invalid_request", "detail": "Request body exceeds the bounded limit."})
            return
        try:
            payload = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._json_response(400, {"status": "invalid_request", "detail": "Body must be valid JSON."})
            return
        if not isinstance(payload, dict):
            self._json_response(400, {"status": "invalid_request", "detail": "Body must be a JSON object."})
            return
        if not EXECUTION_SLOTS.acquire(blocking=False):
            self._json_response(429, {"status": "busy", "detail": "Sandbox execution capacity is busy."})
            return
        try:
            status_code, result = execute_request(payload)
        finally:
            EXECUTION_SLOTS.release()
        self._json_response(status_code, result)

    def _authorized(self) -> bool:
        supplied = self.headers.get("Authorization", "")
        expected = f"Bearer {TOKEN}"
        return bool(TOKEN) and hmac.compare_digest(supplied, expected)

    def _json_response(self, status_code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        message = format % args
        print(json.dumps({"component": "sandbox-runner", "message": redact(message)}), flush=True)


def execute_request(payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    started = time.monotonic()
    command = payload.get("command")
    workspace_value = payload.get("workspace_path")
    working_directory_value = payload.get("working_directory", ".")
    timeout_value = payload.get("timeout_seconds", 120)
    try:
        run_id = UUID(str(payload.get("run_id") or ""))
    except ValueError:
        return 400, blocked_result(str(command or ""), started, "run_id must be a valid UUID.")
    if not isinstance(command, str) or not command.strip() or len(command) > MAX_COMMAND_CHARS:
        return 400, blocked_result(str(command or ""), started, "command must be a non-empty bounded string.")
    if not isinstance(workspace_value, str):
        return 400, blocked_result(command, started, "workspace_path must be a string.")
    if not isinstance(working_directory_value, str):
        return 400, blocked_result(command, started, "working_directory must be a string.")
    if isinstance(timeout_value, bool):
        return 400, blocked_result(command, started, "timeout_seconds must be an integer.")
    try:
        timeout_seconds = int(timeout_value)
    except (TypeError, ValueError):
        return 400, blocked_result(command, started, "timeout_seconds must be an integer.")
    if not 1 <= timeout_seconds <= MAX_TIMEOUT_SECONDS:
        return 400, blocked_result(command, started, f"timeout_seconds must be between 1 and {MAX_TIMEOUT_SECONDS}.")

    policy = PolicyEngine().evaluate_command(command)
    if policy.decision != PolicyDecisionType.ALLOW:
        return 403, blocked_result(command, started, policy.reason)
    try:
        workspace = exact_run_workspace(run_id=run_id, workspace_value=workspace_value)
        working_directory = exact_working_directory(workspace=workspace, value=working_directory_value)
        args = shlex.split(command)
    except (ValueError, OSError) as exc:
        return 403, blocked_result(command, started, str(exc))
    if not args:
        return 400, blocked_result(command, started, "Command did not contain an executable.")
    return 200, run_process(
        command=command,
        args=args,
        working_directory=working_directory,
        timeout_seconds=timeout_seconds,
        started=started,
    )


def exact_run_workspace(*, run_id: UUID, workspace_value: str) -> Path:
    root = WORKSPACE_ROOT.resolve(strict=True)
    expected = root / str(run_id)
    supplied = workspace_value.strip()
    if supplied != str(expected):
        raise ValueError(f"Sandbox workspace must exactly match {expected}.")
    if expected.is_symlink():
        raise ValueError("Sandbox workspace must be an existing non-symlink directory.")
    try:
        resolved = expected.resolve(strict=True)
    except OSError as exc:
        raise ValueError("Sandbox workspace must be an existing non-symlink directory.") from exc
    if not resolved.is_dir():
        raise ValueError("Sandbox workspace must be an existing non-symlink directory.")
    if resolved.parent != root or resolved.name != str(run_id):
        raise ValueError("Sandbox workspace escaped the configured workspace root.")
    return resolved


def exact_working_directory(*, workspace: Path, value: str) -> Path:
    raw = value.strip().replace("\\", "/")
    relative = PurePosixPath(raw)
    if not raw or relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Sandbox working directory must be relative to the run workspace.")
    parts = tuple(part for part in relative.parts if part != ".")
    # The path is built only from normalized relative segments and is checked
    # for symlinks and containment again after strict resolution.
    # codeql[py/path-injection]
    # lgtm[py/path-injection]
    candidate = workspace.joinpath(*parts) if parts else workspace
    # codeql[py/path-injection]
    # lgtm[py/path-injection]
    if candidate != workspace and candidate.is_symlink():
        raise ValueError("Sandbox working directory must be an existing non-symlink directory.")
    try:
        # codeql[py/path-injection]
        # lgtm[py/path-injection]
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ValueError("Sandbox working directory must be an existing non-symlink directory.") from exc
    if resolved != workspace and not resolved.is_relative_to(workspace):
        raise ValueError("Sandbox working directory escaped the run workspace.")
    # codeql[py/path-injection]
    # lgtm[py/path-injection]
    if not resolved.is_dir():
        raise ValueError("Sandbox working directory must be an existing non-symlink directory.")
    return resolved


def run_process(
    *,
    command: str,
    args: list[str],
    working_directory: Path,
    timeout_seconds: int,
    started: float,
) -> dict[str, Any]:
    with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
        try:
            process = subprocess.Popen(  # noqa: S603 - args are policy-allowlisted and shell is never used.
                args,
                cwd=working_directory,
                env=safe_environment(),
                stdin=subprocess.DEVNULL,
                stdout=stdout_file,
                stderr=stderr_file,
                shell=False,
                start_new_session=True,
            )
        except FileNotFoundError as exc:
            return blocked_result(command, started, f"Sandbox executable was not found: {exc.filename}")
        try:
            exit_code = process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            with suppress_process_error():
                os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            return {
                "command": command,
                "status": "failed",
                "exit_code": None,
                "duration_ms": elapsed_ms(started),
                "stdout": read_tail(stdout_file),
                "stderr": read_tail(stderr_file) or "Command timed out.",
                "blocked_reason": None,
            }
        return {
            "command": command,
            "status": "passed" if exit_code == 0 else "failed",
            "exit_code": exit_code,
            "duration_ms": elapsed_ms(started),
            "stdout": read_tail(stdout_file),
            "stderr": read_tail(stderr_file),
            "blocked_reason": None,
        }


class suppress_process_error:
    def __enter__(self) -> None:
        return None

    def __exit__(self, _type: object, _value: object, _traceback: object) -> bool:
        return _type is not None and isinstance(_value, (OSError, ProcessLookupError))


def blocked_result(command: str, started: float, reason: str) -> dict[str, Any]:
    return {
        "command": command,
        "status": "blocked",
        "exit_code": None,
        "duration_ms": elapsed_ms(started),
        "stdout": "",
        "stderr": "",
        "blocked_reason": redact(reason),
    }


def read_tail(handle: Any) -> str:
    handle.flush()
    size = handle.tell()
    handle.seek(max(0, size - MAX_OUTPUT_BYTES))
    return redact(handle.read(MAX_OUTPUT_BYTES).decode("utf-8", errors="ignore"))


def safe_environment() -> dict[str, str]:
    return {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": "/tmp",
        "TMPDIR": "/tmp",
        "LANG": os.getenv("LANG", "C.UTF-8"),
        "LC_ALL": os.getenv("LC_ALL", "C.UTF-8"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "CI": "true",
    }


def redact(value: str) -> str:
    redacted = value
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(lambda match: f"{match.group(1)}[REDACTED]" if match.lastindex else "[REDACTED_SECRET]", redacted)
    return redacted[-MAX_OUTPUT_BYTES:]


def elapsed_ms(started: float) -> int:
    return max(0, int((time.monotonic() - started) * 1000))


def healthcheck() -> int:
    request = (
        "GET /health HTTP/1.1\r\n"
        "Host: sandbox-runner\r\n"
        f"Authorization: Bearer {TOKEN}\r\n"
        "Connection: close\r\n\r\n"
    ).encode("utf-8")
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(2)
            client.connect(str(SOCKET_PATH))
            client.sendall(request)
            response = client.recv(256)
        return 0 if b" 200 " in response.splitlines()[0] else 1
    except OSError:
        return 1


def serve() -> None:
    if len(TOKEN) < 32:
        raise SystemExit("SANDBOX_RUNNER_TOKEN must contain at least 32 characters.")
    SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)
    if SOCKET_PATH.exists():
        if not SOCKET_PATH.is_socket():
            raise SystemExit(f"Refusing to replace non-socket path: {SOCKET_PATH}")
        SOCKET_PATH.unlink()
    server = ThreadingUnixHTTPServer(str(SOCKET_PATH), SandboxRequestHandler)
    SOCKET_PATH.chmod(0o660)
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        server.server_close()
        if SOCKET_PATH.is_socket():
            SOCKET_PATH.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description="RepoPilot isolated sandbox runner")
    parser.add_argument("--healthcheck", action="store_true")
    args = parser.parse_args()
    if args.healthcheck:
        return healthcheck()
    serve()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
