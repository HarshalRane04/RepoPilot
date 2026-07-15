# RepoPilot AI Architecture

RepoPilot AI is organized around a deterministic control plane and auditable agent execution.

## Implemented Architecture

- `apps/api`: FastAPI service for health, dashboard APIs, webhook intake, planning, policy review, and run control.
- `apps/web`: Next.js dashboard shell.
- `packages/shared_contracts`: Pydantic contracts shared by API, workers, and future agent modules.
- `apps/api/alembic`: database migrations for the core lifecycle schema.
- `docker-compose.yml`: local platform runtime with API, worker, beat, web, Postgres/pgvector, Redis, a one-shot non-root volume initializer, and the isolated sandbox runner.
- `app.services.github_webhooks`: HMAC verification and payload normalization.
- `app.services.github_ingestion`: minimized event storage, delivery dedupe, row-locked idempotent processing, installation/repo/issue upserts, run creation, trusted CI ingestion, and worker processing.
- `app.worker.tasks`: bounded event retries, broker-outage reconciliation, periodic cleanup, and asynchronous approved-run execution.
- `app.services.github_app`: GitHub App JWT/token provider plus read/write API client. Reads require configured credentials; writes additionally require `GITHUB_WRITES_ENABLED=true` and downstream evidence gates.
- `app.services.integration_readiness`: runtime readiness checks for GitHub App credentials, OAuth, model gateway, security tools, OTLP export, and secret placeholders.
- `app.services.state_machine`: explicit state-transition guard for the canonical issue-to-PR flow.
- `app.services.triage`: prompt-injection-aware deterministic triage with structured model-gateway enrichment and evidence-constrained fallback.
- `app.services.repository_workspace`: bounded GitHub archive acquisition, traversal/symlink rejection, atomic canonical-workspace replacement, and commit binding.
- `app.services.repo_indexer`: repository scanner, semantic chunker, embedding writer, content-fingerprint reuse, HNSW/lexical candidate retrieval, and cited context packs.
- `app.services.planning`: deterministic planning service that creates `plans`, links `agent_runs`, records context retrieval and policy review steps, and waits for approval.
- `app.services.policy`: deny-by-default policy engine for command allowlists, high-risk path escalation, and plan-level decisions.
- `app.services.sandbox`: client for the authenticated Unix-socket execution service; direct local execution exists only for controlled local tests.
- `app.services.implementation_agent`: approved-run implementation lane with bounded iterative read-tool exploration, repeated-call suppression, scoped write tools, retry feedback, diff capture, and patch-bound sandbox validation.
- `app.services.run_orchestrator`: asynchronous approved-plan execution through implementation, validation, security, and draft-PR stages, stopping at trusted CI.
- `app.services.security_scanner`: deterministic scanner for secret-like text, prompt-injection phrases, and high-risk generated patch paths.
- `app.services.draft_pr`: local branch/PR record creator that requires approved plans, passing validation, and clean blocking-security gates.
- `app.services.ci_analyzer`: trusted/simulated evidence separation, bounded failure-log summarization, patch-generation gate checks, and ready-for-review promotion.
- `app.services.artifacts`: local evidence storage, SHA-256 verification, retention tombstones, and authorized list/download backing.
- `app.services.observability`: run trace aggregation across steps, validation results, security findings, PRs, audit logs, LLM traces, and artifacts.
- `app.services.eval_runner`: benchmark-style metric collection and `eval_runs` report creation.
- `app.services.audit`: audit log writes for webhook and triage activity.
- `services/sandbox_runner`: non-root Unix-socket execution service with a networkless Compose boundary, read-only root filesystem, dropped capabilities, and resource/output limits.

## Control Plane

Every agent run persists state transitions in `agent_runs` and `agent_steps`. The current worker creates a triage run from issue webhooks. Planning creates a second auditable run in `WAIT_FOR_APPROVAL`, stores the context pack and policy decision, and blocks run start until a plan is approved.

