# Security Model

RepoPilot AI is security-sensitive because it can eventually create branches, commits, pull requests, comments, and labels.

## Implemented Security Defaults

- GitHub webhook requests are verified with `X-Hub-Signature-256`.
- GitHub deliveries are deduped by `X-GitHub-Delivery`.
- GitHub webhook deliveries are persisted as minimized/redacted processing envelopes with original payload hashes; audit entries are persisted with redacted metadata before processing.
- Issue text is treated as untrusted input during deterministic triage.
- Prompt-injection style issue text escalates to human review.
- Plans are generated before implementation and are stored with retrieved code citations.
- Plan approval is required before a run can start or execute sandbox validation.
- Policy checks deny commands outside the allowlist and escalate high-risk file paths such as workflows, auth, payments, migrations, Docker files, and env files.
- Escalated plans require an `owner` or `maintainer` approval role.
- The default sandbox backend runs validation commands through Docker with network disabled, CPU/memory/pid limits, and a scrubbed environment.
- Generated patches are applied only to copied run workspaces after an approved plan and policy review.
- The implementation agent requests bounded workspace write tools, and `ToolExecutor` enforces isolated workspace, approved-plan hash, approved write paths, high-risk path, and max file-count checks at the mutation point.
- Patch hashes, changed-file metadata, sandbox validation output, and implementation audit events are persisted for review.
- Security scans detect secret-like text, prompt-injection phrases, and high-risk generated patch paths before draft PR creation.
- `security.semgrep` runs `semgrep --config auto --json --quiet .` against isolated workspaces when `SEMGREP_ENABLED=true`; if Semgrep is enabled but unavailable or fails, the adapter records a high-severity finding instead of silently passing.
- `security.dependency_audit` runs `npm audit --audit-level=moderate --json` for `package-lock.json` and `pip-audit --format json` for Python manifests when `DEPENDENCY_AUDIT_ENABLED=true`; unavailable tools or failed audit commands fail closed with persisted findings.
- `.github/workflows/codeql.yml` runs CodeQL analysis for Python and JavaScript/TypeScript using the current major CodeQL Action tag on public repositories, or on private repositories when GitHub code scanning is available and the repository variable `CODEQL_ENABLED=true` is set.
- Stale isolated workspaces are cleaned on API startup and by a scheduled Celery Beat task over the shared `agent_workspaces` Docker volume.
- Local artifact files are written with owner-only permissions where supported; `repopilot.artifacts.retention_cleanup` is scheduled through Celery Beat and defaults to dry-run retention planning before operators opt into deleting expired local artifact files while retaining database audit records.
- Security findings support `open`, `acknowledged`, `fixed`, and `false_positive` lifecycle states, with review reasons required for acknowledgement and false-positive decisions.
- Draft PR creation is blocked when high or critical security findings are open.
- CI workflow/check conclusions are summarized before a run can move to `READY_FOR_REVIEW`; failed CI can create a fresh waiting revision plan.
- The state-machine guard blocks invalid state skips and records valid run transitions.
- `/settings/readiness` reports placeholder or missing production secrets before GitHub writes are enabled.
- GitHub issue-comment command, workflow-run, check-run, and check-suite normalization are implemented with collaborator permission mapping for `/repopilot` control commands.
- Real GitHub branch, commit, draft PR, and issue-comment client methods are implemented behind `GITHUB_WRITES_ENABLED`, configured GitHub App credentials, validation evidence, security evidence, and permission checks.
- The shared contracts already include policy decisions, security findings, validation results, and trace events so later phases can enforce safety centrally.
- The database schema includes `audit_logs` and `agent_steps` from the beginning.

## Required Later Controls

- Treat comments, commit messages, and third-party CI logs as untrusted input.
- CodeQL SARIF ingestion and GitHub code-scanning alert fetch hooks are available behind `CODEQL_ENABLED`; private repositories also require GitHub code scanning/Advanced Security before CodeQL upload proof can pass. Credentialed CodeQL alert evidence and provider-backed secret scanning remain release gates.
- Move from lexical retrieval to provider-backed embedding retrieval with prompt-injection filtering on retrieved context.
- Expand provider-backed embeddings and live LLM adapter tests.
- Add a credentialed GitHub demo-repository smoke test before claiming real write-mode production readiness.
- Run Semgrep/dependency-audit/CodeQL adapters in CI and capture scanner-version evidence for release claims.
