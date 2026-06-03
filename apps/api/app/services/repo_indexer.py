from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from repopilot_contracts import CodeContextChunk, CodeContextPack, RepositoryIndexRequest, RepositoryIndexResult
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import CodeChunk, Repository, RepositoryIndex
from app.services.audit import record_audit
from app.services.model_gateway import ModelGateway

VECTOR_DIMENSIONS = 1536
CHUNKER_VERSION = "semantic-v1"
IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".next",
    ".cache",
    ".nox",
    ".parcel-cache",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".secrets",
    ".turbo",
    ".tox",
    ".vite",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "htmlcov",
    "node_modules",
    "out",
    "target",
    "vendor",
    ".venv",
    "venv",
}

SENSITIVE_FILE_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    ".npmrc",
    ".pypirc",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
}

SENSITIVE_SUFFIXES = {
    ".key",
    ".pem",
    ".p12",
    ".pfx",
}

GENERATED_FILE_MARKERS = {
    ".gen.",
    ".generated.",
    ".min.",
    ".pb.",
}

TEXT_EXTENSIONS = {
    ".go",
    ".java",
    ".js",
    ".jsx",
    ".json",
    ".md",
    ".mjs",
    ".py",
    ".rs",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}

SOURCE_EXTENSIONS = {
    ".go",
    ".java",
    ".js",
    ".jsx",
    ".mjs",
    ".py",
    ".rs",
    ".ts",
    ".tsx",
}

DOC_EXTENSIONS = {
    ".md",
    ".txt",
}

CONFIG_EXTENSIONS = {
    ".json",
    ".toml",
    ".yaml",
    ".yml",
}


@dataclass(frozen=True)
class SourceChunk:
    file_path: str
    symbol_name: str | None
    chunk_type: str
    text: str
    start_line: int
    end_line: int


@dataclass(frozen=True)
class SourceSpan:
    start_line: int
    end_line: int
    symbol_name: str | None


@dataclass(frozen=True)
class RetrievalScore:
    total: float
    lexical: float
    semantic: float
    path: float
    reason: str