The control plane now publishes its allowed transitions through `GET /settings/state-machine` and uses a transition guard before moving an implementation run through `CREATE_BRANCH`, `IMPLEMENT_PATCH`, `GENERATE_TESTS`, `RUN_LOCAL_VALIDATION`, `RUN_SECURITY_CHECKS`, `OPEN_DRAFT_PR`, `WAIT_FOR_CI`, and `READY_FOR_REVIEW`. Invalid skips such as `WAIT_FOR_APPROVAL -> READY_FOR_REVIEW` are blocked before they can create misleading evidence.

Canonical implemented flow:

1. `VALIDATE_WEBHOOK`, `NORMALIZE_EVENT`, and `TRIAGE_ISSUE` are created from issue webhooks.
2. `POST /repos/{repo_id}/acquire` safely refreshes canonical source and populates `code_chunks`; the lower-level `/index` route remains for already staged server-managed source.
3. `POST /issues/{issue_id}/plan` retrieves cited context, creates an implementation plan, evaluates policy, and leaves the run in `WAIT_FOR_APPROVAL`.
4. `POST /plans/{plan_id}/approve` records the approving user and policy decision. Escalated plans require an `owner` or `maintainer` role.
5. `POST /runs/{run_id}/execute` queues the approved run and persists queued/running/completed orchestration steps. The worker executes the bounded implementation agent, patch-bound validation, security scan, and draft-PR creation before stopping at `WAIT_FOR_CI`. Celery Beat reconciles only queued/running attempts older than the worker hard limit, records failure evidence, and unlocks a safe requeue or fresh isolated retry.
6. Manual `/start`, `/implement`, `/security-scan`, and `/open-draft-pr` routes remain recovery/debug controls, with the same state and evidence gates.
7. Trusted `workflow_run`, `check_run`, and `check_suite` webhooks can qualify a clean run for `READY_FOR_REVIEW`; the admin-only `/prs/{pr_id}/ci` route records non-promoting simulation evidence.
8. `GET /runs/{run_id}/trace`, `/metrics/overview`, and `/evals/reports` provide the observability and release-evidence surfaces.
9. `issue_comment` events normalize `/repopilot approve`, `/repopilot reject`, `/repopilot revise`, and `/repopilot stop` commands into audited control-plane actions after credentialed collaborator-permission checks.
10. Failed trusted workflow events retain the GitHub run ID and may fetch a size-bounded, redacted log archive before CI diagnosis.

## Data Plane

PostgreSQL stores lifecycle state, minimized/redacted webhook envelopes with original payload hashes, retry metadata, installations, repositories, issues, approvals, patch-bound validation/security evidence, artifact provenance, traces, and evaluations. `code_chunks.embedding` is fixed at 1536 dimensions and indexed with pgvector HNSW; external source transfer remains opt-in.

## Sandbox Boundary

API and worker send authenticated bounded requests over a read-only shared Unix-socket mount. The runner itself has no network, a read-only root filesystem, dropped Linux capabilities, CPU/memory/pid limits, a scrubbed environment, exact UUID workspace containment, and a bounded nested working directory for monorepos. Generated patches are applied only in copied run workspaces under `/tmp/repopilot-agent-workspaces`. Patch identity is derived from the complete changed-file SHA-256 manifest, and the draft-PR path recomputes it immediately before any write. Real GitHub writes remain behind credentials, write mode, current-patch validation/security evidence, and permission checks.

## Production Readiness Boundary

`GET /settings/readiness` is the source of truth for whether RepoPilot is still in local prototype mode or ready for credentialed operation. It reports:

- GitHub webhook secret status.
- GitHub App ID/private-key status.
- GitHub OAuth client/session-secret status.
- GitHub write mode.
- Runtime secret encryption key posture.
- LLM model gateway status.
- Non-local model fallback policy.
- External security-tool status.
- OpenTelemetry exporter status.

Real GitHub write actions must remain disabled until the readiness blockers are cleared. The local dashboard displays this state so the operator can see exactly why the system is not yet production-ready.
