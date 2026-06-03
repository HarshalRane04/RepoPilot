# Security Scanner Service

Status: service scaffold. Runtime implementation currently lives in `apps/api/app/services/security_scanner.py`; this directory is reserved for future extraction of Semgrep, dependency-audit, CodeQL, and secret-scanning adapters.

Phase 11 is implemented in `apps/api/app/services/security_scanner.py` and the `/runs/{run_id}/security-scan` route.

Current scope:

- Scan generated patch diffs and changed files.
- Detect GitHub token-like strings, AWS key-like strings, private key headers, credential-like assignments, and prompt-injection phrases.
- Flag high-risk generated paths using the policy engine.
- Persist `security_findings` and a `RUN_SECURITY_CHECKS` agent step.
- Block draft PR creation when high or critical findings remain open.

Future hardening can add Semgrep, CodeQL, dependency audit, and provider-backed secret scanning behind the same persisted finding contract.
