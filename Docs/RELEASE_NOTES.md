# RepoPilot AI Release Notes

## Unreleased v1.0 Candidate

RepoPilot is not yet v1.0 release-ready. This candidate is a local, single-tenant control-plane build with credential-gated GitHub/model paths and explicit remaining proof gates.

### Implemented Locally

- FastAPI control plane with PostgreSQL/pgvector schema, Redis/Celery worker, and Celery Beat cleanup scheduler.
- GitHub webhook verification, minimized event storage, delivery dedupe, row-locked idempotent processing, durable queue retry/reconciliation, issue ingestion, and audit records.
- Dashboard surfaces for activity, prompts, repositories, issues, plans, runs, draft PR records, security findings, evals, metrics, and settings readiness.
- Model gateway with mock-first completions, structured JSON validation, embedding helper, budget checks, capped transient provider retries, provider/mode-aware trace hashes, redacted trace metadata, and provider verification hooks.
- Triage prompts with pre-model prompt-injection checks, missing-info detection, deterministic fallback hints, constrained actions, and secret redaction.
- Canonical GitHub repository acquisition with bounded archive extraction and atomic replacement, truthful OAuth-discovery versus GitHub-App acquisition modes, plus safe indexing, embedding reuse for unchanged content, HNSW/lexical candidate retrieval, citations, score breakdowns, and freshness metadata.
- Planning prompts with redacted issue metadata, cited context chunk evidence, policy constraints, deterministic fallback plans, and explicit expected-evidence requirements.
- Human-gated planning with approval/reject/revise paths, plan hash binding, and policy review.
- Executor-mediated implementation with iterative bounded read-tool exploration, approved-path writes, repeated-call suppression, canonical repository-root paths, monorepo-aware validation working directories, complete changed-file manifest hashes, post-apply write-scope checks, patch-bound validation, and bounded retry feedback; approved runs can be queued through security and draft-PR creation in one action.
- Artifact-backed evidence storage with authorized checksum-verified list/download routes and retention tombstones that preserve provenance after local bytes expire.
- Runtime security checks with prompt/secret scanning, finding lifecycle, CodeQL workflow/SARIF/alert ingestion, and release-only Semgrep/dependency-audit evidence outside the agent host process.
- GitHub write/client path for branch/blob/tree/commit/draft-PR/comment/check-run operations, guarded by credentials, write mode, permission checks, validation, and security gates; check-run, check-annotation, and workflow-log helpers now return bounded, redacted metadata/summaries for agent use.
- Draft PR evidence bodies generated from stored approved-plan hashes, patch hashes, changed files, validation evidence hashes/log URIs, redacted security-finding status, model/cost trace summaries, rollback instructions, and persisted body hashes.
- CI analysis and revision-plan path for workflow/check evidence, including redacted gateway-backed CI summary refinement that rejects invented failure reasons.
- Fixture-backed eval reporting with Python and web fixture repositories plus observed plan-quality, context-precision, patch-quality, human-edit-distance, and provider-comparison scoring for target files, disallowed paths, validation evidence, security result, summary intent, reference diff distance, cost, and latency.
- Local eval report generation through `repopilot_evals.BenchmarkReportBuilder` and `make eval-report`, with generated baseline artifacts written under the git-ignored `Docs/eval-reports/` workspace.
- Planning-only provider eval harness through `repopilot_evals.ProviderPlanningEvalRunner` and `make provider-planning-eval`; local runs read provider credentials from RepoPilot's encrypted runtime secret store first, with shell environment variables preserved as an override for CI and one-off tests.
- Retrieval-quality provider eval harness through `repopilot_evals.ProviderRetrievalEvalRunner` and `make provider-retrieval-eval`; local runs read provider credentials from RepoPilot's encrypted runtime secret store first, call embedding-capable provider endpoints, and report context-precision evidence without mutating fixtures.
- Patch-attempt provider eval harness through `repopilot_evals.ProviderPatchEvalRunner` and `make provider-patch-eval`; local runs read provider credentials from RepoPilot's encrypted runtime secret store first, with reports explicit that validation is not passed unless evidence is supplied.
- Applied-patch provider eval harness through `repopilot_evals.ProviderAppliedPatchEvalRunner` and `make provider-applied-patch-eval`; local runs copy fixtures to temporary workspaces, apply model-generated unified diffs, run benchmark-declared validation commands, derive security results from changed paths and diff content, accept matching no-patch block/escalation decisions for security fixtures, and report patch-quality evidence without mutating fixtures.
- Source-boundary manifest generator through `scripts/source_boundary_manifest.py` and `make source-boundary-manifest`, with non-ignored candidate file hashes written under the git-ignored `Docs/release-artifacts/` workspace.
- Redacted credential readiness snapshot through `scripts/readiness_snapshot.py` and `make readiness-snapshot`, with current GitHub/model/scanner readiness states written under the git-ignored `Docs/release-artifacts/` workspace.
- Redacted aggregate credential smoke summary through `scripts/credential_smoke.py` and `make credential-smoke`, combining GitHub OAuth, GitHub App, and model-provider smoke status without exposing secrets.
- Executed security scanner snapshot through `scripts/security_scanner_snapshot.py`, `make security-scanner-snapshot`, and the CI scanner artifact job. The target runs Semgrep, `pip-audit`, and `npm audit`, verifies CodeQL evidence, records tool versions/results, and binds the report to a release source fingerprint under `Docs/release-artifacts/` or uploaded workflow artifacts.
- Release workflow evidence job in `.github/workflows/release.yml`; manual and tag-triggered release runs upload deterministic local eval, source-boundary manifest, credential-smoke, scanner, and deployment-validation artifacts before API/web/sandbox image builds.
- Source-boundary release hygiene scanner through `scripts/release_hygiene.py` and `make release-hygiene`, with Markdown/JSON reports written under the git-ignored `Docs/release-artifacts/` workspace.
- Release GIF builder through `scripts/release_gifs.py` and `make release-gifs`, with local plan-to-PR and governance flow artifacts plus Markdown/JSON manifests written under the git-ignored `Docs/release-artifacts/` workspace.
- Deployment validation scanner through `scripts/deployment_validate.py`, `make deployment-validate`, and `make deployment-smoke`, with Markdown/JSON static and local-runtime reports written under the git-ignored `Docs/release-artifacts/` workspace.
- Package boundaries for shared contracts, eval verifier, policy engine, LLM catalog helpers, and GitHub permission helpers.
- Fresh-database Alembic verifier that runs `upgrade head -> downgrade base -> upgrade head` on a temporary PostgreSQL database.
- Core operator-console screenshot generation under the git-ignored `Docs/release-artifacts/` workspace, plus a responsive mobile shell fix that replaces the clipped fixed sidebar with a horizontal top rail on narrow screens.
- Credential handoff guide at `Docs/CREDENTIAL_HANDOFF.md` for live GitHub App, OAuth, model-provider, scanner, smoke-test, evidence, and stop-condition inputs.

