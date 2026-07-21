from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from repopilot_contracts import RepositoryIndexRequest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CodeChunk, Installation, Issue, Repository, RepositoryIndex
from app.db.session import get_db
from app.services.auth import CurrentUser, get_current_user
from app.services.authorization import require_repository_access, require_role
from app.services.repo_indexer import RepositoryIndexer
from app.services.repository_workspace import RepositoryAcquisitionError, RepositoryWorkspaceManager
from app.services.audit import record_audit

router = APIRouter()


class RepositoryAcquireRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: str | None = Field(default=None, max_length=255)
    max_files: int = Field(default=500, ge=1, le=5000)
    max_file_bytes: int = Field(default=120_000, ge=1_000, le=2_000_000)


@router.get("")
async def list_repositories(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, object]]:
    require_role(current_user, "viewer")
    result = await db.execute(
        select(Repository, Installation.github_installation_id)
        .join(Installation, Installation.id == Repository.installation_id)
        .order_by(Repository.created_at.desc())
    )
    repository_rows = result.all()
    return await _repository_payloads(db, repository_rows)


async def _repository_payloads(
    db: AsyncSession,
    repository_rows: list[tuple[Repository, str]],
) -> list[dict[str, object]]:
    repositories = [repository for repository, _github_installation_id in repository_rows]
    if not repositories:
        return []
    github_installation_ids = {repository.id: installation_id for repository, installation_id in repository_rows}
    repository_ids = [repository.id for repository in repositories]
    issue_rows = await db.execute(
        select(Issue.repository_id, Issue.number).where(Issue.repository_id.in_(repository_ids))
    )
    issue_numbers_by_repository: dict[str, set[int]] = {}
    for repository_id, number in issue_rows.all():
        issue_numbers_by_repository.setdefault(str(repository_id), set()).add(int(number))
    chunk_rows = await db.execute(select(CodeChunk).where(CodeChunk.repository_id.in_(repository_ids)))
    chunks_by_repository: dict[UUID, list[CodeChunk]] = {}
    for chunk in chunk_rows.scalars().all():
        chunks_by_repository.setdefault(chunk.repository_id, []).append(chunk)
    index_rows = await db.execute(
        select(RepositoryIndex)
        .where(RepositoryIndex.repository_id.in_(repository_ids))
        .order_by(RepositoryIndex.repository_id, RepositoryIndex.created_at.desc())
    )
    latest_indexes: dict[UUID, RepositoryIndex] = {}
    for index in index_rows.scalars().all():
        latest_indexes.setdefault(index.repository_id, index)
    responses: list[dict[str, object]] = []
    for repo in repositories:
        github_installation_id = github_installation_ids.get(repo.id, "")
        responses.append(
            _repository_response(
                repo=repo,
                github_installation_id=github_installation_id,
                issue_count=len(issue_numbers_by_repository.get(str(repo.id), set())),
                chunks=chunks_by_repository.get(repo.id, []),
                latest_index=latest_indexes.get(repo.id),
            )
        )
    return _canonicalize_repository_responses(
        responses,
        issue_numbers_by_repository=issue_numbers_by_repository,
    )


