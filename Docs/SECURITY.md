# Security Model

RepoPilot AI is security-sensitive because it can eventually create branches, commits, pull requests, comments, and labels.

## Implemented Security Defaults

- GitHub webhook requests are verified with `X-Hub-Signature-256`.
- GitHub deliveries are deduped by `X-GitHub-Delivery`; processing takes a row lock and returns immediately for terminal delivery states so at-least-once task redelivery cannot create duplicate runs.
- GitHub webhook deliveries are persisted as minimized/redacted processing envelopes with original payload hashes; audit entries are persisted with redacted metadata before processing.
- Issue text is treated as untrusted input during deterministic triage.
- Prompt-injection style issue text escalates to human review.
- Plans are generated before implementation and are stored with retrieved code citations.
- Plan approval is required before a run can start or execute sandbox validation.
- Policy checks deny commands outside the allowlist and escalate high-risk file paths such as workflows, auth, payments, migrations, Docker files, and env files.
- Escalated plans require an `owner` or `maintainer` approval role.
- The default sandbox backend sends authenticated requests over a private Unix socket to a dedicated non-root runner with no network, a read-only root filesystem, dropped capabilities, CPU/memory/pid limits, bounded output, and a scrubbed environment. The API and worker do not receive the Docker socket.
- Generated patches are applied only to copied run workspaces after an approved plan and policy review.
- The implementation agent requests bounded workspace write tools, and `ToolExecutor` enforces isolated workspace, approved-plan hash, approved write paths, high-risk path, and max file-count checks at the mutation point.
- Patch hashes derived from the complete changed-file SHA-256 manifest, changed-file metadata, sandbox validation output, and implementation audit events are persisted for review. The draft-PR service recomputes current workspace identity before a real GitHub write to reject post-validation mutation.
- Security scans detect secret-like text, prompt-injection phrases, and high-risk generated patch paths before draft PR creation.
- Semgrep, `pip-audit`, and `npm audit` are executed in the owned CI/release evidence boundary, not as host subprocess tools exposed to agents. Python declarations are resolved into a pinned CPython 3.12/Linux transitive set before auditing, avoiding environment-dependent temporary-venv behavior. Strict evidence records tool versions, results, a clean source revision, revision-matched CodeQL proof, and a source fingerprint. Runtime security gates use deterministic patch scanning and credentialed CodeQL ingestion.
- `.github/workflows/codeql.yml` runs CodeQL analysis for Python and JavaScript/TypeScript using the current major CodeQL Action tag on public repositories, or on private repositories when GitHub code scanning is available and the repository variable `CODEQL_ENABLED=true` is set.
- Stale isolated workspaces are cleaned on API startup and by a scheduled Celery Beat task over the shared `agent_workspaces` Docker volume.
- Local artifact files are written with owner-only permissions where supported; authorized downloads verify SHA-256 before serving. `repopilot.artifacts.retention_cleanup` defaults to dry-run and tombstones retained metadata when expired local bytes are deleted.
- Security findings support `open`, `acknowledged`, `fixed`, and `false_positive` lifecycle states, with review reasons required for acknowledgement and false-positive decisions.
- Draft PR creation is blocked when high or critical security findings are open.
- Trusted CI workflow/check conclusions are summarized before a run can move to `READY_FOR_REVIEW`; failed workflow runs can fetch bounded redacted GitHub log archives, and failed CI can create a fresh waiting revision plan. Manual CI input is simulation-only.
- The state-machine guard blocks invalid state skips and records valid run transitions.
- `/settings/readiness` reports placeholder or missing production secrets before GitHub writes are enabled.
- GitHub issue-comment command, workflow-run, check-run, and check-suite normalization are implemented with collaborator permission mapping for `/repopilot` control commands.
- Real GitHub branch, commit, draft PR, and issue-comment client methods are implemented behind `GITHUB_WRITES_ENABLED`, configured GitHub App credentials, validation evidence, security evidence, and permission checks.
- The shared contracts already include policy decisions, security findings, validation results, and trace events so later phases can enforce safety centrally.
- The database schema includes `audit_logs` and `agent_steps` from the beginning.

## Required Later Controls

- Continue expanding adversarial fixtures for comments, commit messages, and third-party CI logs; current command and CI paths already bound, redact, and evidence-constrain these inputs.
- CodeQL SARIF ingestion and GitHub code-scanning alert fetch hooks are available behind `CODEQL_ENABLED`; private repositories also require GitHub code scanning/Advanced Security before CodeQL upload proof can pass. Credentialed CodeQL alert evidence and provider-backed secret scanning remain release gates.
- Validate provider-backed embeddings and live LLM adapters against the bounded hybrid retrieval path; deterministic mock embeddings remain the private-source default.
- Add a credentialed GitHub demo-repository smoke test before claiming real write-mode production readiness.
- Keep Semgrep, dependency audits, and CodeQL evidence strict in CI; bind production readiness to the emitted `REPOPILOT_RELEASE_SOURCE_FINGERPRINT` and rerun whenever source bytes change.