### Verification Snapshot

- API compile check: passed.
- Full API test suite: `317 passed`.
- Alembic head: `0011_artifact_tombstones`.
- Fresh database migration verification: passed with `make migration-verify`.
- Docker Compose config: passed with placeholder local-development secrets.
- Artifact storage mount: API container mounts `repopilot_agent_artifacts` at `/tmp/repopilot-artifacts`.
- Web typecheck: passed in the running Docker web container.
- Web production build: passed in the running Docker web container against the live bind-mounted source.
- API health: passed at `http://127.0.0.1:8000/health`.
- Dashboard HTTP/rendered-label smoke: passed at `http://127.0.0.1:3001/`.
- Local runtime deployment smoke: passed with component-level `/ready` checks for Postgres, Redis, sandbox, repository storage, and artifact storage plus the dashboard endpoint.
- Isolated sandbox smoke: the rebuilt networkless Unix-socket runner executed `python -m pytest --version` successfully from a nested `apps/api` working directory in 238 ms.
- LLM trace smoke: passed through local prompt creation with OpenRouter configured; `llm_traces` rows recorded provider `openrouter`, modes `live`/`fallback`, response hashes, and redacted metadata, and `/runs/{run_id}/trace` returned those fields.
- Source-boundary manifest: generated `338` non-ignored source candidate entries with aggregate SHA-256 evidence after the codebase audit artifact was added.
- Credential readiness snapshot: captured running-app readiness showing `production_ready=true` for local `oss-demo`, `model_mode=live_model_verified`, `github_mode=read_only_verified`, no blockers, local-record mode enabled, and write mode disabled.
- Credential smoke summary: strict redacted smoke evidence passed for GitHub OAuth authorization, GitHub App installation-token creation, and the selected live model provider without exposing secrets.
- Security scanner snapshot: executed Semgrep, Python and npm dependency audits, and CodeQL evidence checks with zero blockers, recording tool versions and the scanned source fingerprint.
- CodeQL proof: public `main` CodeQL workflow succeeded for JavaScript/TypeScript and Python analysis after the repository was made public.
- Browser QA: passed at default desktop viewport for dashboard, repositories/repository detail, plan review, agent runs, run trace, pull requests, security, evaluations, and settings; passed at 390x844 mobile viewport for the dashboard after the responsive shell fix.
- Release GIF evidence: generated local plan-to-PR and governance visual-flow GIFs from the captured operator-console screenshots.

### Known Limitations

- Real GitHub App write readiness is not production-proven until credentials and a disposable demo repository prove branch/commit/draft-PR smoke testing.
- Provider-backed planning, patch-attempt, retrieval, and applied-patch evals were executed with `openrouter/free`; planning and patch quality were 0%, and retrieval context precision was 0 because the free router is not an embedding model. This is negative quality evidence, not a supported model pair. A stronger completion model and real embedding model must pass the same gates before promotion.
- CI uploads Semgrep/dependency-audit posture evidence, and public-repository CodeQL analysis succeeds; credentialed CodeQL alert-fetch evidence is still pending until live GitHub credentials are configured.
- Artifact storage currently uses a local filesystem-backed Docker volume with authorized checksum-verified retrieval and tombstoned retention; production object storage and signed remote retrieval remain deployment work.
- Full browser visual QA remains partially pending: core static screenshots and local visual-flow GIFs are captured, but live credentialed write/CI states still need release captures.
- Release deployment has a guide plus local runtime smoke evidence, but production-like cloud/VM deployment validation is still pending.
- No autonomous merge behavior is included or planned for v1.

### Upgrade Notes

- Alembic revision IDs fit Alembic's default `version_num VARCHAR(32)` column. Local databases upgrade through evidence provenance, durable webhook delivery, HNSW retrieval, and artifact tombstones at `0011_artifact_tombstones`.
- `REPOPILOT_ARTIFACT_STORE_ROOT`, `REPOPILOT_ARTIFACT_INLINE_MAX_BYTES`, `REPOPILOT_ARTIFACT_RETENTION_MAX_AGE_SECONDS`, `REPOPILOT_ARTIFACT_RETENTION_INTERVAL_SECONDS`, and `REPOPILOT_ARTIFACT_RETENTION_DRY_RUN` control local artifact storage, large inline-output externalization, and scheduled local retention cleanup.

### v1.0 Tag Gate

Tag `v1.0.0` only after credentialed GitHub smoke, provider-backed evals, live-state browser captures, deployment validation, and final source-boundary hygiene all pass.
