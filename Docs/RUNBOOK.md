# RepoPilot AI Runbook

## Local Stack

Start:

```bash
make init-local-env
make up
```

Migrate:

```bash
make migrate
```

Verify the migration chain against a fresh temporary database:

```bash
make migration-verify
```

This creates a temporary PostgreSQL database, runs `upgrade head`, `downgrade base`, and `upgrade head`, then drops the temporary database.

Health checks:

- API: `curl http://localhost:8000/health`
- Web: `open http://localhost:3001`
- Postgres: `docker-compose exec postgres pg_isready -U repopilot -d repopilot`
- Redis: `docker-compose exec redis redis-cli ping`
- Production readiness: `curl http://localhost:8000/settings/readiness`
- State-machine contract: `curl http://localhost:8000/settings/state-machine`

The web service bind-mounts `apps/web` for local iteration and uses Docker named volumes for `node_modules` and `.next`. Docker Desktop may leave ignored ACL-protected mount-point directories at `apps/web/node_modules` and `apps/web/.next` while the service is running; treat them as runtime mount points, not source files.

Runtime secrets entered through the dashboard are encrypted under `.local/repopilot-secrets`, which Docker Compose bind-mounts to `/home/appuser/.repopilot` for `api`, `worker`, and `beat`. Keep this directory out of git; it is intentionally ignored and excluded from the Docker build context.

Local mode may use the managed Fernet key file generated under `.local/repopilot-secrets`. Non-local and release-candidate deployments must provide `REPOPILOT_RUNTIME_SECRETS_KEY` through the host secret manager so `/settings/readiness` does not treat the deployment as using a local-only key.

Build the sandbox image used by the default Docker backend:

```bash
make sandbox-image
```

## Artifact Storage

RepoPilot stores large or review-critical run evidence behind artifact pointers instead of keeping unbounded stdout, stderr, and patch text inline in database JSON fields.

Local defaults:

- `REPOPILOT_ARTIFACT_STORE_ROOT=/tmp/repopilot-artifacts`
- `REPOPILOT_ARTIFACT_INLINE_MAX_BYTES=12000`
- Docker Compose mounts the named volume `agent_artifacts` at `/tmp/repopilot-artifacts` for API, worker, and beat.

Artifact URIs use the local form:

```text
local://artifacts/<run-id>/<artifact-type>/<sha256-prefix>-<filename>
```

Stored records include artifact type, storage backend, storage key, URI, SHA-256, byte size, content type, and metadata. Current artifact-backed evidence includes patch diffs, validation command logs, and large tool outputs. Local artifact storage is object-store-ready by contract, but production deployments should replace or back the local filesystem path with durable object storage and define retention rules.

## Credential Placeholders

The repository includes `.env.example` with placeholders for GitHub App, OAuth, model, observability, and security-tool settings. Run `make init-local-env` to create a git-ignored `.env` with local-only Compose values. Local mode is expected to show readiness blockers until real values are provided.

Use `REPOPILOT_RELEASE_PROFILE=oss-demo` for local demos and `REPOPILOT_RELEASE_PROFILE=production` for release candidates. Production profile turns local-record GitHub write mode into a readiness blocker. Keep `ALLOW_MODEL_FALLBACK=false` outside local development so live-provider failures fail closed.

Use `Docs/CREDENTIAL_HANDOFF.md` when you are ready to collect live GitHub/model inputs and run the credentialed smoke sequence.

Do not set `GITHUB_WRITES_ENABLED=true` until all of these are configured for a demo repository:

- `GITHUB_WEBHOOK_SECRET`
- `GITHUB_APP_ID`
- `GITHUB_INSTALLATION_ID`
- `GITHUB_APP_PRIVATE_KEY` or `GITHUB_PRIVATE_KEY_PATH`
- `GITHUB_CLIENT_ID`
- `GITHUB_CLIENT_SECRET`
- `GITHUB_OAUTH_CALLBACK_URL`
- `WEB_APP_URL`
- `SESSION_SECRET_KEY`
- `MODEL_PROVIDER`, `MODEL_NAME`, and `MODEL_API_KEY`

Readiness modes to check before live operation:

- `github_mode=credentials_unverified`: credentials are present but installation-token verification has not passed.
- `github_mode=read_only_verified`: installation-token verification passed and read-only GitHub operations can be smoke tested.
- `github_mode=write_enabled_unverified`: write mode is enabled without branch/commit/draft-PR smoke evidence.
- `github_mode=write_enabled_verified`: write mode has a smoke verification marker.
- `model_mode=mock_model`: deterministic local model mode.
- `model_mode=live_model_unverified`: provider key is configured but provider verification has not passed.
- `model_mode=live_model_verified`: provider verification passed for the configured provider/model.
- `Runtime secret key` integration mode `managed_file_key_nonlocal`: a non-local deployment is still relying on the local managed key file and must set `REPOPILOT_RUNTIME_SECRETS_KEY`.
- `Model fallback policy` integration mode `fallback_enabled_nonlocal`: deterministic fallback is enabled outside local mode and must be disabled before production claims.

