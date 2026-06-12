from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from repopilot_contracts import RepositoryIndexRequest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CodeChunk, Issue, Repository, RepositoryIndex
from app.db.session import get_db
from app.services.auth import CurrentUser, get_current_user
from app.services.authorization import require_repository_access, require_role
from app.services.repo_indexer import RepositoryIndexer

router = APIRouter()


@router.get("")
async def list_repositories(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, object]]:
    require_role(current_user, "viewer")
    result = await db.execute(select(Repository).order_by(Repository.created_at.desc()))
    repositories = result.scalars().all()
    response: list[dict[str, object]] = []
    indexer = RepositoryIndexer()
    for repo in repositories:
        issue_count = await db.scalar(select(func.count()).select_from(Issue).where(Issue.repository_id == repo.id))
        chunks = (await db.execute(select(CodeChunk).where(CodeChunk.repository_id == repo.id))).scalars().all()
        latest_index = await db.scalar(
            select(RepositoryIndex)
            .where(RepositoryIndex.repository_id == repo.id)
            .order_by(RepositoryIndex.created_at.desc())
            .limit(1)
        )
        file_paths = sorted({chunk.file_path for chunk in chunks})
        test_file_count = sum(1 for path in file_paths if _is_test_file(path))
        embedding_model = latest_index.embedding_model if latest_index else chunks[0].embedding_model if chunks else None
        embedding_provider = latest_index.embedding_provider if latest_index else chunks[0].embedding_provider if chunks else None
        embedding_dimensions = latest_index.embedding_dimensions if latest_index else chunks[0].embedding_dimensions if chunks else None
        index_stale = indexer.index_metadata_is_stale(latest_index) if latest_index else indexer.index_is_stale_for_embeddings(chunks)
        response.append(
            {
                "id": str(repo.id),
                "installation_id": str(repo.installation_id),
                "owner": repo.owner,
                "name": repo.name,
                "default_branch": repo.default_branch,
                "last_indexed_sha": repo.last_indexed_sha,
                "issue_count": issue_count or 0,
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
        )
    return response


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
