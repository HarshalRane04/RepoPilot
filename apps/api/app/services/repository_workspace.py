from __future__ import annotations

import asyncio
import fcntl
import shutil
import stat
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from uuid import UUID, uuid4

import httpx

from app.core.config import Settings, settings
from app.db.models import Installation, Repository
from app.services.github_app import GitHubAppTokenProvider, GitHubIntegrationError
from app.services.runtime_secrets import effective_settings
from app.services.url_safety import github_api_base_url, path_fragment, path_segment


class RepositoryAcquisitionError(RuntimeError):
    pass


@dataclass(frozen=True)
class AcquiredRepository:
    repository_id: UUID
    source_path: str
    ref: str
    commit_sha: str
    files_extracted: int
    unpacked_bytes: int


class RepositoryWorkspaceManager:
    """Acquire a GitHub repository into the canonical server-managed workspace."""

    def __init__(
        self,
        *,
        config: Settings | None = None,
        token_provider: GitHubAppTokenProvider | None = None,
    ) -> None:
        self.config = config or effective_settings(settings)
        self.token_provider = token_provider or GitHubAppTokenProvider()
        self.root = Path(self.config.repository_workspace_root).expanduser()

    async def acquire(
        self,
        *,
        repository: Repository,
        installation: Installation,
        ref: str | None = None,
    ) -> AcquiredRepository:
        requested_ref = (ref or repository.default_branch).strip()
        if not requested_ref or len(requested_ref) > 255 or any(char in requested_ref for char in ("\x00", "\r", "\n")):
            raise RepositoryAcquisitionError("Repository ref is invalid.")
        if installation.github_installation_id.startswith("oauth:"):
            raise RepositoryAcquisitionError(
                "Repository acquisition requires a GitHub App installation; OAuth discovery does not provide a reusable source token."
            )
        if not self.token_provider.is_configured():
            raise RepositoryAcquisitionError("GitHub App credentials are required to acquire repository source.")

        self.root.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            prefix=f".{repository.id}.archive-",
            suffix=".zip",
            dir=self.root,
            delete=False,
        ) as handle:
            archive_path = Path(handle.name)
        stage = self.root / f".{repository.id}.stage-{uuid4()}"
        try:
            token = await self.token_provider.create_installation_access_token(installation.github_installation_id)
            commit_sha = await self._resolve_ref_sha(
                token=token,
                owner=repository.owner,
                name=repository.name,
                ref=requested_ref,
            )
            await self._download_archive(
                token=token,
                owner=repository.owner,
                name=repository.name,
                ref=commit_sha,
                destination=archive_path,
            )
            files_extracted, unpacked_bytes = await asyncio.to_thread(self._extract_archive, archive_path, stage)
            await asyncio.to_thread(self._install_stage, repository.id, stage)
        except RepositoryAcquisitionError:
            raise
        except (httpx.HTTPError, OSError, zipfile.BadZipFile, GitHubIntegrationError) as exc:
            raise RepositoryAcquisitionError(f"Repository acquisition failed: {exc}") from exc
        finally:
            archive_path.unlink(missing_ok=True)
            if stage.exists():
                shutil.rmtree(stage, ignore_errors=True)

        target = self.root / str(repository.id)
        return AcquiredRepository(
            repository_id=repository.id,
            source_path=str(target.resolve()),
            ref=requested_ref,
            commit_sha=commit_sha,
            files_extracted=files_extracted,
            unpacked_bytes=unpacked_bytes,
        )

    async def _resolve_ref_sha(self, *, token: str, owner: str, name: str, ref: str) -> str:
        url = (
            f"{github_api_base_url(self.config.github_api_base_url)}/repos/"
            f"{path_segment(owner)}/{path_segment(name)}/commits/{path_fragment(ref)}"
        )
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            response = await client.get(url, headers=self._headers(token))
        if response.status_code >= 400:
            raise RepositoryAcquisitionError(
                f"GitHub could not resolve repository ref ({response.status_code}): {response.text[:240]}"
            )
        payload = response.json()
        sha = str(payload.get("sha") or "") if isinstance(payload, dict) else ""
        if len(sha) != 40 or any(char not in "0123456789abcdefABCDEF" for char in sha):
            raise RepositoryAcquisitionError("GitHub commit response did not contain a valid SHA.")
        return sha.lower()

    async def _download_archive(
        self,
        *,
        token: str,
        owner: str,
        name: str,
        ref: str,
        destination: Path,
    ) -> None:
        url = (
            f"{github_api_base_url(self.config.github_api_base_url)}/repos/"
            f"{path_segment(owner)}/{path_segment(name)}/zipball/{path_fragment(ref)}"
        )
        max_bytes = self.config.repository_archive_max_bytes
        received = 0
        async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=20), follow_redirects=True) as client:
            async with client.stream("GET", url, headers=self._headers(token)) as response:
                if response.status_code >= 400:
                    body = (await response.aread())[:240].decode("utf-8", errors="replace")
                    raise RepositoryAcquisitionError(
                        f"GitHub repository archive request failed ({response.status_code}): {body}"
                    )
                declared = response.headers.get("content-length")
                if declared:
                    try:
                        declared_size = int(declared)
                    except ValueError as exc:
                        raise RepositoryAcquisitionError("GitHub returned an invalid archive content length.") from exc
                    if declared_size > max_bytes:
                        raise RepositoryAcquisitionError("Repository archive exceeds the configured download limit.")
                with destination.open("wb") as handle:
                    async for chunk in response.aiter_bytes(chunk_size=1024 * 1024):
                        received += len(chunk)
                        if received > max_bytes:
                            raise RepositoryAcquisitionError("Repository archive exceeds the configured download limit.")
                        handle.write(chunk)
        if received == 0:
            raise RepositoryAcquisitionError("GitHub returned an empty repository archive.")

    def _extract_archive(self, archive_path: Path, stage: Path) -> tuple[int, int]:
        stage.mkdir(mode=0o700, parents=False, exist_ok=False)
        stage_root = stage.resolve()
        with zipfile.ZipFile(archive_path) as archive:
            members = archive.infolist()
            if len(members) > self.config.repository_archive_max_entries:
                raise RepositoryAcquisitionError("Repository archive contains too many entries.")
            unpacked = sum(info.file_size for info in members if not info.is_dir())
            if unpacked > self.config.repository_archive_max_unpacked_bytes:
                raise RepositoryAcquisitionError("Repository archive exceeds the configured unpacked-size limit.")
            prefix = self._archive_prefix(members)
            files = 0
            for info in members:
                relative = self._safe_member_path(info.filename, prefix=prefix)
                if relative is None:
                    continue
                mode = (info.external_attr >> 16) & 0xFFFF
                if stat.S_ISLNK(mode):
                    raise RepositoryAcquisitionError("Repository archive contains a symbolic link.")
                target = stage.joinpath(*relative.parts)
                resolved = target.resolve(strict=False)
                if stage_root not in resolved.parents:
                    raise RepositoryAcquisitionError("Repository archive attempted path traversal.")
                if info.is_dir():
                    target.mkdir(mode=0o755, parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("wb") as destination:
                    shutil.copyfileobj(source, destination, length=1024 * 1024)
                target.chmod(0o755 if mode & 0o111 else 0o644)
                files += 1
        if files == 0:
            raise RepositoryAcquisitionError("Repository archive contained no files.")
        return files, unpacked

    def _install_stage(self, repository_id: UUID, stage: Path) -> None:
        target = self.root / str(repository_id)
        backup = self.root / f".{repository_id}.backup-{uuid4()}"
        lock_path = self.root / f".{repository_id}.lock"
        with lock_path.open("a+b") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                if target.exists():
                    target.rename(backup)
                try:
                    stage.rename(target)
                except Exception:
                    if backup.exists() and not target.exists():
                        backup.rename(target)
                    raise
                if backup.exists():
                    shutil.rmtree(backup)
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def _archive_prefix(self, members: list[zipfile.ZipInfo]) -> str | None:
        roots = {
            PurePosixPath(info.filename).parts[0]
            for info in members
            if info.filename and PurePosixPath(info.filename).parts
        }
        return next(iter(roots)) if len(roots) == 1 else None

    def _safe_member_path(self, name: str, *, prefix: str | None) -> PurePosixPath | None:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or "\\" in name or "\x00" in name:
            raise RepositoryAcquisitionError("Repository archive contains an unsafe path.")
        parts = list(path.parts)
        if prefix and parts and parts[0] == prefix:
            parts = parts[1:]
        if not parts:
            return None
        return PurePosixPath(*parts)

    def _headers(self, token: str) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "RepoPilot-Acquisition/1.0",
        }
