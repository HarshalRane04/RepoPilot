# RepoPilot Credential Readiness Snapshot

- Generated at: `2026-06-02T19:38:43.729203+00:00`
- Environment: `local`
- Production ready: `False`
- GitHub mode: `missing_credentials`
- Model mode: `live_model_verified`
- GitHub writes enabled: `False`

## Integrations

| Integration | State | Mode | Required | Detail | Next Step |
|---|---|---|---|---|---|
| GitHub webhook secret | placeholder | None | True | Used to verify X-Hub-Signature-256 on all GitHub webhooks. | Set GITHUB_WEBHOOK_SECRET to the value configured in the GitHub App. |
| GitHub App installation credentials | missing | missing_credentials | True | Required for installation tokens, branch creation, commits, PRs, comments, labels, checks, and CI log reads. | Set GITHUB_APP_ID, GITHUB_APP_PRIVATE_KEY or GITHUB_PRIVATE_KEY_PATH, and GITHUB_INSTALLATION_ID. |
| GitHub OAuth credentials | configured | oauth_configured | True | Required for real GitHub user sessions and repository import from the dashboard. | Set GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET, SESSION_SECRET_KEY, GITHUB_OAUTH_CALLBACK_URL, and WEB_APP_URL. |
| GitHub write mode | disabled | local_record_mode | False | Local record mode is active; branch and PR operations stay in the database. | Set GITHUB_WRITES_ENABLED=true only after GitHub App credentials are configured. |
| LLM model gateway | verified | live_model_verified | True | Provider configured as OpenRouter/google/gemma-4-31b-it:free at https://openrouter.ai/api/v1. | Set MODEL_API_KEY and run provider verification before live planning/code-generation claims. |
| External security tools | placeholder | regex_scanner_only | True | Enabled tools: deterministic regex scanner only. | Enable SEMGREP_ENABLED, CODEQL_ENABLED, and DEPENDENCY_AUDIT_ENABLED after tool installation/workflows exist. |
| OpenTelemetry export | placeholder | otel_export_unconfigured | False | OpenTelemetry instrumentation is enabled but no OTLP exporter endpoint is configured. | Set OTEL_EXPORTER_OTLP_ENDPOINT for real trace export. |
| Dashboard session secret | configured | session_secret_ready | True | Required before replacing local header auth with cookie-backed GitHub sessions. | Set SESSION_SECRET_KEY to a long random secret. |

## Blockers

- GitHub webhook secret: Set GITHUB_WEBHOOK_SECRET to the value configured in the GitHub App.
- GitHub App installation credentials: Set GITHUB_APP_ID, GITHUB_APP_PRIVATE_KEY or GITHUB_PRIVATE_KEY_PATH, and GITHUB_INSTALLATION_ID.
- External security tools: Enable SEMGREP_ENABLED, CODEQL_ENABLED, and DEPENDENCY_AUDIT_ENABLED after tool installation/workflows exist.

## Warnings

- GitHub write mode: Local record mode is active; branch and PR operations stay in the database.
- OpenTelemetry export: OpenTelemetry instrumentation is enabled but no OTLP exporter endpoint is configured.

## GitHub App Field Status

| Field | Configured | Secret | Source |
|---|---|---|---|
| GITHUB_WEBHOOK_SECRET | False | True | environment |
| GITHUB_APP_ID | False | False | environment |
| GITHUB_APP_SLUG | False | False | environment |
| GITHUB_APP_PRIVATE_KEY | False | True | environment |
| GITHUB_PRIVATE_KEY_PATH | False | False | environment |
| GITHUB_INSTALLATION_ID | False | False | environment |
| GITHUB_APP_VERIFIED_AT | False | False | environment |
| GITHUB_APP_VERIFIED_INSTALLATION_ID | False | False | environment |
| GITHUB_WRITE_SMOKE_VERIFIED_AT | False | False | environment |
