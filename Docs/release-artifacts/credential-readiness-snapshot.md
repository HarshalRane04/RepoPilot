# RepoPilot Credential Readiness Snapshot

- Generated at: `2026-06-06T17:51:43.318978+00:00`
- Environment: `local`
- Production ready: `False`
- GitHub mode: `missing_credentials`
- Model mode: `mock_model`
- GitHub writes enabled: `False`

## Integrations

| Integration | State | Mode | Required | Detail | Next Step |
|---|---|---|---|---|---|
| GitHub webhook secret | configured | None | True | Used to verify X-Hub-Signature-256 on all GitHub webhooks. | Set GITHUB_WEBHOOK_SECRET to the value configured in the GitHub App. |
| GitHub App installation credentials | missing | missing_credentials | True | Required for installation tokens, branch creation, commits, PRs, comments, labels, checks, and CI log reads. | Set GITHUB_APP_ID, GITHUB_APP_PRIVATE_KEY or GITHUB_PRIVATE_KEY_PATH, and GITHUB_INSTALLATION_ID. |
| GitHub OAuth credentials | missing | oauth_missing | True | Required for real GitHub user sessions and repository import from the dashboard. | Set GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET, SESSION_SECRET_KEY, GITHUB_OAUTH_CALLBACK_URL, and WEB_APP_URL. |
| GitHub write mode | disabled | local_record_mode | False | Local record mode is active; branch and PR operations stay in the database. | Set GITHUB_WRITES_ENABLED=true only after GitHub App credentials are configured. |
| LLM model gateway | placeholder | mock_model | True | The deterministic mock model keeps tests stable but cannot perform real planning or patch generation. | Set MODEL_PROVIDER, MODEL_NAME, and MODEL_API_KEY for the selected provider. |
| External security tools | configured | external_scanners_enabled | True | Enabled tools: Semgrep, CodeQL, dependency audit. | Enable SEMGREP_ENABLED, CODEQL_ENABLED, and DEPENDENCY_AUDIT_ENABLED after tool installation/workflows exist. |
| OpenTelemetry export | placeholder | otel_export_unconfigured | False | OpenTelemetry instrumentation is enabled but no OTLP exporter endpoint is configured. | Set OTEL_EXPORTER_OTLP_ENDPOINT for real trace export. |
| Dashboard session secret | configured | session_secret_ready | True | Required before replacing local header auth with cookie-backed GitHub sessions. | Set SESSION_SECRET_KEY to a long random secret. |

## Blockers

- GitHub App installation credentials: Set GITHUB_APP_ID, GITHUB_APP_PRIVATE_KEY or GITHUB_PRIVATE_KEY_PATH, and GITHUB_INSTALLATION_ID.
- GitHub OAuth credentials: Set GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET, SESSION_SECRET_KEY, GITHUB_OAUTH_CALLBACK_URL, and WEB_APP_URL.
- LLM model gateway: Set MODEL_PROVIDER, MODEL_NAME, and MODEL_API_KEY for the selected provider.

## Warnings

- GitHub write mode: Local record mode is active; branch and PR operations stay in the database.
- OpenTelemetry export: OpenTelemetry instrumentation is enabled but no OTLP exporter endpoint is configured.

## GitHub App Field Status

| Field | Configured | Secret | Source |
|---|---|---|---|
| GITHUB_WEBHOOK_SECRET | True | True | environment |
| GITHUB_APP_ID | False | False | environment |
| GITHUB_APP_SLUG | False | False | environment |
| GITHUB_APP_PRIVATE_KEY | False | True | environment |
| GITHUB_PRIVATE_KEY_PATH | False | False | environment |
| GITHUB_INSTALLATION_ID | False | False | environment |
| GITHUB_APP_VERIFIED_AT | False | False | environment |
| GITHUB_APP_VERIFIED_INSTALLATION_ID | False | False | environment |
| GITHUB_WRITE_SMOKE_VERIFIED_AT | False | False | environment |
