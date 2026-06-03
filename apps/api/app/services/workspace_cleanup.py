from __future__ import annotations

import shutil
import time
from pathlib import Path
from uuid import UUID

WORKSPACE_ROOT = Path("/tmp/repopilot-agent-workspaces")


class WorkspaceCleanupService:
    def __init__(self, *, workspace_root: Path | None = None, max_age_seconds: int = 24 * 60 * 60) -> None:
        self.workspace_root = workspace_root or WORKSPACE_ROOT
        self.max_age_seconds = max_age_seconds

    def cleanup_stale_workspaces(self, *, active_run_ids: set[UUID | str] | None = None) -> dict[str, object]:
        active = {str(run_id) for run_id in (active_run_ids or set())}
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        removed: list[str] = []
        skipped: list[str] = []
        now = time.time()

        for child in self.workspace_root.iterdir():
            if not child.is_dir():
                continue
            if child.name in active:
                skipped.append(child.name)
                continue
            age_seconds = now - child.stat().st_mtime
            if age_seconds < self.max_age_seconds:
                skipped.append(child.name)
                continue
            shutil.rmtree(child, ignore_errors=True)
            removed.append(child.name)

        return {
            "workspace_root": str(self.workspace_root),
            "removed": removed,
            "skipped": skipped,
            "removed_count": len(removed),
        }
