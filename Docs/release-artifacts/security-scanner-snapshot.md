# RepoPilot Security Scanner Snapshot

- Generated at: `2026-06-03T04:55:09.551490+00:00`
- Root: `/Users/harshalrane/Documents/RepoPilot`
- Release scanner proof ready: `False`
- CodeQL workflow present: `True`
- Dependency manifests found: `8`

## Scanner Status

| Scanner | Env Key | Enabled | Status | Required For Release | Detail | Next Step |
|---|---|---|---|---|---|---|
| built_in_prompt_and_secret_guards |  | True | ready | True | Deterministic prompt-injection and secret-pattern guards are implemented in the local control plane. |  |
| release_hygiene_secret_scan |  | True | ready | True | Source-boundary hygiene scanning is available through make release-hygiene. |  |
| semgrep | SEMGREP_ENABLED | False | disabled | True | SEMGREP_ENABLED is false; Semgrep evidence remains local-placeholder only. | Install Semgrep and set SEMGREP_ENABLED=true for release scanner proof. |
| dependency_audit | DEPENDENCY_AUDIT_ENABLED | False | disabled | True | DEPENDENCY_AUDIT_ENABLED is false; npm/pip audit evidence is not production-proven. | Install audit tools and set DEPENDENCY_AUDIT_ENABLED=true for release scanner proof. |
| codeql | CODEQL_ENABLED | False | disabled | True | CODEQL_ENABLED is false; CodeQL workflow is present, but SARIF/alert evidence remains credential-blocked. | Set CODEQL_ENABLED=true after GitHub credentials and code-scanning access are verified. |

## Tool Availability

| Tool | Available | Version | Detail |
|---|---|---|---|
| semgrep | False |  | semgrep executable was not found. |
| npm | True | 10.9.4 |  |
| pip-audit | False |  | pip-audit executable was not found. |
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

- SEMGREP_ENABLED is false; Semgrep evidence remains local-placeholder only.
- DEPENDENCY_AUDIT_ENABLED is false; npm/pip audit evidence is not production-proven.
- CODEQL_ENABLED is false; CodeQL workflow is present, but SARIF/alert evidence remains credential-blocked.
