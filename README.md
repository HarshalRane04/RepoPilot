# RepoPilot AI

RepoPilot AI is a local-first, single-tenant GitHub App control plane and operator console for human-approved issue triage, planning, validation evidence, security checks, and gated draft PR workflows.

The current codebase contains a strong local control plane, but the full AI coding loop is still under active implementation. See [Docs/IMPROVEMENT_PLAN.md](Docs/IMPROVEMENT_PLAN.md) for the safety-first roadmap from the current MVP to a production-grade LLM-powered PR agent.

## Current Implementation Status

Implemented today:

- FastAPI backend with protected API routes, health checks, and OpenAPI docs.
- PostgreSQL + pgvector schema through Alembic.
- Redis + Celery worker plumbing.
- Shared Pydantic contracts for issues, plans, runs, tools, validation, security, PRs, traces, readiness, and evals.
- GitHub webhook HMAC verification, delivery dedupe, event storage, normalization, audit events, and queue dispatch.
- GitHub OAuth login that imports the authenticated user's repositories.
- Repository indexing for server-managed local source paths, with gateway-mediated deterministic embeddings, embedding metadata, and stale-index detection.
- Deterministic issue triage with model-gateway structured-output attempts, confidence scores, and prompt-injection prechecks.
- Deterministic implementation planning from retrieved citations, with planning structured-output attempts routed through the mock-first `ModelGateway`.
- Human approval, rejection, and revision gates for implementation plans, with approved-plan hash enforcement before write/implementation/PR actions.
- Mock-first model gateway for completions, structured JSON validation, deterministic embeddings, budget checks, prompt/response hashes, and LLM trace rows.
- Deny-by-default policy checks for risky files and commands.
- Docker-first sandbox validation runner with scrubbed environment, no network, resource limits, and local backend only for local development.
- Model-facing `ToolRegistry` and `ToolExecutor` boundary for audited tool calls.
- Executor-mediated implementation lane that asks the model for bounded workspace tool calls, applies writes only through `ToolExecutor`, captures a diff hash, and validates inside the isolated run workspace.
- Security scanner for generated patches and workspaces, plus finding lifecycle updates with reasoned acknowledgement/fixed/false-positive states.
- Local draft PR records after approval, validation, and security checks, with real GitHub branch/commit/PR writer plumbing behind write-mode readiness gates.
- CI analyzer for workflow/check events, failure-log summaries, and fresh revision-plan creation after CI failure.
- Observability endpoints for run traces, audit logs, metrics, readiness, and eval reports.
- Fixture-backed local eval runner with 31 benchmark tasks, per-task outcomes, category pass rates, observed plan-quality/context-precision/patch-quality/human-edit-distance/provider-comparison scoring, and release quality gates.
- Local Markdown/JSON eval report generation with `make eval-report`; the latest baseline is in `Docs/eval-reports/`.
- Planning-only live-provider eval harness with `make provider-planning-eval`, using provider keys from the shell environment rather than source files.
- Manual GitHub Actions provider-planning workflow for credentialed model tests with secret-name inputs and downloadable eval artifacts.
- Source-boundary manifest generation with `make source-boundary-manifest`; the latest manifest is in `Docs/release-artifacts/`.
- Redacted credential readiness snapshot generation with `make readiness-snapshot`; the latest snapshot is in `Docs/release-artifacts/`.
- Security scanner posture snapshot generation with `make security-scanner-snapshot`; the latest snapshot is in `Docs/release-artifacts/`.
- Source-boundary hygiene report generation with `make release-hygiene`; the latest report is in `Docs/release-artifacts/`.
- Deployment topology/docs validation with `make deployment-validate`; the latest report is in `Docs/release-artifacts/`.
- Local runtime deployment smoke with `make deployment-smoke`; the latest report is in `Docs/release-artifacts/`.
- Next.js operator dashboard for repositories, issues, runs, PRs, security finding lifecycle actions, CI revision plans, evals, audit logs, and settings.

Not production-complete yet:

- Live-provider quality validation for LLM triage, planning reasoning, and code generation.
- Provider-backed embeddings.
- End-to-end smoke test against a real GitHub demo repository with user-provided GitHub App credentials.
- Full live GitHub Actions archive parsing and credentialed provider-backed plan/patch-quality/human-edit-distance comparisons.
- Production deployment packaging.

## Safety Model

RepoPilot is designed around these invariants:

- No autonomous merges.
- No code changes before a human-approved plan.
- No raw model access to arbitrary Python functions or arbitrary shell.
- Model actions must pass through `ToolExecutor` or an equivalent audited executor boundary.
- Generated code is applied only inside isolated run workspaces.
- GitHub writes stay disabled unless credentials, write mode, validation evidence, security gates, and permission checks are all satisfied.
- Live model and embedding calls are explicit data-transfer boundaries. Keep `EMBEDDING_SOURCE_TRANSFER_ENABLED=false` unless the repository owner approves sending repository paths and selected source/context chunks to the configured embedding provider.
- Every state transition, tool call, write action, validation result, security finding, and PR action is audited.

## Local Start

For a step-by-step self-hosted install path, use [Docs/QUICKSTART.md](Docs/QUICKSTART.md). The short path is:

Prerequisites and common first-run gotchas:

