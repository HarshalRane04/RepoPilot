# RepoPilot Credential Smoke Summary

- Generated at: `2026-06-06T17:58:52.263512+00:00`
- Status: `blocked`
- GitHub OAuth: `blocked`
- GitHub App: `blocked`
- Model provider: `blocked`

## Details

| Gate | OK | Status | Detail |
|---|---|---|---|
| GitHub OAuth | `False` | `blocked` | Missing or invalid GitHub OAuth setting(s): GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET, SESSION_SECRET_KEY. |
| GitHub App | `False` | `blocked` | Missing required GitHub App credential(s): GITHUB_APP_ID, GITHUB_APP_PRIVATE_KEY or GITHUB_PRIVATE_KEY_PATH, GITHUB_INSTALLATION_ID. |
| Model provider | `False` | `blocked` | Configure a live model provider before running provider smoke verification. |

## Next Step

Save missing runtime secrets through the dashboard or make configure-runtime-secrets, then rerun make credential-smoke.
