# RepoPilot AI Case Study

RepoPilot AI demonstrates a human-gated coding agent control plane for GitHub issues. The build prioritizes safety and evidence over autonomy: plans require approval, generated patches run in isolated workspaces, risky commands and paths are blocked, security findings gate draft PR records, and CI evidence is summarized before review.

## Implemented Outcome

- Issue webhook to tracked repository and issue.
- Repository indexing with cited context retrieval.
- Human-approved implementation plan.
- Executor-mediated implementation/test evidence generation in an isolated run workspace.
- Sandbox validation.
- Security scan, finding lifecycle, Semgrep/dependency-audit adapters, CodeQL SARIF ingestion, and credential-gated CodeQL alert fetch.
- Local draft PR record by default, with real GitHub branch/commit/draft-PR path implemented behind credentials and write gates.
- CI analysis and ready-for-review promotion.
- Run trace, LLM trace metadata, audit records, and evaluation report.

## Portfolio Signals

- Backend: FastAPI, SQLAlchemy, Alembic, PostgreSQL/pgvector, Redis/Celery.
- Frontend: Next.js operational dashboard.
- DevSecOps: HMAC verification, policy gates, sandboxing, secret/injection scanning, audit logs.
- LLMOps: provider-agnostic model gateway, LLM trace table, run replay surface, cost/latency metric hooks.
- Evaluation: fixture repositories, benchmark categories, observed plan-quality/context-precision/patch-quality/human-edit-distance/provider-comparison scoring, local Markdown/JSON eval reports, planning-only provider harness, measurable control-plane metrics, release checklist.

## Remaining Proof Before v1.0

- Credentialed GitHub App smoke test on a disposable demo repository.
- Live model and embedding provider evals with observed plan-quality, context-precision, patch-quality, human-edit-distance, provider ranking, cost, and latency evidence.
- Credentialed browser captures for live GitHub/model/write states.
- Provider-backed scanner evidence in CI.
- Final source-boundary commit and release tag.
