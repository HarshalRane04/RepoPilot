# RepoPilot AI Release Notes

## Unreleased v1.0 Candidate

RepoPilot is not yet v1.0 release-ready. This candidate is a local, single-tenant control-plane build with credential-gated GitHub/model paths and explicit remaining proof gates.

### Implemented Locally

- FastAPI control plane with PostgreSQL/pgvector schema, Redis/Celery worker, and Celery Beat cleanup scheduler.
- GitHub webhook verification, event normalization, delivery dedupe, queue dispatch, issue ingestion, and audit records.
- Dashboard surfaces for activity, prompts, repositories, issues, plans, runs, draft PR records, security findings, evals, metrics, and settings readiness.
- Model gateway with mock-first completions, structured JSON validation, embedding helper, budget checks, capped transient provider retries, provider/mode-aware trace hashes, redacted trace metadata, and provider verification hooks.
- Triage prompts with pre-model prompt-injection checks, missing-info detection, deterministic fallback hints, constrained actions, and secret redaction.
- Repository indexing with safe file scanning, secret-like path filtering, generated/dependency skip rules, symlink escape rejection, semantic symbol/heading chunking, deterministic mock embeddings, citations, semantic/lexical/path score breakdowns, context freshness metadata, and dedicated `repository_indexes` metadata for content fingerprint, embedding model, chunker version, and stale-index detection.
- Planning prompts with redacted issue metadata, cited context chunk evidence, policy constraints, deterministic fallback plans, and explicit expected-evidence requirements.
- Human-gated planning with approval/reject/revise paths, plan hash binding, and policy review.
- Executor-mediated implementation in isolated run workspaces with approved-path controls, diff hash capture, validation, and bounded retry behavior.
- Artifact-backed evidence storage for patch diffs, validation logs, and large tool outputs through `ArtifactRecord`, `ArtifactReference`, `local://artifacts/...` URIs, SHA-256 metadata, and the local `agent_artifacts` Docker volume.
- Security checks with prompt/secret scanning, finding lifecycle, Semgrep/dependency-audit adapters, CodeQL workflow file, CodeQL SARIF ingestion, and credential-gated CodeQL alert fetch.
- GitHub write/client path for branch/blob/tree/commit/draft-PR/comment/check-run operations, guarded by credentials, write mode, permission checks, validation, and security gates; check-run, check-annotation, and workflow-log helpers now return bounded, redacted metadata/summaries for agent use.
- Draft PR evidence bodies generated from stored approved-plan hashes, patch hashes, changed files, validation evidence hashes/log URIs, redacted security-finding status, model/cost trace summaries, rollback instructions, and persisted body hashes.
- CI analysis and revision-plan path for workflow/check evidence, including redacted gateway-backed CI summary refinement that rejects invented failure reasons.
- Fixture-backed eval reporting with Python and web fixture repositories plus observed plan-quality, context-precision, patch-quality, human-edit-distance, and provider-comparison scoring for target files, disallowed paths, validation evidence, security result, summary intent, reference diff distance, cost, and latency.
- Local eval report generation through `repopilot_evals.BenchmarkReportBuilder`, `make eval-report`, and checked-in baseline artifacts under `Docs/eval-reports/`.
- Planning-only provider eval harness through `repopilot_evals.ProviderPlanningEvalRunner` and `make provider-planning-eval`; local runs read provider credentials from RepoPilot's encrypted runtime secret store first, with shell environment variables preserved as an override for CI and one-off tests.
- Retrieval-quality provider eval harness through `repopilot_evals.ProviderRetrievalEvalRunner` and `make provider-retrieval-eval`; local runs read provider credentials from RepoPilot's encrypted runtime secret store first, call embedding-capable provider endpoints, and report context-precision evidence without mutating fixtures.
- Patch-attempt provider eval harness through `repopilot_evals.ProviderPatchEvalRunner` and `make provider-patch-eval`; local runs read provider credentials from RepoPilot's encrypted runtime secret store first, with reports explicit that validation is not passed unless evidence is supplied.
- Applied-patch provider eval harness through `repopilot_evals.ProviderAppliedPatchEvalRunner` and `make provider-applied-patch-eval`; local runs copy fixtures to temporary workspaces, apply model-generated unified diffs, run benchmark-declared validation commands, derive security results from changed paths and diff content, accept matching no-patch block/escalation decisions for security fixtures, and report patch-quality evidence without mutating fixtures.
- Source-boundary manifest generator through `scripts/source_boundary_manifest.py` and `make source-boundary-manifest`, with non-ignored candidate file hashes under `Docs/release-artifacts/`.
- Redacted credential readiness snapshot through `scripts/readiness_snapshot.py` and `make readiness-snapshot`, with current GitHub/model/scanner readiness states under `Docs/release-artifacts/`.
- Security scanner posture snapshot through `scripts/security_scanner_snapshot.py`, `make security-scanner-snapshot`, and the CI `scanner-posture` artifact job, with external scanner enablement, dependency manifest, CodeQL workflow, and tool-availability evidence under `Docs/release-artifacts/` or uploaded workflow artifacts.
- Release workflow evidence job in `.github/workflows/release.yml`; manual and tag-triggered release runs now upload deterministic local eval, source-boundary manifest, and deployment-validation artifacts before API/web/sandbox image builds. Dry run `27059971285` passed and its downloaded artifact hashes are archived under `Docs/release-artifacts/release-workflow-dry-run.*`.
- Source-boundary release hygiene scanner through `scripts/release_hygiene.py` and `make release-hygiene`, with Markdown/JSON reports under `Docs/release-artifacts/`.
- Release GIF builder through `scripts/release_gifs.py` and `make release-gifs`, with local plan-to-PR and governance flow artifacts plus Markdown/JSON manifests under `Docs/release-artifacts/`.
- Deployment validation scanner through `scripts/deployment_validate.py`, `make deployment-validate`, and `make deployment-smoke`, with Markdown/JSON static and local-runtime reports under `Docs/release-artifacts/`.
- Package boundaries for shared contracts, eval verifier, policy engine, LLM catalog helpers, and GitHub permission helpers.
- Fresh-database Alembic verifier that runs `upgrade head -> downgrade base -> upgrade head` on a temporary PostgreSQL database.
- Core operator-console screenshots under `Docs/release-artifacts/`, plus a responsive mobile shell fix that replaces the clipped fixed sidebar with a horizontal top rail on narrow screens.
- Credential handoff guide at `Docs/CREDENTIAL_HANDOFF.md` for live GitHub App, OAuth, model-provider, scanner, smoke-test, evidence, and stop-condition inputs.

