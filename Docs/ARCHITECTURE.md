# RepoPilot AI Architecture

RepoPilot AI is organized around a deterministic control plane and auditable agent execution.

## Implemented Architecture: Phases 1-13

- `apps/api`: FastAPI service for health, dashboard APIs, webhook intake, planning, policy review, and run control.
- `apps/web`: Next.js dashboard shell.
- `packages/shared_contracts`: Pydantic contracts shared by API, workers, and future agent modules.
- `apps/api/alembic`: database migrations for the core lifecycle schema.
- `docker-compose.yml`: local platform runtime with API, worker, web, Postgres/pgvector, and Redis.
- `app.services.github_webhooks`: HMAC verification and payload normalization.
- `app.services.github_ingestion`: raw event storage, delivery dedupe, installation/repo/issue upserts, run creation, and worker processing.
- `app.services.github_app`: GitHub App JWT/token-provider and API-client scaffolding. It remains gated until credentials are configured and `GITHUB_WRITES_ENABLED=true`.
- `app.services.integration_readiness`: runtime readiness checks for GitHub App credentials, OAuth, model gateway, security tools, OTLP export, and secret placeholders.
- `app.services.state_machine`: explicit state-transition guard for the canonical issue-to-PR flow.
- `app.services.triage`: deterministic MVP triage until the model-backed agent arrives.
- `app.services.repo_indexer`: local repository scanner, text chunker, deterministic mock embedding writer, commit fingerprint generator, and cited context retriever.
- `app.services.planning`: deterministic planning service that creates `plans`, links `agent_runs`, records context retrieval and policy review steps, and waits for approval.
- `app.services.policy`: deny-by-default policy engine for command allowlists, high-risk path escalation, and plan-level decisions.
- `app.services.sandbox`: Docker-first command runner with network disabled, resource limits, scrubbed environment, and an explicit local backend for tests/development.
- `app.services.implementation_agent`: approved-run implementation lane that copies the source workspace, generates a scoped pytest evidence patch, guards patch paths, runs local validation through the sandbox runner, and records patch/validation evidence.
- `app.services.security_scanner`: deterministic scanner for secret-like text, prompt-injection phrases, and high-risk generated patch paths.
- `app.services.draft_pr`: local branch/PR record creator that requires approved plans, passing validation, and clean blocking-security gates.
- `app.services.ci_analyzer`: workflow conclusion ingestion, failure-log summarization, and ready-for-review promotion.
- `app.services.observability`: run trace aggregation across steps, validation results, security findings, PRs, audit logs, and LLM traces.
- `app.services.eval_runner`: benchmark-style metric collection and `eval_runs` report creation.
- `app.services.audit`: audit log writes for webhook and triage activity.
- `services/sandbox_runner/Dockerfile`: local Python/Node sandbox image used by the default Docker sandbox backend.

## Control Plane

Every agent run persists state transitions in `agent_runs` and `agent_steps`. The current worker creates a triage run from issue webhooks. Planning creates a second auditable run in `WAIT_FOR_APPROVAL`, stores the context pack and policy decision, and blocks run start until a plan is approved.

The control plane now publishes its allowed transitions through `GET /settings/state-machine` and uses a transition guard before moving an implementation run through `CREATE_BRANCH`, `IMPLEMENT_PATCH`, `GENERATE_TESTS`, `RUN_LOCAL_VALIDATION`, `RUN_SECURITY_CHECKS`, `OPEN_DRAFT_PR`, `WAIT_FOR_CI`, and `READY_FOR_REVIEW`. Invalid skips such as `WAIT_FOR_APPROVAL -> READY_FOR_REVIEW` are blocked before they can create misleading evidence.

Canonical implemented flow:

1. `VALIDATE_WEBHOOK`, `NORMALIZE_EVENT`, and `TRIAGE_ISSUE` are created from issue webhooks.
2. `POST /repos/{repo_id}/index` populates `code_chunks` for retrieval.
3. `POST /issues/{issue_id}/plan` retrieves cited context, creates an implementation plan, evaluates policy, and leaves the run in `WAIT_FOR_APPROVAL`.
4. `POST /plans/{plan_id}/approve` records the approving user and policy decision. Escalated plans require an `owner` or `maintainer` role.
5. `POST /runs/{run_id}/start` moves an approved run to `CREATE_BRANCH`; `POST /runs/{run_id}/sandbox` and `POST /runs/{run_id}/implement` require an approved plan before any validation or generated patch can run.
6. `POST /runs/{run_id}/implement` creates a disposable run workspace, writes a generated pytest evidence file, stores a patch hash and diff metadata in `agent_steps`, and records validation output in `validation_results`.
7. `POST /runs/{run_id}/security-scan` persists security findings and records `RUN_SECURITY_CHECKS`.
8. `POST /runs/{run_id}/open-draft-pr` creates a local branch/PR record only when validation passed and no open high/critical findings exist, then moves the run to `WAIT_FOR_CI`.
9. `POST /prs/{pr_id}/ci` summarizes CI evidence and moves clean successful PRs to `READY_FOR_REVIEW`.
10. `GET /runs/{run_id}/trace`, `/metrics/overview`, and `/evals/reports` provide the observability and release-evidence surfaces.
11. `issue_comment` events normalize `/repopilot approve`, `/repopilot reject`, `/repopilot revise`, and `/repopilot stop` commands into audited control-plane actions. Sender permission checks are still placeholders until the credentialed GitHub client is enabled.
12. `workflow_run` events normalize PR-linked CI conclusions and can feed the same CI analyzer used by `POST /prs/{pr_id}/ci`.

## Data Plane

PostgreSQL stores lifecycle state, raw webhook payloads, installations, repositories, issues, approvals, validation results, security findings, traces, and evaluations. The Phase 5 indexer stores lexical chunks plus deterministic mock embeddings in `code_chunks.embedding`; a real embedding provider can replace that function without changing the storage contract.

## Sandbox Boundary

The default sandbox backend runs allowlisted commands through Docker with `--network none`, CPU and memory limits, a pids limit, a scrubbed environment, and only the requested workspace mounted at `/workspace`. Generated pytest evidence patches are applied only in a copied run workspace under `/tmp/repopilot-agent-workspaces`; the platform creates local branch/PR database records for Phase 10, not real GitHub branches or commits.

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
