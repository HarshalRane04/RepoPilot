# Repository Indexer Service

Status: service scaffold. Runtime implementation currently lives in `apps/api/app/services/repo_indexer.py`; this directory is reserved for future service extraction once indexing workers are split from the API process.

Phase 5 is implemented in `apps/api/app/services/repo_indexer.py`.

Current scope:

- Index a local source path through `POST /repos/{repo_id}/index`.
- Skip common generated and dependency directories.
- Chunk text files with line metadata and simple symbol detection.
- Store chunks in `code_chunks` with deterministic mock embeddings and a commit/content fingerprint.
- Retrieve scored context packs through `GET /repos/{repo_id}/context?query=...`.

Remote clone/fetch orchestration and provider-backed embeddings are reserved for the next repository-indexing iteration.
