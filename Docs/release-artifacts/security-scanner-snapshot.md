# RepoPilot Security Scanner Snapshot

- Generated at: `2026-06-18T07:09:24.252405+00:00`
- Root: `/Users/harshalrane/Documents/RepoPilot`
- Release scanner proof ready: `False`
- CodeQL workflow present: `True`
- CodeQL run evidence present: `False`
- Dependency manifests found: `8`

## Scanner Status

| Scanner | Env Key | Enabled | Status | Required For Release | Detail | Next Step |
|---|---|---|---|---|---|---|
| built_in_prompt_and_secret_guards |  | True | ready | True | Deterministic prompt-injection and secret-pattern guards are implemented in the local control plane. |  |
| release_hygiene_secret_scan |  | True | ready | True | Source-boundary hygiene scanning is available through make release-hygiene. |  |
| semgrep | SEMGREP_ENABLED | True | ready | True | Semgrep is enabled and the executable is available for sandbox security gates. |  |
| dependency_audit | DEPENDENCY_AUDIT_ENABLED | True | ready | True | Dependency audit is enabled and manifests were found: 8. |  |
| codeql | CODEQL_ENABLED | True | workflow_ready | True | CODEQL_ENABLED is true and a CodeQL workflow file is present; successful GitHub CodeQL run, SARIF ingestion, or alert-fetch evidence is still required. | Run the GitHub CodeQL workflow on a code-scanning-enabled repository and capture Docs/release-artifacts/codeql-run-evidence.json or verified alert/SARIF evidence. |

## Tool Availability

| Tool | Available | Version | Detail |
|---|---|---|---|
| semgrep | True | 1.167.0 |  |
| npm | True | 10.9.4 |  |
| pip-audit | True | pip-audit 2.10.1 |  |
| codeql | False |  | codeql executable was not found. |

## Dependency Manifests

- `apps/api/requirements.txt`
- `apps/web/package-lock.json`
- `packages/evals/fixtures/python-service/pyproject.toml`
- `packages/evals/pyproject.toml`
- `packages/github_client/pyproject.toml`
- `packages/llm_client/pyproject.toml`
- `packages/policy_engine/pyproject.toml`
- `packages/shared_contracts/pyproject.toml`

## Warnings

- CODEQL_ENABLED is true and a CodeQL workflow file is present; successful GitHub CodeQL run, SARIF ingestion, or alert-fetch evidence is still required.
