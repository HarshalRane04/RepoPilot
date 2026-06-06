# RepoPilot AI Demo Script

This script is written for the local single-tenant demo first, then the credentialed GitHub App smoke test. Keep the two modes separate in the narration: local mode proves the control plane and evidence model; credentialed mode proves real GitHub writes.

## Demo Setup

1. Start the local stack.

   ```bash
   POSTGRES_PASSWORD=placeholder REDIS_PASSWORD=placeholder GITHUB_WEBHOOK_SECRET=change-me-local-dev SESSION_SECRET_KEY=placeholder DEV_HEADER_AUTH_ENABLED=true docker compose up -d --build
   ```

2. Apply migrations.

   ```bash
   docker compose exec api alembic upgrade head
   ```

3. Open the dashboard at `http://localhost:3001`.
4. Confirm the API is healthy at `http://localhost:8000/health`.
5. Open Settings and show readiness blockers for missing live GitHub/model credentials.

## Local Control-Plane Demo

1. Show the dashboard overview: activity, repositories, issues, plans, runs, draft PR records, security findings, evals, and settings.
2. Send a signed `issues` webhook using the smoke command in `Docs/RUNBOOK.md`.
3. Show the webhook delivery in Activity and the synced repository/issue in the dashboard.
4. Index a local fixture or demo checkout and show cited repository context.
5. Generate a plan and emphasize that the run stops at `WAIT_FOR_APPROVAL`.
6. Approve the plan as an owner and show the approval ledger/hash.
7. Start the run and execute the implementation lane in the isolated workspace.
8. Open the run trace and show tool calls, policy decisions, diff hash, validation evidence, and redacted logs.
9. Run security checks and show the security lifecycle state.
10. Open the local draft PR record and PR summary. Explain that local mode does not write to GitHub.
11. Ingest CI evidence or use the CI summary endpoint to show the run reaching review-ready state.
12. Run evals and show per-task outcomes, category metrics, observed plan quality, context precision, observed patch quality, human edit distance, provider comparison ranking, and quality gates.
13. Open `Docs/eval-reports/v1-local-latest.md` to show the baseline fixture report and the remaining false gates for missing observed model/provider evidence.
14. If a provider key is configured in the encrypted local runtime secret store, run `make provider-planning-eval` and show the generated planning-only provider report without claiming patch-quality proof. Shell environment keys still work as an override for one-off runs.

Recommended demo issue:

```text
Fix repository list issue count display
```

Recommended validation command:

```bash
pytest
```

## Credentialed GitHub Smoke Demo

Run this only after the user supplies GitHub App credentials, an installation ID, and a disposable demo repository.

1. Configure secrets through `.env` or the runtime secret store:
   - `GITHUB_APP_ID`
   - `GITHUB_INSTALLATION_ID`
   - `GITHUB_APP_PRIVATE_KEY` or `GITHUB_PRIVATE_KEY_PATH`
   - `GITHUB_WEBHOOK_SECRET`
   - `GITHUB_CLIENT_ID`
   - `GITHUB_CLIENT_SECRET`
   - `SESSION_SECRET_KEY`
   - `GITHUB_WRITES_ENABLED=true`
2. Verify installation-token creation through Settings or `/settings/github/app/verify`.
3. Send a real GitHub issue event from the demo repository.
4. Use `/repopilot status` and `/repopilot approve` comments to prove collaborator permission checks.
5. Run an approved, low-risk issue through branch creation, commit creation, and draft PR creation.
6. Confirm the draft PR body contains only stored evidence: plan, changed files, validation, security, CI status, trace/cost, and rollback notes.
7. Disable `GITHUB_WRITES_ENABLED` and show that writes fail closed.

## Recording Checklist

- Capture dashboard overview.
- Capture readiness settings.
- Capture plan review before approval.
- Capture run trace after implementation.
- Capture security findings and PR evidence.
- Capture eval report.
- Capture real GitHub draft PR only after credentialed smoke succeeds.

## Claims To Avoid Until Proven

- Do not claim autonomous merging.
- Do not claim production GitHub write readiness before the credentialed smoke test.
- Do not claim live model quality before provider-backed evals run with observed plan-quality, context-precision, patch-quality, human-edit-distance, provider ranking, cost, and latency evidence.
- Do not claim browser-polished release readiness before desktop/mobile screenshots are captured.
