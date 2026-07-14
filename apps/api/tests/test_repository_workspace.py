from __future__ import annotations

import stat
import asyncio
import zipfile
from pathlib import Path

import pytest

from app.core.config import Settings
from app.db.models import Installation, Repository
from app.services.repository_workspace import RepositoryAcquisitionError, RepositoryWorkspaceManager


def _manager(tmp_path: Path) -> RepositoryWorkspaceManager:
    return RepositoryWorkspaceManager(
        config=Settings(
            REPOPILOT_REPOSITORY_WORKSPACE_ROOT=str(tmp_path),
            REPOPILOT_REPOSITORY_ARCHIVE_MAX_BYTES=1_000_000,
            REPOPILOT_REPOSITORY_ARCHIVE_MAX_UNPACKED_BYTES=1_000_000,
            REPOPILOT_REPOSITORY_ARCHIVE_MAX_ENTRIES=100,
        )
    )


def test_repository_archive_extracts_single_root_and_preserves_executable(tmp_path: Path) -> None:
    archive_path = tmp_path / "repo.zip"
    executable = zipfile.ZipInfo("octo-demo/scripts/check.sh")
    executable.external_attr = (stat.S_IFREG | 0o755) << 16
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("octo-demo/README.md", "demo")
        archive.writestr(executable, "#!/bin/sh\nexit 0\n")

    stage = tmp_path / "stage"
    files, unpacked = _manager(tmp_path)._extract_archive(archive_path, stage)

    assert files == 2
    assert unpacked > 0
    assert (stage / "README.md").read_text(encoding="utf-8") == "demo"
    assert (stage / "scripts/check.sh").stat().st_mode & stat.S_IXUSR


def test_repository_archive_rejects_path_traversal(tmp_path: Path) -> None:
    archive_path = tmp_path / "repo.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../outside.txt", "secret")

    with pytest.raises(RepositoryAcquisitionError, match="unsafe path"):
        _manager(tmp_path)._extract_archive(archive_path, tmp_path / "stage")

    assert not (tmp_path.parent / "outside.txt").exists()


def test_repository_archive_rejects_symlinks(tmp_path: Path) -> None:
    archive_path = tmp_path / "repo.zip"
    symlink = zipfile.ZipInfo("octo-demo/link")
    symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(symlink, "/etc/passwd")

    with pytest.raises(RepositoryAcquisitionError, match="symbolic link"):
        _manager(tmp_path)._extract_archive(archive_path, tmp_path / "stage")


def test_repository_acquisition_rejects_oauth_discovery_without_network(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    repository = Repository(owner="octo", name="demo", default_branch="main")
    installation = Installation(github_installation_id="oauth:123", account_name="octo")

    with pytest.raises(RepositoryAcquisitionError, match="GitHub App installation"):
        asyncio.run(manager.acquire(repository=repository, installation=installation))
