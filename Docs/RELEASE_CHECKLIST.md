# RepoPilot AI v1.0 Release Checklist

RepoPilot v1.0 is release-ready only when local controls, credentialed GitHub proof, model/eval proof, browser QA, and deployment documentation are all complete.

## Required Local Evidence

- Docker Compose starts API, web, worker, beat, Postgres, and Redis.
- Migrations apply cleanly from a fresh database.
- API health returns `status=ok`.
- Dashboard loads at `http://localhost:3001`.
- Webhook delivery is verified, deduped, stored, queued, and processed.
- Repository indexing returns cited context and skips secret-like files.
- Issue planning stops at human approval.
- Approved runs execute implementation in isolated workspaces.
- Validation evidence, security findings, PR evidence, run trace, and audit records are persisted.
- Patch diffs, validation logs, and large tool outputs are artifact-backed with `ArtifactRecord` metadata instead of unbounded inline blobs.
- Security finding lifecycle actions require review reasons.
- CI failure can create a fresh waiting revision plan.
- Fixture-backed eval report contains at least 20 tasks with per-task outcomes plus observed plan-quality, context-precision, patch-quality, human-edit-distance, and provider-comparison gate status. The local baseline lives at `Docs/eval-reports/v1-local-latest.md` and can be regenerated with `make eval-report`.
- Source-boundary manifest is generated with `make source-boundary-manifest`; the latest manifest lives at `Docs/release-artifacts/source-boundary-manifest.md`.
- Credential readiness snapshot is generated with `make readiness-snapshot`; the latest snapshot lives at `Docs/release-artifacts/credential-readiness-snapshot.md`.
- Security scanner posture snapshot is generated with `make security-scanner-snapshot`; the latest snapshot lives at `Docs/release-artifacts/security-scanner-snapshot.md`.
- Source-boundary hygiene report is generated with `make release-hygiene`; the latest report lives at `Docs/release-artifacts/source-boundary-hygiene.md`.
- Release GIF evidence is generated with `make release-gifs`; the latest manifest lives at `Docs/release-artifacts/release-gifs.md`.
- Deployment validation report is generated with `make deployment-validate`; the latest report lives at `Docs/release-artifacts/deployment-validation.md`.
- Local runtime deployment smoke report is generated with `make deployment-smoke`; the latest report lives at `Docs/release-artifacts/deployment-runtime-smoke.md`.

## Required Credentialed Evidence

- GitHub App installation-token verification succeeds.
- Live credential collection follows `Docs/CREDENTIAL_HANDOFF.md`.
- Repository sync uses a real installation.
- `/repopilot status` and `/repopilot approve` enforce collaborator permissions.
- A disposable demo issue produces a real branch, commit, and draft PR.
- `GITHUB_WRITES_ENABLED=false` blocks the same write path.
- CodeQL alert fetch is proven against a repository with code-scanning enabled.
- Live model provider verification succeeds without storing raw secrets.
- Provider-backed triage/planning/retrieval/patch eval metrics are recorded, including observed plan-quality pass rate, context precision, observed patch-quality pass rate, human edit distance, provider/model ranking, cost, and latency. The planning-only provider harness can be run with `make provider-planning-eval`, but patch/retrieval/live-CI proof still needs separate evidence.

## Required Browser Evidence

- Current local static evidence is captured under `Docs/release-artifacts/` for dashboard desktop/mobile, plan review, agent runs, run trace, pull requests, security, evaluations, and settings.
- Current local GIF evidence is captured under `Docs/release-artifacts/` for the plan-to-PR and governance visual flows; continue collecting credentialed live-state captures after GitHub/model verification.
- Desktop screenshot of dashboard overview.
- Desktop screenshot of plan review and run trace.
- Desktop screenshot of security/eval surfaces.
- Mobile screenshot of primary navigation and run detail.
- No text overflow, incoherent overlap, or false production-ready labels.

## Verification Commands

```bash
PYTHONPYCACHEPREFIX=/private/tmp/repopilot-pycache python3 -m compileall apps/api/app packages/shared_contracts/repopilot_contracts apps/api/alembic/versions packages/evals/repopilot_evals packages/policy_engine/repopilot_policy_engine packages/llm_client/repopilot_llm_client packages/github_client/repopilot_github_client
PYTHONPYCACHEPREFIX=/private/tmp/repopilot-pycache python3 -m pytest apps/api/tests
POSTGRES_PASSWORD=placeholder REDIS_PASSWORD=placeholder GITHUB_WEBHOOK_SECRET=change-me-local-dev SESSION_SECRET_KEY=placeholder DEV_HEADER_AUTH_ENABLED=true make migration-verify
docker exec repopilot-web-1 sh -lc 'npm run typecheck'
docker exec repopilot-web-1 sh -lc 'npm run build'
docker compose config --quiet
curl -sS --max-time 8 http://127.0.0.1:8000/health
curl -sS --max-time 8 http://127.0.0.1:3001/
make source-boundary-manifest
make readiness-snapshot
make security-scanner-snapshot
make release-hygiene
make release-gifs
make deployment-validate
make deployment-smoke
```

## Hygiene Gates

- No `.secrets`, `.DS_Store`, `.pytest_cache`, `__pycache__`, `*.egg-info`, or `tsconfig.tsbuildinfo` files remain after cleanup.
- `make release-hygiene` reports no failed findings before final packaging.
- `make deployment-validate` reports no failed findings before release packaging.
- `apps/web/node_modules` and `apps/web/.next` may appear while the web service is running; they must be ignored Docker mount points backed by named volumes.
- `.dockerignore` excludes local secrets, generated web artifacts, dependency folders, docs/images, and local tool artifacts.
- Local `agent_artifacts` storage is either intentionally retained for review or governed by a documented cleanup/retention step before release packaging.
- `README 2.md` removal is recorded in `Docs/SOURCE_BOUNDARY_DECISIONS.md`; no stale duplicate README remains in the source boundary.
- A deliberate baseline commit exists before the v1.0 tag.

## Release Claims

- No autonomous merges.
- No source checkout mutation during generated patch execution.
- No real GitHub writes unless write mode, credentials, permission checks, approved plan hash, validation evidence, and clean blocking-security gates are present.
- Draft PR summaries are evidence-backed and contain no invented validation/security claims.
- Every state transition, tool call, write, validation result, security finding, PR record, LLM trace, and eval report is auditable.

## Tag Gate

Tag `v1.0.0` only after all local evidence, credentialed evidence, browser evidence, and hygiene gates pass.
