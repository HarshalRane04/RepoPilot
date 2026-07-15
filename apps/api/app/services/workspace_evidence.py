from __future__ import annotations

import difflib
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import UUID

from app.services.repo_indexer import IGNORED_DIRS, SENSITIVE_FILE_NAMES, SENSITIVE_SUFFIXES, TEXT_EXTENSIONS
from app.services.security_envelope import stable_json_hash


WORKSPACE_ROOT = Path("/tmp/repopilot-agent-workspaces")
INTERNAL_DIR = ".repopilot"
MAX_READ_BYTES = 200_000
MAX_DIFF_BYTES = 40_000
IGNORED_WORKSPACE_DIRS = {
    ".git",
    ".mypy_cache",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "htmlcov",
    "node_modules",
    "venv",
    ".venv",
}
IGNORED_TOOL_DIRS = set(IGNORED_DIRS) | IGNORED_WORKSPACE_DIRS | {INTERNAL_DIR}
SENSITIVE_TOOL_DIR_NAMES = {"secrets", ".secrets"}


class WorkspaceBoundaryError(ValueError):
    pass


def isolated_workspace(run_id: UUID, workspace_path: str) -> Path:
    root = WORKSPACE_ROOT.resolve()
    expected = root / str(run_id)
    expected_resolved = expected.resolve()
    supplied = workspace_path.strip()
    if supplied not in {str(expected), str(expected_resolved)}:
        raise WorkspaceBoundaryError(f"Workspace write tools may only target isolated run workspace: {expected_resolved}")
    if expected.is_symlink() or not expected_resolved.is_dir():
        raise WorkspaceBoundaryError(f"Workspace path is not a non-symlink directory: {expected_resolved}")
    if expected_resolved.parent != root or expected_resolved.name != str(run_id):
        raise WorkspaceBoundaryError(f"Workspace escaped the configured run workspace root: {root}")
    return expected_resolved


def is_sensitive_workspace_path(relative_path: str) -> bool:
    path = PurePosixPath(relative_path.replace("\\", "/"))
    lowered_parts = {part.lower() for part in path.parts}
    if lowered_parts.intersection(SENSITIVE_TOOL_DIR_NAMES):
        return True
    name = path.name.lower()
    if name in SENSITIVE_FILE_NAMES:
        return True
    if any(name.startswith(prefix) for prefix in (".env.", "secret.", "secrets.")):
        return True
    return path.suffix.lower() in SENSITIVE_SUFFIXES


def iter_workspace_files(workspace: Path) -> list[Path]:
    files: list[Path] = []
    for path in workspace.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(workspace)
        if any(part in IGNORED_TOOL_DIRS for part in relative.parts):
            continue
        if is_sensitive_workspace_path(relative.as_posix()):
            continue
        files.append(path)
    return sorted(files)


def workspace_snapshot(workspace: Path) -> dict[str, dict[str, str]]:
    snapshot: dict[str, dict[str, str]] = {}
    for path in iter_workspace_files(workspace):
        relative = path.relative_to(workspace).as_posix()
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        entry = {"sha256": digest.hexdigest()}
        if (path.suffix.lower() in TEXT_EXTENSIONS or not path.suffix) and path.stat().st_size <= MAX_READ_BYTES:
            entry["content"] = path.read_text(encoding="utf-8", errors="ignore")
        snapshot[relative] = entry
    return snapshot


def baseline_path(workspace: Path) -> Path:
    return workspace / INTERNAL_DIR / "baseline.json"


def write_baseline(workspace: Path) -> None:
    metadata_dir = workspace / INTERNAL_DIR
    metadata_dir.mkdir(parents=True, exist_ok=True)
    baseline_path(workspace).write_text(json.dumps(workspace_snapshot(workspace), sort_keys=True), encoding="utf-8")


def load_baseline(workspace: Path) -> dict[str, dict[str, str]]:
    path = baseline_path(workspace)
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    return {str(key): value for key, value in payload.items() if isinstance(value, dict)}


def workspace_diff_payload(workspace: Path) -> dict[str, Any]:
    baseline = load_baseline(workspace)
    current = workspace_snapshot(workspace)
    all_paths = sorted(set(baseline) | set(current))
    changed_files: list[dict[str, Any]] = []
    patch_evidence: list[dict[str, str | None]] = []
    diff_parts: list[str] = []
    truncated = False

    for path in all_paths:
        before = baseline.get(path, {})
        after = current.get(path, {})
        if before.get("sha256") == after.get("sha256"):
            continue
        old_text = str(before.get("content", ""))
        new_text = str(after.get("content", ""))
        if path not in baseline:
            change_type = "create"
        elif path not in current:
            change_type = "delete"
        else:
            change_type = "modify"
        diff_lines = list(
            difflib.unified_diff(
                old_text.splitlines(keepends=True),
                new_text.splitlines(keepends=True),
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
            )
        )
        additions = sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++"))
        deletions = sum(1 for line in diff_lines if line.startswith("-") and not line.startswith("---"))
        changed_files.append({"path": path, "change_type": change_type, "additions": additions, "deletions": deletions})
        patch_evidence.append(
            {
                "path": path,
                "change_type": change_type,
                "before_sha256": str(before.get("sha256")) if before.get("sha256") else None,
                "after_sha256": str(after.get("sha256")) if after.get("sha256") else None,
            }
        )
        if sum(len(part) for part in diff_parts) < MAX_DIFF_BYTES:
            diff_parts.extend(diff_lines)
        else:
            truncated = True

    return {
        "workspace_path": str(workspace),
        "changed_files": changed_files,
        "patch_hash": stable_json_hash({"changes": patch_evidence}),
        "diff": "".join(diff_parts),
        "truncated": truncated,
    }
