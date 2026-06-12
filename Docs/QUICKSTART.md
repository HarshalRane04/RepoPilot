# RepoPilot Self-Hosted Quickstart

This quickstart is for the open-source, single-tenant, self-hosted RepoPilot path.

RepoPilot is safe-by-default: local mode can run without live GitHub writes or live model keys. Real GitHub branch/commit/PR writes stay disabled until credentials, model verification, approval, validation, security, and permission gates are proven.

## Prerequisites

- Docker Desktop or a compatible Docker daemon.
- Git.
- `make`.
- `curl`, for local health/readiness smoke checks.
- `jq` and `openssl`, when running the manual webhook smoke commands in `Docs/RUNBOOK.md`.
- `uv`, when running host-side eval/provider/developer targets.
- Python 3.12 if running helper scripts outside containers.
- Node.js 22 if running the web app outside containers.
- A disposable GitHub repository for live smoke tests.
- A model-provider key for live AI behavior.

## 1. Clone And Configure Local Defaults

```bash
git clone https://github.com/HarshalRane04/RepoPilot.git
cd RepoPilot
make start-local
```

`make start-local` creates `.env` from `.env.example`, fills only local-safe Compose values, builds/starts the Docker Compose stack, applies migrations, and builds the sandbox image used for isolated validation. It keeps `GITHUB_WRITES_ENABLED=false`, enables local header auth for the dashboard, and leaves live GitHub/model credentials blank. Edit `.env` only for local service wiring, callback URLs, feature toggles, and local-only placeholder passwords. Treat real database, Redis, webhook, session, OAuth, GitHub App, and model values as secrets. Do not commit `.env`.

Keep `REPOPILOT_RELEASE_PROFILE=oss-demo` for local portfolio demos. Switch to `REPOPILOT_RELEASE_PROFILE=production` only when preparing a credentialed release candidate; production profile blocks local-record GitHub write mode, managed-file runtime encryption keys, and non-local model fallback from being reported as ready.

For live GitHub/model credentials, use the dashboard Settings screen or the encrypted runtime secret helper:

```bash
make configure-runtime-secrets
```

The local encrypted store is `.local/repopilot-secrets/`, which is git-ignored and bind-mounted into the API, worker, and beat containers.

For non-local deployments, set `REPOPILOT_RUNTIME_SECRETS_KEY` through the host secret manager. The managed key file is intended for local development only.

## 2. Manual Local Stack Fallback

If you need to run the source-build steps one at a time:

```bash
make init-local-env
make up
make migrate
make sandbox-image
```

For published GHCR images, set `REPOPILOT_IMAGE_TAG` in `.env` to a release tag such as `v1.0.0`, `latest`, or a digest-pinned override through `REPOPILOT_API_IMAGE`/`REPOPILOT_WEB_IMAGE`/`REPOPILOT_SANDBOX_IMAGE`, then run:

```bash
make ghcr-pull
make ghcr-up
make ghcr-migrate
```

The GHCR path uses `docker-compose.ghcr.yml` and does not bind-mount local source into API, worker, beat, or web containers.

Keep the GHCR path marked release-candidate until a fresh-host smoke proves the published images are public and runnable.

Open:

- Dashboard: `http://localhost:3001`
- API health: `http://localhost:8000/health`
- API docs: `http://localhost:8000/docs`

Local prompt/demo mode does not require live GitHub writes. Use the dashboard Prompt view to submit a prompt, create a local tracked issue/run, review the generated plan, approve it, execute sandbox validation, and inspect the local PR record. Real GitHub branches and draft PRs stay disabled until the Settings readiness checks and write smoke are proven.

## 3. Check Local Readiness

```bash
make readiness-snapshot
make credential-smoke
make deployment-validate
```

In a fresh local checkout, credential smoke is expected to be `blocked` until GitHub/model credentials are saved. That is not a failure for local development; it is a release blocker for production claims.

## 4. Configure GitHub App And Model Provider

Follow `Docs/GITHUB_APP_SETUP.md` and `Docs/CREDENTIAL_HANDOFF.md`.

Minimum live smoke inputs:

- GitHub App ID.
- GitHub App private key or private key path.
- GitHub installation ID.
- GitHub webhook secret.
- GitHub OAuth client ID and secret.
- Session secret key.
- Model provider, model name, and provider API key.

Save those values through Settings or `make configure-runtime-secrets`, not by committing source changes.

Live model and embedding modes are explicit opt-in data-transfer boundaries. Keep `EMBEDDING_SOURCE_TRANSFER_ENABLED=false` unless the repository owner approves sending repository file paths and selected source/documentation chunks to the configured embedding provider. Live planning/model calls may also send issue text, selected repository context, prompts, model outputs, and CI/security evidence summaries to the configured provider.

## 5. Run Live Smoke In Safe Order

Keep `GITHUB_WRITES_ENABLED=false` first.

```bash
make credential-smoke-strict
```

Then verify:

1. GitHub OAuth/session readiness.
2. GitHub App installation-token readiness.
3. Model provider readiness.
4. Repository sync from the installation.
5. Signed issue webhook delivery.
6. `/repopilot status` permission behavior from a real collaborator.

Only after read-only checks pass, enable write mode for a disposable demo repository and run one low-risk issue through:

```text
issue -> triage -> retrieve context -> generate plan -> human approval -> implement in sandbox -> validate -> security scan -> draft PR
```

Turn write mode back off after the smoke test unless continuing controlled validation.

Keep `ALLOW_MODEL_FALLBACK=false` outside local development. Local mode can use deterministic fallback for repeatable tests, but production should fail closed when a live provider is missing, unreachable, or unsupported.

## 6. Release Verification

Use local developer targets while credentials are absent:

```bash
make source-boundary-manifest
make release-hygiene
make security-scanner-snapshot
make deployment-smoke
```

Use the strict release gate only after credentials and runtime services are ready:

```bash
make release-verify
```

`make release-verify` is supposed to fail if credential smoke is blocked, runtime smoke fails, hygiene has warnings/failures, or scanner blockers remain.

## Current Limits

- The default model mode is deterministic mock behavior.
- Real GitHub writes require explicit write mode and verified credentials.
- CodeQL proof depends on public code scanning or private GitHub Advanced Security/code-scanning setup.
- Local artifacts are filesystem-backed; production deployments should define retention and backup policy.
- RepoPilot never autonomously merges PRs.
