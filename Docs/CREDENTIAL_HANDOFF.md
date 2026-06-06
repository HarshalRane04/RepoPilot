# RepoPilot Credential And Smoke-Test Handoff

RepoPilot is intentionally safe-by-default. Local mode keeps GitHub writes disabled, uses mock model behavior unless a provider is configured, and stores all sensitive runtime values outside source control.

Use this handoff when you are ready to prove the live GitHub/model paths.

## Local Runtime Secret Store

For local testing, store real credentials in RepoPilot's encrypted runtime secret store, not in `.env` and not in GitHub Actions. The local store defaults to:

| File | Purpose |
|---|---|
| `.local/repopilot-secrets/runtime-secrets.json` | Encrypted runtime values used by Docker Compose API, worker, beat, and dashboard settings writes. |
| `.local/repopilot-secrets/runtime-secrets.key` | Local Fernet key used to decrypt the Docker Compose runtime store. |
| `~/.repopilot/runtime-secrets.json` | Optional host-only store used when running `make configure-runtime-secrets` outside Docker without Compose path overrides. |
| `~/.repopilot/runtime-secrets.key` | Optional host-only key for the host-only store. |

Docker Compose bind-mounts `.local/repopilot-secrets` to `/home/appuser/.repopilot` in the API, worker, and beat containers. That makes dashboard-entered secrets local and persistent across container rebuilds while keeping them out of git and out of the Docker build context.

The dashboard Settings screen writes to this store through write-only secret forms. You can also run:

```bash
make configure-runtime-secrets
```

The helper prompts with hidden input for API keys, OAuth secrets, webhook secrets, and private keys, then prints only configured/missing status. The Make target pins the helper to `.local/repopilot-secrets` even though `.env` uses the in-container `/home/appuser/.repopilot` path. Use GitHub repository Actions secrets only when a GitHub-hosted workflow needs a provider key, for example the Provider Planning Eval workflow.

## Required GitHub App Inputs

Provide these through the dashboard Settings screen or runtime secret store, not by committing them:

| Secret Or Setting | Purpose |
|---|---|
| `GITHUB_APP_ID` | Identifies the GitHub App for installation-token creation. |
| `GITHUB_APP_SLUG` | Optional human-readable app slug for links and setup context. |
| `GITHUB_APP_PRIVATE_KEY` or `GITHUB_PRIVATE_KEY_PATH` | Signs GitHub App JWTs. Prefer a path or runtime secret store entry over raw env text. |
| `GITHUB_INSTALLATION_ID` | Targets the installed organization/user account. |
| `GITHUB_WEBHOOK_SECRET` | Verifies GitHub webhook deliveries with HMAC. |
| `GITHUB_CLIENT_ID` | Enables GitHub OAuth login for the dashboard. |
| `GITHUB_CLIENT_SECRET` | Completes GitHub OAuth exchange. |
| `GITHUB_OAUTH_CALLBACK_URL` | Must match the callback URL configured in the GitHub OAuth/App settings. |
| `WEB_APP_URL` | Public dashboard URL used in OAuth and links. |
| `SESSION_SECRET_KEY` | Signs local dashboard sessions. |
| `GITHUB_WRITES_ENABLED` | Keep `false` until read-only verification passes, then enable only for a disposable demo repo. |

## Required Model Inputs

| Secret Or Setting | Purpose |
|---|---|
| `MODEL_PROVIDER` | Provider ID from the Settings model catalog. |
| `MODEL_NAME` | Selected provider model. |
| `MODEL_API_KEY` | Provider API key. |
| `MODEL_BASE_URL` | Optional custom provider base URL. |
| `MODEL_REASONING_LEVEL` | Optional reasoning level when supported by the selected model. |
| `EMBEDDING_PROVIDER` | Optional embedding provider override. |
| `EMBEDDING_MODEL` | Optional embedding model override. |

## Optional Security Tool Inputs

| Setting | Purpose |
|---|---|
| `SEMGREP_ENABLED=true` | Enables command-backed Semgrep scans. The API/worker image installs Semgrep, and `make security-scanner-snapshot` provisions it on demand for local evidence capture. |
| `DEPENDENCY_AUDIT_ENABLED=true` | Enables npm/pip dependency audit adapters. The API/worker image installs pip-audit, and the web runtime already includes npm. |
| `CODEQL_ENABLED=true` | Enables credential-gated CodeQL alert fetch and SARIF ingestion flows. |
| GitHub repository variable `CODEQL_ENABLED=true` | Allows `.github/workflows/codeql.yml` to run on private repositories after GitHub code scanning/Advanced Security is enabled. Public repositories run the workflow automatically. |

## Smoke-Test Order

Run live proof in this order so failures stay isolated:

1. Save GitHub App credentials with `GITHUB_WRITES_ENABLED=false`.
2. Run `make credential-smoke` to create a redacted aggregate status artifact for GitHub OAuth, GitHub App installation-token readiness, and model-provider readiness.
3. Run `make github-oauth-smoke` to prove the dashboard OAuth/session inputs can generate a GitHub authorize URL without exposing the client secret.
4. Run `/settings/github/app/verify` from the dashboard or API, or run `make github-app-smoke` to write redacted local evidence under `Docs/release-artifacts/`.
5. Sync installation repositories and confirm the demo repo appears.
6. Deliver a signed issue webhook and confirm it is stored, deduped, queued, normalized, and visible in Activity.
7. Post `/repopilot status` from a real collaborator and verify permission mapping.
8. Save model provider credentials and run `/settings/models/verify`.
9. Run live triage/planning on a disposable issue and confirm no code is written before plan approval.
10. Enable `GITHUB_WRITES_ENABLED=true` only for the disposable demo repo.
11. Approve a low-risk plan and run the issue-to-draft-PR flow.
12. Confirm branch, commit, draft PR, issue comment, validation evidence, security evidence, audit rows, and PR summary.
13. Disable write mode again after the smoke test unless continuing controlled validation.

## Evidence To Capture

- GitHub App verification response with secrets redacted.
- Demo repository sync result.
- Webhook event delivery ID and normalized issue.
- Permission-check result for `/repopilot status` and `/repopilot approve`.
- Draft PR URL, branch, head SHA, and issue link.
- Validation artifact URI and hash.
- Security finding summary and scanner status.
- CI/check status or a documented reason CI was unavailable.
- LLM trace IDs, prompt/response hashes, token/cost/latency totals.
- Dashboard screenshots showing verified GitHub mode, verified model mode, run trace, PR evidence, and security/eval states.

## Stop Conditions

Stop the live smoke test immediately if any of these happen:

- Webhook signature verification fails.
- Installation-token verification fails.
- Sender permission is unknown or below the required threshold.
- Plan hash does not match the approved plan.
- Validation fails.
- High or critical security findings remain open.
- PR body would contain validation/security evidence that is not backed by stored records.
- Any raw secret appears in logs, traces, artifacts, screenshots, or PR text.