## Webhook Smoke Test

Create a signed local issue payload:

```bash
BODY='{"action":"opened","installation":{"id":123},"repository":{"name":"demo","default_branch":"main","owner":{"login":"octo"}},"issue":{"number":1,"title":"Fix empty repo dashboard crash","body":"The dashboard crashes on a fresh install. Steps to reproduce: open it with no repositories.","html_url":"https://github.com/octo/demo/issues/1"},"sender":{"login":"alice"}}'
SIG=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac 'change-me-local-dev' | sed 's/^.* //')
curl -X POST http://localhost:8000/webhooks/github \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: issues" \
  -H "X-GitHub-Delivery: local-delivery-1" \
  -H "X-Hub-Signature-256: sha256=$SIG" \
  --data "$BODY"
```

Then inspect:

- `curl http://localhost:8000/webhooks/events`
- `curl http://localhost:8000/repos`
- `curl http://localhost:8000/metrics/overview`
- `curl http://localhost:8000/activity`

## GitHub Command And CI Event Smoke Shapes

Issue comments beginning with `/repopilot` are normalized and audited. Permission checks use the credentialed GitHub client to inspect the sender's repository role when GitHub App credentials are configured; otherwise commands fail closed or remain local-demo only.

Supported command shapes:

```text
/repopilot approve
/repopilot reject
/repopilot revise <instructions>
/repopilot stop
```

`workflow_run` events with a linked pull request are normalized into CI evidence and routed through the same analyzer as `/prs/{pr_id}/ci`.

Redis/Celery dispatch is enabled by default. If you are running only the API process without Redis for a quick route test, set `ENABLE_QUEUE_DISPATCH=false`; the full local stack should use Redis.

If Redis or the worker is unavailable while queue dispatch is enabled, the API stores the event and marks it `enqueue_failed` so the failure is visible through `/webhooks/events`.

## Workspace Cleanup

RepoPilot keeps generated patches inside isolated run workspaces mounted at `/tmp/repopilot-agent-workspaces`. The API performs a startup cleanup, and the local Compose stack also runs a Celery Beat scheduler that periodically dispatches `repopilot.workspace.cleanup`.

Tune cleanup with:

- `WORKSPACE_CLEANUP_MAX_AGE_SECONDS`: default `86400`.
- `WORKSPACE_CLEANUP_INTERVAL_SECONDS`: default `3600`.

The cleanup task queries non-terminal agent runs and skips their workspace IDs. Terminal or abandoned workspaces older than the configured age are removed from the shared `agent_workspaces` Docker volume.

## CodeQL SARIF Ingestion

RepoPilot does not run arbitrary CodeQL shell commands inside agent workspaces. Instead, it exposes a guarded SARIF ingestion path for CodeQL output produced by CI.

Check the recommended workflow:

```bash
curl http://localhost:8000/security/codeql/recommendation \
  -H "X-RepoPilot-User: local-owner" \
  -H "X-RepoPilot-Role: owner"
```

Ingest CodeQL SARIF for a run after enabling `CODEQL_ENABLED=true`:

```bash
curl -X POST "http://localhost:8000/security/runs/$RUN_ID/codeql/sarif" \
  -H "X-RepoPilot-User: local-owner" \
  -H "X-RepoPilot-Role: owner" \
  -H "Content-Type: application/json" \
  --data @codeql-sarif-request.json
```

The request shape is:

```json
{
  "source": "github-codeql",
  "fail_on_findings": true,
  "sarif": {
    "version": "2.1.0",
    "runs": []
  }
}
```

High and critical CodeQL findings are persisted as `codeql` security findings and can block draft PR creation while open.

When GitHub App credentials are configured, RepoPilot can also fetch open CodeQL code-scanning alerts for the linked repository and ingest them into the same security-finding lifecycle:

```bash
curl -X POST "http://localhost:8000/security/runs/$RUN_ID/codeql/alerts/fetch" \
  -H "X-RepoPilot-User: local-owner" \
  -H "X-RepoPilot-Role: owner" \
  -H "Content-Type: application/json" \
  --data '{"state":"open","tool_name":"CodeQL","per_page":100,"fail_on_findings":true}'
```

