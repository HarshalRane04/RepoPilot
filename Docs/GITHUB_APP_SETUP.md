# GitHub App Setup

This guide configures RepoPilot AI as a local development GitHub App for the current Phases 2-13 workflow.

## Create The App

1. Open GitHub Developer Settings and create a new GitHub App.
2. Set the webhook URL to your public tunnel URL plus `/webhooks/github`.
   - Local example with a tunnel: `https://<your-tunnel>/webhooks/github`
3. Set the webhook secret to the same value as `GITHUB_WEBHOOK_SECRET`.
4. Generate and download a private key for GitHub App token signing.
5. Create an OAuth App or configure the GitHub App's user authorization callback for dashboard login.

## Minimum Local Permissions

Repository permissions:

- Issues: read/write, for receiving issue events and later adding labels/comments.
- Metadata: read, required by GitHub Apps.
- Pull requests: read, used for PR views and future write-backed draft PR creation.
- Contents: read, reserved for later indexing.
- Checks: read, reserved for later CI status ingestion.
- Actions: read, for workflow run and log ingestion.

Subscribe to events:

- Issues
- Issue comments
- Pull request
- Workflow run

`issues`, RepoPilot `issue_comment` commands, and PR-linked `workflow_run` events are actively normalized. Other event types are safe to receive because unsupported events are stored and marked ignored by the worker.

## Local Environment And Runtime Secrets

Use `.env` for local service wiring and non-secret defaults. Store live GitHub, OAuth, model, and session secrets through the dashboard Settings screen or RepoPilot's encrypted runtime secret store. Do not commit live credentials and do not paste them into public issues, PR comments, screenshots, or logs.

For local Compose, the encrypted store lives under `.local/repopilot-secrets/` and is mounted into the API, worker, and beat containers at `/home/appuser/.repopilot`. The helper below prompts with hidden input for secret values and writes encrypted values locally:

```bash
make configure-runtime-secrets
```

The dashboard Settings screen writes to the same store. Use GitHub Actions repository secrets only for GitHub-hosted workflows that need provider keys, such as provider eval workflows.

Set only local placeholders and non-secret toggles in `.env` if you are not using the defaults. The following values are local-only placeholders and must not be used for live smoke tests or production-like deployments:

```bash
GITHUB_WEBHOOK_SECRET=change-me-local-dev
GITHUB_OAUTH_CALLBACK_URL=http://localhost:8000/auth/github/callback
WEB_APP_URL=http://localhost:3001
SESSION_SECRET_KEY=change-me-session-secret
MODEL_PROVIDER=mock
MODEL_NAME=mock-planner
MODEL_API_KEY=
GITHUB_WRITES_ENABLED=false
ENABLE_QUEUE_DISPATCH=true
```

Save these values through Settings or `make configure-runtime-secrets` before live smoke tests:

- `GITHUB_APP_ID`
- `GITHUB_INSTALLATION_ID`
- `GITHUB_APP_PRIVATE_KEY` or `GITHUB_PRIVATE_KEY_PATH`
- `GITHUB_WEBHOOK_SECRET`
- `GITHUB_CLIENT_ID`
- `GITHUB_CLIENT_SECRET`
- `SESSION_SECRET_KEY`
- `MODEL_PROVIDER`
- `MODEL_NAME`
- `MODEL_API_KEY`

Check readiness:

```bash
curl http://localhost:8000/settings/readiness
```

The readiness response now reports `github_mode`:

- `missing_credentials`: GitHub App credentials are absent.
- `credentials_present_installation_missing`: app key material exists but no installation ID is configured.
- `credentials_unverified`: credentials and installation ID are present, but no installation-token verification has passed.
- `read_only_verified`: RepoPilot created an installation token successfully; read-only GitHub operations can be smoke tested.
- `write_enabled_unverified`: `GITHUB_WRITES_ENABLED=true` is set, but no branch/commit/draft-PR smoke marker exists.
- `write_enabled_verified`: write mode is enabled and a write-smoke verification marker exists.

Keep `GITHUB_WRITES_ENABLED=false` until `github_mode=read_only_verified` and you have tested the app on a disposable demo repository. Do not claim production write readiness until the branch/commit/draft-PR smoke test has succeeded.

Run the full stack:

```bash
docker-compose up --build
docker-compose exec api alembic upgrade head
```

After the stack is running, open `http://localhost:3001`, choose **Connect with GitHub**, and authorize the OAuth app. RepoPilot validates the signed state cookie, exchanges the OAuth code, reads `/user`, `/user/emails`, and `/user/repos`, then stores the discovered repositories in the local `installations` and `repositories` tables.

The API verifies GitHub signatures before storing events. The worker consumes event IDs from Redis/Celery and creates installation, repository, issue, agent run, agent step, and audit records.

## Expected Flow

1. A signed-in dashboard user chooses **Connect with GitHub**.
2. `GET /auth/github/login` sets a signed state cookie and returns the GitHub authorization URL.
3. GitHub redirects to `GET /auth/github/callback`, where RepoPilot validates state, exchanges the code, creates a session cookie, and imports the user's repositories.
4. GitHub sends an `issues` event.
5. `POST /webhooks/github` verifies `X-Hub-Signature-256`.
6. The API dedupes `X-GitHub-Delivery` and stores the raw event.
7. The API enqueues `repopilot.github.process_event` through Redis/Celery.
8. The worker normalizes the payload and upserts installation, repository, and issue records.
9. The deterministic triage service sets issue type, complexity, risk score, status, and acceptance criteria.
10. A local repository path is indexed through `/repos/{repo_id}/index`.
11. `/issues/{issue_id}/plan` retrieves cited context, creates a plan, and records the policy decision.
12. `/plans/{plan_id}/approve` records human approval.
13. `/repopilot approve`, `/repopilot reject`, `/repopilot revise`, and `/repopilot stop` issue comments are normalized and audited as GitHub commands. Sender permission checks use GitHub collaborator permissions when installation credentials are configured.
14. Approved runs can execute allowlisted validation commands through `/runs/{run_id}/sandbox`.
15. `/runs/{run_id}/implement` applies model-proposed, executor-mediated workspace tool calls in an isolated workspace.
16. `/runs/{run_id}/security-scan` gates generated evidence before PR creation.
17. `/runs/{run_id}/open-draft-pr` creates a local draft PR record by default, or a real branch/commit/draft PR when write mode and evidence gates pass.
18. `/prs/{pr_id}/ci` and PR-linked `workflow_run` events ingest CI conclusions and promote clean runs to review.
19. The dashboard reads `/webhooks/events`, `/repos`, `/metrics/overview`, `/settings/readiness`, and `/auth/session`.

## Safety Boundary

Local mode creates branch and draft PR records only. Real GitHub branch, commit, comment, and draft PR writes are implemented but remain gated by `GITHUB_WRITES_ENABLED=true`, verified installation credentials, approved plan hash, validated diff hash, security gates, and permission checks.
