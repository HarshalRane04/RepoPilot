# RepoPilot AI Deployment Guide

RepoPilot v1 is designed as a single-tenant, self-hostable GitHub App. Start with Docker Compose for local demos, then move to a single VM or container host with managed Postgres/Redis when live credentials are introduced.

## Local Docker Compose

Required services:

- `api`: FastAPI application and migrations.
- `web`: Next.js operator console on `localhost:3001`.
- `worker`: Celery worker for webhook and run tasks.
- `beat`: Celery Beat scheduler for stale workspace cleanup.
- `postgres`: PostgreSQL with pgvector.
- `redis`: queue broker, result backend, and local cache.

Start:

```bash
POSTGRES_PASSWORD=<password> REDIS_PASSWORD=<password> GITHUB_WEBHOOK_SECRET=<secret> SESSION_SECRET_KEY=<secret> docker compose up -d --build
docker compose exec api alembic upgrade head
```

For local demos, use placeholder values from `.env.example`. For live or production-like deployments, load secrets from a restricted `.env` outside source control or a secret manager; avoid placing live secrets directly in shell commands where they can be captured by shell history, process listings, or terminal logs.

Health checks:

```bash
curl http://localhost:8000/health
curl http://localhost:3001/
docker compose ps
make source-boundary-manifest
make security-scanner-snapshot
make deployment-validate
make deployment-smoke
```

## Single-VM Deployment

1. Provision a VM with Docker, Docker Compose, enough disk for repository clones, and outbound HTTPS to GitHub/model providers.
2. Put RepoPilot behind TLS through a reverse proxy.
3. Route:
   - `https://<host>/webhooks/github` to API port `8000`.
   - `https://<host>/auth/github/callback` to API port `8000`.
   - `https://<host>/` or a dashboard subdomain to web port `3000` inside the container.
4. Store `.env` outside source control with restrictive permissions, or use a host secret manager for live values.
   Set `REPOPILOT_RELEASE_PROFILE=production` for release candidates so readiness blocks demo-only local-record and fallback paths.
5. Run `docker compose up -d --build`.
6. Run `docker compose exec api alembic upgrade head`.
7. Verify `/settings/readiness` before enabling writes.

## Managed Postgres And Redis

For production-like operation, prefer managed data services:

- Set `DATABASE_URL` and `ALEMBIC_DATABASE_URL` to the managed Postgres DSNs.
- Enable pgvector before migrations.
- Set `REDIS_URL`, `CELERY_BROKER_URL`, and `CELERY_RESULT_BACKEND` to managed Redis endpoints.
- Require TLS if the provider supports it.
- Keep queue/result databases separate if the provider supports logical Redis DBs or separate instances.

## Secrets

Never commit live secrets. Required runtime secrets include:

- `POSTGRES_PASSWORD`
- `REDIS_PASSWORD`
- `SESSION_SECRET_KEY`
- `GITHUB_WEBHOOK_SECRET`
- `GITHUB_APP_ID`
- `GITHUB_INSTALLATION_ID`
- `GITHUB_APP_PRIVATE_KEY` or `GITHUB_PRIVATE_KEY_PATH`
- `GITHUB_CLIENT_ID`
- `GITHUB_CLIENT_SECRET`
- `MODEL_API_KEY`
- `REPOPILOT_RUNTIME_SECRETS_KEY`

Keep `GITHUB_WRITES_ENABLED=false` until credential verification, demo-repo write smoke, validation gates, and security gates pass.
Keep `ALLOW_MODEL_FALLBACK=false` outside local development so provider outages or unsupported adapters fail closed instead of creating deterministic mock-like evidence.

## Storage And Cleanup

- Repository clones should live under `REPOPILOT_REPOSITORY_WORKSPACE_ROOT`.
- Run workspaces live under `/tmp/repopilot-agent-workspaces` in local Compose and are shared by API/worker/beat through the `agent_workspaces` volume.
- Startup cleanup and Celery Beat cleanup remove terminal or abandoned stale workspaces while skipping active run IDs.
- Web `node_modules` and `.next` are Docker named volumes in local development and should not be treated as source.
- The API/worker image installs Semgrep and pip-audit into an isolated `/opt/repopilot-security-tools` virtualenv, then exposes only the command shims on `PATH`. This keeps scanner dependencies from altering the API runtime dependency graph while making `SEMGREP_ENABLED=true` and `DEPENDENCY_AUDIT_ENABLED=true` meaningful runtime gates.

## Backups

Back up:

- Postgres database.
- Runtime secret store, if using saved encrypted GitHub/model credentials.
- Configuration `.env` or secret-manager entries.
- Release artifacts and eval reports under `Docs/`.

Do not back up transient run workspaces unless debugging an incident; they may contain generated code and redacted validation logs.

## Observability

- Configure `OTEL_EXPORTER_OTLP_ENDPOINT` for traces.
- Retain API, worker, beat, and web logs.
- Monitor queue depth, webhook failures, validation failures, scanner failures, model cost, and GitHub API rate limits.
- Keep LLM trace storage redacted and hash-backed.

## Rollback

1. Set `GITHUB_WRITES_ENABLED=false`.
2. Stop worker and beat if tasks are causing impact.
3. Revert to the previous container image.
4. Run Alembic downgrade only if the migration has an explicitly tested downgrade path.
5. Re-enable services after `/health`, `/settings/readiness`, and a local smoke test pass.

## Production Readiness Gate

Do not expose RepoPilot to non-demo repositories until:

- GitHub App credentials are verified.
- Draft PR smoke test passes on a disposable repository.
- Security scanners are configured or explicitly documented as disabled.
- Browser QA screenshots are captured.
- Eval report shows measured quality for the supported Python/TypeScript scope.
- Backup and rollback procedures have been tested.
- `make deployment-validate` passes and `Docs/release-artifacts/deployment-validation.md` is attached to the release evidence.
- `make deployment-smoke` passes against the local API and web endpoints, and `Docs/release-artifacts/deployment-runtime-smoke.md` is attached to the release evidence.