This path is credential-gated through the GitHub App installation token and remains skipped while `CODEQL_ENABLED=false`.

## Phase 5-13 Smoke Test

Index a local checkout for the repository discovered from the webhook:

```bash
REPO_ID=$(curl -s http://localhost:8000/repos | jq -r '.[0].id')
curl -X POST "http://localhost:8000/repos/$REPO_ID/index" \
  -H "Content-Type: application/json" \
  --data "{\"source_path\":\"$PWD\"}"
```

Retrieve a cited context pack:

```bash
curl "http://localhost:8000/repos/$REPO_ID/context?query=dashboard%20crash"
```

Generate and approve a plan:

```bash
ISSUE_ID=$(curl -s "http://localhost:8000/repos/$REPO_ID/issues" | jq -r '.issues[0].id')
PLAN_RESPONSE=$(curl -s -X POST "http://localhost:8000/issues/$ISSUE_ID/plan")
PLAN_ID=$(printf '%s' "$PLAN_RESPONSE" | jq -r '.plan_id')
RUN_ID=$(printf '%s' "$PLAN_RESPONSE" | jq -r '.run_id')

curl -X POST "http://localhost:8000/plans/$PLAN_ID/approve" \
  -H "X-RepoPilot-User: local-owner" \
  -H "X-RepoPilot-Role: owner"
```

Start the approved run and execute an allowlisted sandbox command:

```bash
curl -X POST "http://localhost:8000/runs/$RUN_ID/start"
curl -X POST "http://localhost:8000/runs/$RUN_ID/sandbox" \
  -H "Content-Type: application/json" \
  --data "{\"workspace_path\":\"$PWD\",\"command\":\"pytest\",\"timeout_seconds\":120}"
```

The sandbox route blocks unapproved runs and non-allowlisted commands. With `SANDBOX_BACKEND=docker`, Docker must be reachable and the `repopilot-sandbox:local` image must exist.
`/runs/{run_id}/start` also records a guarded transition to `CREATE_BRANCH`; invalid state skips are rejected by the state-machine guard.

Execute the Phase 9 implementation/test lane against an approved run:

```bash
curl -X POST "http://localhost:8000/runs/$RUN_ID/implement" \
  -H "Content-Type: application/json" \
  --data "{\"workspace_path\":\"$PWD/apps/api\",\"validation_command\":\"pytest\",\"timeout_seconds\":120,\"max_changed_files\":5}"
```

The implementation lane copies the workspace into `/tmp/repopilot-agent-workspaces/$RUN_ID`, writes a generated pytest evidence file in that copy, runs the allowlisted validation command through the sandbox runner, and stores the patch hash plus validation result on the run. It does not mutate the source checkout.

Run the remaining release gates:

```bash
curl -X POST "http://localhost:8000/runs/$RUN_ID/security-scan" \
  -H "Content-Type: application/json" \
  --data '{"fail_on_findings":true}'

PR_RESPONSE=$(curl -s -X POST "http://localhost:8000/runs/$RUN_ID/open-draft-pr" \
  -H "Content-Type: application/json" \
  --data '{"branch_prefix":"repopilot"}')
PR_ID=$(printf '%s' "$PR_RESPONSE" | jq -r '.pr_id')

curl -X POST "http://localhost:8000/prs/$PR_ID/ci" \
  -H "Content-Type: application/json" \
  --data '{"workflow_name":"local-ci","conclusion":"success","log_text":"all checks passed"}'

curl "http://localhost:8000/prs/$PR_ID/summary"
curl "http://localhost:8000/runs/$RUN_ID/trace"
curl -X POST "http://localhost:8000/evals/run" \
  -H "Content-Type: application/json" \
  --data '{"benchmark_version":"v1-local","task_count":30,"model_config":{"provider":"mock"}}'
curl "http://localhost:8000/evals/reports"
```

The draft PR route creates a local branch/PR database record and a GitHub-shaped URL while `GITHUB_WRITES_ENABLED=false`. It does not push a branch, commit, comment, label, or pull request to GitHub until credentials are configured and write mode is enabled.

## Common Issues

- If API startup fails with database connection errors, confirm Postgres is healthy and `.env` matches Docker service names.
- If migrations fail on `vector`, confirm the `pgvector/pgvector:pg16` image is running.
- If the dashboard cannot reach the API, confirm `NEXT_PUBLIC_API_URL=http://localhost:8000` for browser access.
- If sandbox validation returns `Sandbox backend executable not found: docker`, install/start Docker or set `SANDBOX_BACKEND=local` only for a controlled development test.
- If sandbox validation exits before running tests, rebuild the image with `make sandbox-image`.