class RepositoryIndexer:
    async def index_repository(
        self,
        db: AsyncSession,
        *,
        repository_id: UUID,
        request: RepositoryIndexRequest,
    ) -> RepositoryIndexResult:
        repository = await db.get(Repository, repository_id)
        if repository is None:
            raise ValueError(f"Repository not found: {repository_id}")

        source_root = self._server_managed_source_path(request.source_path)

        files = list(self._iter_indexable_files(source_root, max_files=request.max_files, max_file_bytes=request.max_file_bytes))
        content_fingerprint = self._content_fingerprint(source_root, files)
        commit_sha = request.commit_sha or content_fingerprint
        chunks: list[SourceChunk] = []
        skipped_files = 0

        for file_path in files:
            try:
                relative_path = file_path.relative_to(source_root).as_posix()
                text = file_path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                skipped_files += 1
                continue
            chunks.extend(self._chunk_file(relative_path=relative_path, text=text))

        await db.execute(delete(CodeChunk).where(CodeChunk.repository_id == repository.id))
        embedding_response = await ModelGateway().embed(
            db,
            run_id=None,
            texts=[f"{chunk.file_path}\n{chunk.text}" for chunk in chunks],
            agent_name="repo_indexer",
        )
        embeddings = [self._normalize_embedding(vector) for vector in embedding_response.embeddings]
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            db.add(
                CodeChunk(
                    repository_id=repository.id,
                    file_path=chunk.file_path,
                    symbol_name=chunk.symbol_name,
                    chunk_type=chunk.chunk_type,
                    chunk_text=self._encode_chunk_text(chunk),
                    embedding=embedding,
                    embedding_provider=embedding_response.provider,
                    embedding_model=embedding_response.model,
                    embedding_dimensions=embedding_response.dimensions,
                    commit_sha=commit_sha,
                )
            )

        index_record = RepositoryIndex(
            repository_id=repository.id,
            source_path=str(source_root),
            commit_sha=commit_sha,
            content_fingerprint=content_fingerprint,
            files_indexed=len(files) - skipped_files,
            chunks_indexed=len(chunks),
            skipped_files=skipped_files,
            embedding_provider=embedding_response.provider,
            embedding_model=embedding_response.model,
            embedding_dimensions=embedding_response.dimensions,
            chunker_version=CHUNKER_VERSION,
            status="ready",
            metadata_json={
                "language_counts": self._language_counts(files),
                "chunk_types": self._chunk_type_counts(chunks),
                "max_files": request.max_files,
                "max_file_bytes": request.max_file_bytes,
                "embedding_mode": embedding_response.mode.value,
            },
        )
        db.add(index_record)
        await db.flush()
        repository.last_indexed_sha = commit_sha
        await record_audit(
            db,
            actor_type="system",
            action="repository.indexed",
            entity_type="repository",
            entity_id=str(repository.id),
            metadata={
                "source_path": str(source_root),
                "index_id": str(index_record.id),
                "files_indexed": len(files) - skipped_files,
                "chunks_indexed": len(chunks),
                "commit_sha": commit_sha,
                "content_fingerprint": content_fingerprint,
                "embedding_model": embedding_response.model,
                "embedding_mode": embedding_response.mode.value,
                "chunker_version": CHUNKER_VERSION,
            },
        )
        await db.commit()

        return RepositoryIndexResult(
            index_id=str(index_record.id),
            repository_id=str(repository.id),
            source_path=str(source_root),
            commit_sha=commit_sha,
            content_fingerprint=content_fingerprint,
            files_indexed=len(files) - skipped_files,
            chunks_indexed=len(chunks),
            skipped_files=skipped_files,
            embedding_provider=embedding_response.provider,
            embedding_model=embedding_response.model,
            embedding_dimensions=embedding_response.dimensions,
            chunker_version=CHUNKER_VERSION,
        )

    def _server_managed_source_path(self, source_path: str) -> Path:
        workspace_root = Path(settings.repository_workspace_root).expanduser().resolve()
        source_root = Path(source_path).expanduser().resolve()
        if not source_root.exists() or not source_root.is_dir():
            raise ValueError(f"Source path is not a directory: {source_root}")
        if not source_root.is_relative_to(workspace_root):
            raise ValueError(f"Source path is outside the configured repository workspace root: {workspace_root}")
        return source_root

    async def retrieve_context(
        self,
        db: AsyncSession,
        *,
        repository_id: UUID,
        query: str,
        limit: int = 6,
    ) -> CodeContextPack:
        result = await db.execute(select(CodeChunk).where(CodeChunk.repository_id == repository_id))
        chunks = result.scalars().all()
        query_terms = self._terms(query)
        query_embedding_response = await ModelGateway().embed(
            db,
            run_id=None,
            texts=[query],
            agent_name="repo_retrieval",
        )
        query_embedding = self._normalize_embedding(query_embedding_response.embeddings[0]) if query_embedding_response.embeddings else self._embed_text(query)

        scored: list[tuple[RetrievalScore, CodeChunk, int, int, str]] = []
        for chunk in chunks:
            start_line, end_line, text = self._decode_chunk_text(chunk.chunk_text)
            score = self._score_breakdown(
                text=text,
                file_path=chunk.file_path,
                query_terms=query_terms,
                query_embedding=query_embedding,
                chunk_embedding=chunk.embedding,
            )
            if score.total > 0:
                scored.append((score, chunk, start_line, end_line, text))

        scored.sort(key=lambda item: item[0].total, reverse=True)
        selected = scored[:limit]
        context_chunks = [
            CodeContextChunk(
                file_path=chunk.file_path,
                symbol_name=chunk.symbol_name,
                chunk_type=chunk.chunk_type,
                start_line=start_line,
                end_line=end_line,
                score=round(score.total, 3),
                semantic_score=round(score.semantic, 3),
                lexical_score=round(score.lexical, 3),
                path_score=round(score.path, 3),
                selection_reason=score.reason,
                freshness=self._freshness_metadata(chunk),
                text=text,
            )
            for score, chunk, start_line, end_line, text in selected
        ]
        return CodeContextPack(
            repository_id=str(repository_id),
            query=query,
            chunks=context_chunks,
            citations=[f"{chunk.file_path}:{chunk.start_line}-{chunk.end_line}" for chunk in context_chunks],
        )

    def _iter_indexable_files(self, root: Path, *, max_files: int, max_file_bytes: int) -> list[Path]:
        files: list[Path] = []
        resolved_root = root.resolve()
        for path in root.rglob("*"):
            if len(files) >= max_files:
                break
            try:
                relative_path = path.relative_to(root)
            except ValueError:
                continue
            if any(part.lower() in IGNORED_DIRS for part in relative_path.parts):
                continue
            try:
                resolved_path = path.resolve(strict=True)
            except OSError:
                continue
            if not resolved_path.is_relative_to(resolved_root):
                continue
            if not path.is_file():
                continue
            relative_text = relative_path.as_posix()
            if self._is_sensitive_file(relative_text):
                continue
            if self._is_generated_file(relative_text):
                continue
            if path.suffix.lower() not in TEXT_EXTENSIONS:
                continue
            try:
                if path.stat().st_size > max_file_bytes:
                    continue
            except OSError:
                continue
            files.append(path)
        return sorted(files)

    def _chunk_file(self, *, relative_path: str, text: str, max_lines: int = 80, overlap: int = 10) -> list[SourceChunk]:
        lines = text.splitlines()
        if not lines:
            return []

        spans = self._semantic_spans(relative_path=relative_path, lines=lines)
        if spans:
            chunks: list[SourceChunk] = []
            last_end = 0
            for span in spans:
                if span.start_line > last_end + 1:
                    chunks.extend(
                        self._fixed_window_chunks(
                            relative_path=relative_path,
                            lines=lines,
                            start_line=last_end + 1,
                            end_line=span.start_line - 1,
                            symbol_name=None,
                            max_lines=max_lines,
                            overlap=overlap,
                        )
                    )
                chunks.extend(
                    self._fixed_window_chunks(
                        relative_path=relative_path,
                        lines=lines,
                        start_line=span.start_line,
                        end_line=span.end_line,
                        symbol_name=span.symbol_name,
                        max_lines=max_lines,
                        overlap=overlap,
                    )
                )
                last_end = max(last_end, span.end_line)
            if last_end < len(lines):
                chunks.extend(
                    self._fixed_window_chunks(
                        relative_path=relative_path,
                        lines=lines,
                        start_line=last_end + 1,
                        end_line=len(lines),
                        symbol_name=None,
                        max_lines=max_lines,
                        overlap=overlap,
                    )
                )
            return chunks

        return self._fixed_window_chunks(
            relative_path=relative_path,
            lines=lines,
            start_line=1,
            end_line=len(lines),
            symbol_name=None,
            max_lines=max_lines,
            overlap=overlap,
        )

    def _fixed_window_chunks(
        self,
        *,
        relative_path: str,
        lines: list[str],
        start_line: int,
        end_line: int,
        symbol_name: str | None,
        max_lines: int,
        overlap: int,
    ) -> list[SourceChunk]:
        chunks: list[SourceChunk] = []
        start = max(start_line, 1)
        final_line = min(end_line, len(lines))
        while start <= final_line:
            end = min(start + max_lines - 1, final_line)
            chunk_lines = lines[start - 1:end]
            chunk_text = "\n".join(chunk_lines).strip()
            if chunk_text:
                chunks.append(
                    SourceChunk(
                        file_path=relative_path,
                        symbol_name=symbol_name or self._symbol_name(chunk_lines),
                        chunk_type=self._chunk_type(relative_path),
                        text=chunk_text,
                        start_line=start,
                        end_line=end,
                    )
                )
            if end == final_line:
                break
            start = max(start + 1, end - overlap + 1)
        return chunks

    def _semantic_spans(self, *, relative_path: str, lines: list[str]) -> list[SourceSpan]:
        suffix = Path(relative_path).suffix.lower()
        if suffix == ".md":
            return self._markdown_spans(lines)
        pattern = self._symbol_pattern_for_suffix(suffix)
        if pattern is None:
            return []
        starts: list[tuple[int, str]] = []
        for index, line in enumerate(lines, start=1):
            match = pattern.match(line)
            if not match:
                continue
            symbol = next((group for group in match.groups() if group), None)
            if symbol:
                starts.append((index, symbol))
        return [
            SourceSpan(
                start_line=start_line,
                end_line=(starts[position + 1][0] - 1 if position + 1 < len(starts) else len(lines)),
                symbol_name=symbol,
            )
            for position, (start_line, symbol) in enumerate(starts)
        ]

    def _markdown_spans(self, lines: list[str]) -> list[SourceSpan]:
        starts: list[tuple[int, str]] = []
        for index, line in enumerate(lines, start=1):
            match = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", line)
            if match:
                starts.append((index, match.group(1).strip()))
        return [
            SourceSpan(
                start_line=start_line,
                end_line=(starts[position + 1][0] - 1 if position + 1 < len(starts) else len(lines)),
                symbol_name=symbol,
            )
            for position, (start_line, symbol) in enumerate(starts)
        ]

    def _symbol_pattern_for_suffix(self, suffix: str) -> re.Pattern[str] | None:
        patterns = {
            ".py": r"^\s*(?:async\s+def|def|class)\s+([A-Za-z_][A-Za-z0-9_]*)\b",
            ".js": r"^\s*(?:export\s+)?(?:async\s+)?(?:function|class)\s+([A-Za-z_$][A-Za-z0-9_$]*)\b|^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=",
            ".jsx": r"^\s*(?:export\s+)?(?:async\s+)?(?:function|class)\s+([A-Za-z_$][A-Za-z0-9_$]*)\b|^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=",
            ".mjs": r"^\s*(?:export\s+)?(?:async\s+)?(?:function|class)\s+([A-Za-z_$][A-Za-z0-9_$]*)\b|^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=",
            ".ts": r"^\s*(?:export\s+)?(?:async\s+)?(?:function|class|interface|type)\s+([A-Za-z_$][A-Za-z0-9_$]*)\b|^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=",
            ".tsx": r"^\s*(?:export\s+)?(?:async\s+)?(?:function|class|interface|type)\s+([A-Za-z_$][A-Za-z0-9_$]*)\b|^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=",
            ".go": r"^\s*func\s+(?:\([^)]+\)\s*)?([A-Za-z_][A-Za-z0-9_]*)\b",
            ".rs": r"^\s*(?:pub\s+)?(?:async\s+)?(?:fn|struct|enum|trait|impl)\s+([A-Za-z_][A-Za-z0-9_]*)\b",
            ".java": r"^\s*(?:(?:public|private|protected|static|final|abstract|synchronized)\s+)*(?:class|interface|enum|record)\s+([A-Za-z_][A-Za-z0-9_]*)\b|^\s*(?:(?:public|private|protected|static|final|abstract|synchronized)\s+)+[A-Za-z0-9_<>, ?\[\]]+\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
        }
        pattern = patterns.get(suffix)
        return re.compile(pattern) if pattern else None

    def _symbol_name(self, lines: list[str]) -> str | None:
        for line in lines:
            match = re.match(r"\s*(?:def|class|function|const|let|export function)\s+([A-Za-z0-9_]+)", line)
            if match:
                return match.group(1)
        return None

    def _chunk_type(self, path: str) -> str:
        suffix = Path(path).suffix.lower()
        if self._is_test_file(path):
            return "test"
        if suffix in DOC_EXTENSIONS:
            return "doc"
        if suffix in CONFIG_EXTENSIONS:
            return "config"
        if suffix in SOURCE_EXTENSIONS:
            return "source"
        return suffix.lstrip(".") or "text"

    def _is_test_file(self, path: str) -> bool:
        lowered = path.lower()
        return (
            "/test" in lowered
            or lowered.startswith("test")
            or ".test." in lowered
            or ".spec." in lowered
            or lowered.endswith("_test.py")
        )

    def _is_sensitive_file(self, relative_path: str) -> bool:
        path = Path(relative_path)
        lowered_parts = {part.lower() for part in path.parts}
        if lowered_parts.intersection({"secrets", ".secrets"}):
            return True
        name = path.name.lower()
        if name in SENSITIVE_FILE_NAMES:
            return True
        if any(name.startswith(prefix) for prefix in (".env.", "secret.", "secrets.")):
            return True
        return path.suffix.lower() in SENSITIVE_SUFFIXES

    def _is_generated_file(self, relative_path: str) -> bool:
        name = Path(relative_path).name.lower()
        return any(marker in name for marker in GENERATED_FILE_MARKERS)

    def _encode_chunk_text(self, chunk: SourceChunk) -> str:
        return f"@@ lines={chunk.start_line}-{chunk.end_line}\n{chunk.text}"

    def _decode_chunk_text(self, value: str) -> tuple[int, int, str]:
        first, _, rest = value.partition("\n")
        match = re.match(r"@@ lines=(\d+)-(\d+)", first)
        if not match:
            return 1, max(1, len(value.splitlines())), value
        return int(match.group(1)), int(match.group(2)), rest

    def _terms(self, value: str) -> set[str]:
        return {term for term in re.findall(r"[a-zA-Z0-9_]{3,}", value.lower()) if term not in {"the", "and", "for"}}

    def _score_breakdown(
        self,
        *,
        text: str,
        file_path: str,
        query_terms: set[str],
        query_embedding: list[float],
        chunk_embedding: list[float] | None,
    ) -> RetrievalScore:
        if not query_terms:
            return RetrievalScore(total=0.0, lexical=0.0, semantic=0.0, path=0.0, reason="No searchable query terms.")
        searchable = f"{file_path}\n{text}".lower()
        hits = sum(1 for term in query_terms if term in searchable)
        lexical_score = hits / max(len(query_terms), 1)
        path_score = 0.2 if any(term in file_path.lower() for term in query_terms) else 0.0
        vector_score = self._cosine_similarity(query_embedding, [] if chunk_embedding is None else list(chunk_embedding))
        semantic_score = max(vector_score, 0.0)
        total = lexical_score + path_score + (0.25 * semantic_score)
        reasons: list[str] = []
        if lexical_score > 0:
            reasons.append("query terms matched chunk text")
        if path_score > 0:
            reasons.append("query terms matched file path")
        if semantic_score > 0:
            reasons.append("embedding similarity contributed")
        return RetrievalScore(
            total=total,
            lexical=lexical_score,
            semantic=semantic_score,
            path=path_score,
            reason=", ".join(reasons) if reasons else "No positive retrieval signal.",
        )

    def _freshness_metadata(self, chunk: CodeChunk) -> dict[str, object]:
        return {
            "commit_sha": chunk.commit_sha,
            "embedding_provider": chunk.embedding_provider,
            "embedding_model": chunk.embedding_model,
            "embedding_dimensions": chunk.embedding_dimensions,
            "chunker_version": CHUNKER_VERSION,
            "stale": self.index_is_stale_for_embeddings([chunk]),
        }

    def index_is_stale_for_embeddings(self, chunks: list[CodeChunk]) -> bool:
        if not chunks:
            return False
        configured_provider = settings.embedding_provider
        configured_model = settings.embedding_model
        configured_dimensions = int(settings.embedding_dimensions)
        return any(
            chunk.embedding_provider != configured_provider
            or chunk.embedding_model != configured_model
            or chunk.embedding_dimensions != configured_dimensions
            for chunk in chunks
        )

    def index_metadata_is_stale(self, index: RepositoryIndex | None) -> bool:
        if index is None:
            return False
        return (
            index.embedding_provider != settings.embedding_provider
            or index.embedding_model != settings.embedding_model
            or index.embedding_dimensions != int(settings.embedding_dimensions)
            or index.chunker_version != CHUNKER_VERSION
        )

    def _content_fingerprint(self, root: Path, files: list[Path]) -> str:
        digest = hashlib.sha256()
        for path in files:
            digest.update(path.relative_to(root).as_posix().encode("utf-8"))
            try:
                digest.update(path.read_bytes())
            except OSError:
                continue
        return digest.hexdigest()[:16]

    def _language_counts(self, files: list[Path]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for path in files:
            language = self._language_for_suffix(path.suffix.lower())
            if language:
                counts[language] = counts.get(language, 0) + 1
        return counts

    def _language_for_suffix(self, suffix: str) -> str | None:
        return {
            ".go": "Go",
            ".java": "Java",
            ".js": "JavaScript",
            ".jsx": "JavaScript",
            ".mjs": "JavaScript",
            ".md": "Markdown",
            ".py": "Python",
            ".rs": "Rust",
            ".ts": "TypeScript",
            ".tsx": "TypeScript",
            ".yaml": "YAML",
            ".yml": "YAML",
        }.get(suffix)

    def _chunk_type_counts(self, chunks: list[SourceChunk]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for chunk in chunks:
            counts[chunk.chunk_type] = counts.get(chunk.chunk_type, 0) + 1
        return counts

    def _embed_text(self, value: str, dimensions: int = 1536) -> list[float]:
        vector = [0.0] * dimensions
        for term in self._terms(value):
            bucket = int(hashlib.sha256(term.encode("utf-8")).hexdigest(), 16) % dimensions
            vector[bucket] += 1.0
        magnitude = math.sqrt(sum(component * component for component in vector))
        if magnitude == 0:
            return vector
        return [component / magnitude for component in vector]

    def _normalize_embedding(self, vector: list[float]) -> list[float]:
        if len(vector) == VECTOR_DIMENSIONS:
            return vector
        if len(vector) > VECTOR_DIMENSIONS:
            return vector[:VECTOR_DIMENSIONS]
        return [*vector, *([0.0] * (VECTOR_DIMENSIONS - len(vector)))]

    def _cosine_similarity(self, left: list[float], right: list[float]) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0
        return sum(left_item * right_item for left_item, right_item in zip(left, right, strict=True))