- Install Docker Desktop or another Docker daemon, and make sure it is running before `make start-local`.
- Install `make`, Git, and a POSIX shell. The local bootstrap scripts generate `.env` values, then Docker Compose builds API/web images from source.
- The first run can take several minutes because it builds containers, applies migrations, and builds the sandbox image.
- If Docker Compose reports missing `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `GITHUB_WEBHOOK_SECRET`, or `SESSION_SECRET_KEY`, run `make init-local-env` before starting Compose.
- `make init-local-env` enables local header-based dev auth for the dashboard/API so a fresh clone is usable without OAuth. Do not use that local auth posture as a production deployment setting.
- Real GitHub, OAuth, scanner, and model-provider values should be saved through dashboard Settings or `make configure-runtime-secrets`, not committed to source.

1. Clone the repo and start the local stack:

   ```bash
   git clone https://github.com/HarshalRane04/RepoPilot.git
   cd RepoPilot
   make start-local
   ```

   This runs `make init-local-env`, builds/starts Docker Compose, applies migrations, and builds the sandbox image. The generated `.env` uses git-ignored local-only values for Compose startup, keeps real GitHub/model credentials blank, and leaves `GITHUB_WRITES_ENABLED=false`. Treat real database, Redis, webhook, session, OAuth, GitHub App, and model values as secrets. For a credentialed GitHub App smoke test, save `GITHUB_APP_ID`, `GITHUB_INSTALLATION_ID`, `GITHUB_APP_PRIVATE_KEY` or `GITHUB_PRIVATE_KEY_PATH`, OAuth credentials, and model-provider keys through the dashboard Settings screen or `make configure-runtime-secrets`. Keep `GITHUB_WRITES_ENABLED=false` until `/settings/readiness` reports `github_mode=read_only_verified` and a disposable demo repository has passed the write smoke test.

2. Open:

   - API health: http://localhost:8000/health
   - API docs: http://localhost:8000/docs
   - Dashboard: http://localhost:3001

Manual source-build fallback:

```bash
make init-local-env
make up
make migrate
make sandbox-image
```

To run published containers instead of source-building API/web images, set `REPOPILOT_IMAGE_TAG` in `.env` and use the GHCR targets:

```bash
make ghcr-pull
make ghcr-up
make ghcr-migrate
```

The released-image path uses `docker-compose.ghcr.yml` and pulls `ghcr.io/harshalrane04/repopilot-api`, `ghcr.io/harshalrane04/repopilot-web`, and `ghcr.io/harshalrane04/repopilot-sandbox`. Keep this path marked release-candidate until a fresh-host GHCR smoke proves the published images are public and runnable.

## Common Checks

```bash
docker compose config
make api-test
make web-typecheck
make sandbox-image
make eval-report
make provider-planning-eval
make source-boundary-manifest
make readiness-snapshot
make security-scanner-snapshot
make release-hygiene
make deployment-validate
make deployment-smoke
```

After live credentials and runtime services are configured, the strict release gate is:

```bash
make release-verify
```

For live model testing from GitHub, add the provider key as a repository secret and run the manual **Provider Planning Eval** workflow. See [Docs/MODEL_TESTING.md](Docs/MODEL_TESTING.md).

## API Highlights

- `POST /webhooks/github`: verifies GitHub webhook signatures, dedupes deliveries, stores payloads, audits receipt, and queues processing.
- `GET /auth/session`: returns the signed session identity.
- `GET /auth/github/login`: starts GitHub OAuth when configured.
- `GET /auth/github/callback`: validates OAuth state, imports repositories, and creates a session cookie.
- `GET /repos`: lists tracked repositories.
- `POST /repos/{repo_id}/index`: indexes a server-managed local repository source path.
- `GET /repos/{repo_id}/context`: retrieves cited context chunks.
- `POST /issues/{issue_id}/triage`: reruns deterministic triage.
- `POST /issues/{issue_id}/plan`: generates a deterministic cited plan and waits for approval.
- `POST /plans/{plan_id}/approve`: approves allowed plans and enforces escalation checks.
- `POST /runs/{run_id}/implement`: creates an isolated workspace, executes model-proposed write tools through `ToolExecutor`, validates, and records patch evidence.
- `POST /runs/{run_id}/security-scan`: scans generated evidence for secrets, risky paths, and prompt-injection phrases.
- `POST /runs/{run_id}/open-draft-pr`: creates a local draft PR record after gates pass.
- `GET /runs/{run_id}/trace`: returns an auditable trace across steps, validation, security, PRs, audits, and LLM metadata.
- `POST /prs/{pr_id}/ci`: stores a CI conclusion and promotes clean runs when evidence passes.
- `POST /prs/{pr_id}/revision-plan`: creates a fresh waiting plan from CI failure evidence.
- `PATCH /security/findings/{finding_id}/status`: updates finding lifecycle state with required review reasons for acknowledgement and false-positive decisions.
- `POST /evals/run`: runs the local fixture-backed benchmark scorer and stores per-task outcomes plus optional observed plan/patch-quality and provider-comparison evidence from `model_config`.
- `GET /settings/readiness`: shows production-readiness blockers for GitHub, OAuth, model, security, and observability integrations.

## Roadmap

The active implementation roadmap is:

```text
hygiene -> safety envelope -> model gateway -> semantic planning -> human review -> executor-mediated patching -> validation/security -> GitHub writes -> CI/evals/release
```

The next major milestones are a real GitHub demo-repo smoke test with user-provided credentials, provider-backed embedding/model validation, and deployment packaging from [Docs/IMPROVEMENT_PLAN.md](Docs/IMPROVEMENT_PLAN.md).