@router.get("/{repo_id}")
async def get_repository(
    repo_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    repository = await require_repository_access(db, repository_id=repo_id, current_user=current_user, action="read")
    aliases = await db.execute(
        select(Repository, Installation.github_installation_id)
        .join(Installation, Installation.id == Repository.installation_id)
        .where(
            func.lower(Repository.owner) == repository.owner.casefold(),
            func.lower(Repository.name) == repository.name.casefold(),
        )
        .order_by(Repository.created_at.desc())
    )
    responses = await _repository_payloads(db, list(aliases.all()))
    if not responses:
        raise HTTPException(status_code=404, detail="Repository installation record is missing.")
    return responses[0]


def _repository_response(
    *,
    repo: Repository,
    github_installation_id: str,
    issue_count: int,
    chunks: list[CodeChunk],
    latest_index: RepositoryIndex | None,
) -> dict[str, object]:
    acquirable = bool(github_installation_id) and not github_installation_id.startswith("oauth:")
    file_paths = sorted({chunk.file_path for chunk in chunks})
    test_file_count = sum(1 for path in file_paths if _is_test_file(path))
    embedding_model = latest_index.embedding_model if latest_index else chunks[0].embedding_model if chunks else None
    embedding_provider = latest_index.embedding_provider if latest_index else chunks[0].embedding_provider if chunks else None
    embedding_dimensions = latest_index.embedding_dimensions if latest_index else chunks[0].embedding_dimensions if chunks else None
    indexer = RepositoryIndexer()
    index_stale = indexer.index_metadata_is_stale(latest_index) if latest_index else indexer.index_is_stale_for_embeddings(chunks)
    return {
        "id": str(repo.id),
        "installation_id": str(repo.installation_id),
        "source_mode": "github_app" if acquirable else "oauth_discovery",
        "acquirable": acquirable,
        "owner": repo.owner,
        "name": repo.name,
        "default_branch": repo.default_branch,
        "last_indexed_sha": repo.last_indexed_sha,
        "issue_count": issue_count,
        "index_id": str(latest_index.id) if latest_index else None,
        "index_status": latest_index.status if latest_index else None,
        "indexed_at": latest_index.created_at if latest_index else None,
        "content_fingerprint": latest_index.content_fingerprint if latest_index else None,
        "chunker_version": latest_index.chunker_version if latest_index else None,
        "indexed_file_count": latest_index.files_indexed if latest_index else len(file_paths),
        "code_chunk_count": latest_index.chunks_indexed if latest_index else len(chunks),
        "test_file_count": test_file_count,
        "language": _infer_language(file_paths),
        "framework": _infer_framework(chunks),
        "embedding_provider": embedding_provider,
        "embedding_model": embedding_model,
        "embedding_dimensions": embedding_dimensions,
        "index_stale": index_stale,
    }


def _canonicalize_repository_responses(
    responses: list[dict[str, object]],
    *,
    issue_numbers_by_repository: dict[str, set[int]] | None = None,
) -> list[dict[str, object]]:
    groups: dict[str, list[dict[str, object]]] = {}
    for response in responses:
        canonical_id = _canonical_repository_id(str(response["owner"]), str(response["name"]))
        groups.setdefault(canonical_id, []).append(response)

    canonical: list[dict[str, object]] = []
    index_fields = (
        "last_indexed_sha",
        "index_id",
        "index_status",
        "indexed_at",
        "content_fingerprint",
        "chunker_version",
        "indexed_file_count",
        "code_chunk_count",
        "test_file_count",
        "language",
        "framework",
        "embedding_provider",
        "embedding_model",
        "embedding_dimensions",
        "index_stale",
    )
    for canonical_id, aliases in groups.items():
        preferred = max(
            aliases,
            key=lambda item: (
                bool(item.get("acquirable")),
                item.get("indexed_at") is not None,
                _timestamp_value(item.get("indexed_at")),
            ),
        )
        index_evidence = max(
            aliases,
            key=lambda item: (item.get("indexed_at") is not None, _timestamp_value(item.get("indexed_at"))),
        )
        merged = dict(preferred)
        if index_evidence.get("indexed_at") is not None:
            for field in index_fields:
                merged[field] = index_evidence.get(field)
        alias_ids = [str(preferred["id"]), *sorted(str(item["id"]) for item in aliases if item is not preferred)]
        merged.update(
            {
                "canonical_id": canonical_id,
                "alias_ids": alias_ids,
                "installation_ids": sorted({str(item["installation_id"]) for item in aliases}),
                "source_modes": sorted({str(item["source_mode"]) for item in aliases}),
            }
        )
        if issue_numbers_by_repository is not None:
            issue_numbers: set[int] = set()
            for alias_id in alias_ids:
                issue_numbers.update(issue_numbers_by_repository.get(alias_id, set()))
            merged["issue_count"] = len(issue_numbers)
        else:
            merged["issue_count"] = sum(int(item.get("issue_count", 0)) for item in aliases)
        canonical.append(merged)
    return canonical


def _canonical_repository_id(owner: str, name: str) -> str:
    return f"{owner.strip().casefold()}/{name.strip().casefold()}"


def _timestamp_value(value: object) -> float:
    if isinstance(value, datetime):
        return value.timestamp()
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return 0.0
    return 0.0


@router.post("/{repo_id}/index", status_code=202)
async def trigger_repository_index(
    repo_id: UUID,
    request: RepositoryIndexRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    try:
        repository = await require_repository_access(db, repository_id=repo_id, current_user=current_user, action="write")
        result = await RepositoryIndexer().index_repository(db, repository_id=repository.id, request=request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result.model_dump(mode="json")


@router.post("/{repo_id}/acquire", status_code=202)
async def acquire_and_index_repository(
    repo_id: UUID,
    request: RepositoryAcquireRequest | None = None,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    repository = await require_repository_access(db, repository_id=repo_id, current_user=current_user, action="write")
    installation = await db.get(Installation, repository.installation_id)
    if installation is None:
        raise HTTPException(status_code=409, detail="Repository installation record is missing.")
    if installation.github_installation_id.startswith("oauth:"):
        raise HTTPException(
            status_code=409,
            detail="This repository was discovered through OAuth only. Install the GitHub App on it before acquisition.",
        )
    request = request or RepositoryAcquireRequest()
    try:
        acquired = await RepositoryWorkspaceManager().acquire(
            repository=repository,
            installation=installation,
            ref=request.ref,
        )
        indexed = await RepositoryIndexer().index_repository(
            db,
            repository_id=repository.id,
            request=RepositoryIndexRequest(
                source_path=acquired.source_path,
                commit_sha=acquired.commit_sha,
                max_files=request.max_files,
                max_file_bytes=request.max_file_bytes,
            ),
        )
    except RepositoryAcquisitionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    await record_audit(
        db,
        actor_type="user",
        actor_id=current_user.username,
        action="repository.acquired",
        entity_type="repository",
        entity_id=str(repository.id),
        metadata={
            "ref": acquired.ref,
            "commit_sha": acquired.commit_sha,
            "files_extracted": acquired.files_extracted,
            "unpacked_bytes": acquired.unpacked_bytes,
            "index_id": indexed.index_id,
        },
    )
    await db.commit()
    return {
        "status": "ready",
        "acquisition": {
            "source_path": acquired.source_path,
            "ref": acquired.ref,
            "commit_sha": acquired.commit_sha,
            "files_extracted": acquired.files_extracted,
            "unpacked_bytes": acquired.unpacked_bytes,
        },
        "index": indexed.model_dump(mode="json"),
    }


@router.get("/{repo_id}/context")
async def retrieve_repository_context(
    repo_id: UUID,
    query: str = Query(min_length=1),
    limit: int = Query(default=6, ge=1, le=20),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    repository = await require_repository_access(db, repository_id=repo_id, current_user=current_user, action="read")
    context = await RepositoryIndexer().retrieve_context(db, repository_id=repository.id, query=query, limit=limit)
    return context.model_dump(mode="json")


@router.get("/{repo_id}/issues")
async def list_repository_issues(
    repo_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    repository = await require_repository_access(db, repository_id=repo_id, current_user=current_user, action="read")
    result = await db.execute(
        select(Issue).where(Issue.repository_id == repository.id).order_by(Issue.created_at.desc())
    )
    issues = result.scalars().all()
    return {
        "repo_id": str(repository.id),
        "issues": [
            {
                "id": str(issue.id),
                "number": issue.number,
                "title": issue.title,
                "issue_type": issue.issue_type,
                "complexity": issue.complexity,
                "risk_score": issue.risk_score,
                "status": issue.status,
                "created_at": issue.created_at,
            }
            for issue in issues
        ],
    }


def _is_test_file(path: str) -> bool:
    lowered = path.lower()
    return (
        "/test" in lowered
        or lowered.startswith("test")
        or ".test." in lowered
        or ".spec." in lowered
        or lowered.endswith("_test.py")
    )


def _infer_language(file_paths: list[str]) -> str | None:
    counts: dict[str, int] = {}
    extension_map = {
        ".py": "Python",
        ".ts": "TypeScript",
        ".tsx": "TypeScript",
        ".js": "JavaScript",
        ".jsx": "JavaScript",
        ".go": "Go",
        ".rs": "Rust",
        ".java": "Java",
        ".yaml": "YAML",
        ".yml": "YAML",
    }
    for path in file_paths:
        for suffix, language in extension_map.items():
            if path.endswith(suffix):
                counts[language] = counts.get(language, 0) + 1
                break
    if not counts:
        return None
    return max(counts.items(), key=lambda item: item[1])[0]


def _infer_framework(chunks: list[CodeChunk]) -> str | None:
    corpus = "\n".join(chunk.chunk_text[:1200].lower() for chunk in chunks)
    if "from fastapi" in corpus or "import fastapi" in corpus:
        return "FastAPI"
    if '"next"' in corpus or "'next'" in corpus or "from \"next" in corpus:
        return "Next.js"
    if "astro" in corpus:
        return "Astro"
    if "github actions" in corpus or ".github/workflows/" in corpus:
        return "GitHub Actions"
    return None