### Verification Snapshot

- API compile check: passed.
- Full API test suite: `171 passed`.
- Alembic head: `0006_llm_trace_metadata`.
- Fresh database migration verification: passed with `make migration-verify`.
- Docker Compose config: passed with placeholder local-development secrets.
- Artifact storage mount: API container mounts `repopilot_agent_artifacts` at `/tmp/repopilot-artifacts`.
- Web typecheck: passed in the running Docker web container.
- Web production build: passed in the running Docker web container against the live bind-mounted source.
- API health: passed at `http://127.0.0.1:8000/health`.
- Dashboard HTTP/rendered-label smoke: passed at `http://127.0.0.1:3001/`.
- Local runtime deployment smoke: passed with `make deployment-smoke` against `http://127.0.0.1:8000/health` and `http://127.0.0.1:3001/`.
- LLM trace smoke: passed through local prompt creation with OpenRouter configured; `llm_traces` rows recorded provider `openrouter`, modes `live`/`fallback`, response hashes, and redacted metadata, and `/runs/{run_id}/trace` returned those fields.
- Source-boundary manifest: generated `319` non-ignored source candidate entries with aggregate SHA-256 evidence.
- Credential readiness snapshot: captured running-app readiness showing `model_mode=live_model_verified`, `github_mode=missing_credentials`, and write mode disabled.
- Security scanner snapshot: captured local scanner posture, dependency manifests, external scanner enablement, and installed-tool availability; current local proof still reports external scanner enablement as incomplete until Semgrep, dependency audit, and CodeQL are enabled in the runtime/CI path.
- Browser QA: passed at default desktop viewport for dashboard, repositories/repository detail, plan review, agent runs, run trace, pull requests, security, evaluations, and settings; passed at 390x844 mobile viewport for the dashboard after the responsive shell fix.
- Release GIF evidence: generated local plan-to-PR and governance visual-flow GIFs from the captured operator-console screenshots.

### Known Limitations

- Real GitHub App write readiness is not production-proven until the user supplies credentials and a disposable demo repository for branch/commit/draft-PR smoke testing.
- Live model and live embedding quality are not production-proven until provider keys are supplied and provider-backed planning, patch-attempt, retrieval, and applied-patch evals run.
- Semgrep, dependency-audit, and CodeQL scanner paths are implemented locally, and the CodeQL workflow file is present. CI now uploads Semgrep/dependency-audit posture evidence, but release-grade CodeQL proof remains incomplete until a code-scanning-enabled repository produces SARIF/alert evidence.
- Artifact storage currently uses local filesystem-backed Docker volume storage; production object storage, retention policy, and signed artifact retrieval are pending deployment work.
- Full browser visual QA remains partially pending: core static screenshots and local visual-flow GIFs are captured, but live credentialed write/CI states still need release captures.
- Release deployment has a guide plus local runtime smoke evidence, but production-like cloud/VM deployment validation is still pending.
- No autonomous merge behavior is included or planned for v1.

### Upgrade Notes

- Alembic revision IDs were shortened to fit Alembic's default `version_num VARCHAR(32)` column. Local development databases stamped with the old pre-baseline head `0003_canonical_plan_run_link` should be restamped to `0003_plan_run_link` before running new Alembic commands, then upgraded through `0006_llm_trace_metadata`.
- `REPOPILOT_ARTIFACT_STORE_ROOT` and `REPOPILOT_ARTIFACT_INLINE_MAX_BYTES` control local artifact storage and large inline-output externalization.

### v1.0 Tag Gate

Tag `v1.0.0` only after credentialed GitHub smoke, provider-backed evals, live-state browser captures, deployment validation, and final source-boundary hygiene all pass.
