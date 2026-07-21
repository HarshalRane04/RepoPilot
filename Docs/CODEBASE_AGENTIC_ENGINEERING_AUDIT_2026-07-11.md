# RepoPilot Codebase and Agentic Engineering Audit

Date: 2026-07-11; final verification refreshed 2026-07-15
Branch reviewed: `codex/dependabot-manifest-root`
Status: implementation and complete local proof finished; separately authorized external proof remains intentionally pending

## Executive Outcome

RepoPilot has been moved from a partially connected release-candidate harness to a materially safer and more useful single-tenant agent control plane. The work did not merely add endpoints or expose more tools. It tightened the authority boundaries around every consequential action, connected the approved-plan workflow into a practical one-click execution lane, made repository acquisition and monorepo validation real, bound evidence to the exact generated patch, removed non-functional and dangerous surface area, and made the local verification path deterministic.

The result is suitable for continued release-candidate testing. It is not yet honest to call it production-ready because real GitHub writes, live provider quality, published-image installation, and a production-like deployment still require external credentials and controlled proof.

Key measured outcomes:

- Full API suite increased from the 283-test audit baseline to **354 passing tests**.
- The release-shaped API test target runs in the networkless sandbox image with mock model settings, rather than inheriting developer provider secrets.
- Ruff, TypeScript, the isolated production web build, `npm audit`, both Compose configurations, the Alembic round trip, readiness, the real Unix-socket sandbox path, static deployment validation, and runtime deployment smoke all pass.
- The main tool registry was simplified while its useful capabilities improved: unsafe/fabricated tools were removed and 32 permission-tiered, schema-validated tools remain.
- Empty service placeholders were removed. `services/sandbox_runner` is now the only separately deployed service under `services/` because it owns a real isolation boundary.
- RepoPilot's own GitHub mutation mode remained disabled throughout runtime verification. Repository-maintenance commits and PR updates were performed separately through the authenticated maintainer CLI; no agent-generated patch was written to GitHub and `GITHUB_WRITES_ENABLED` remained false.

## Scope and Method

The review covered every tracked top-level area and followed the complete operational path rather than treating files in isolation:

- API routes, authentication, authorization, persistence models, migrations, workers, retries, service boundaries, tool registry, agent implementations, provider adapters, and shared contracts.
- Operator-console data loading, workflow actions, settings, readiness, repository UX, plan/run/PR/security views, polling, and error handling.
- Source and released-image Compose definitions, Dockerfiles, non-root ownership, storage, health/readiness, deployment validation, and release scripts.
- Tests, fixtures, eval harnesses, release evidence, and public documentation.
- Cross-cutting threat review for prompt injection, secret leakage, object authorization, stale evidence, path traversal, symlinks, archive bombs, command execution, tool escalation, webhook duplication, CI trust, and write-mode time-of-check/time-of-use gaps.

The audit used repository-wide inventory and pattern searches, dependency/route tracing, targeted tests while editing, full regression suites, static checks, container rebuilds, live service readiness, and a real request across the API-to-sandbox Unix socket.

## Repository Inventory

| Measure | Audited value |
|---|---:|
| Tracked files | 328 |
| Runtime/test files under `apps`, `packages`, `services`, and `scripts` | 271 |
| Python lines in those areas | 33,991 |
| TypeScript/TSX lines | 5,533 |
| API test modules | 40 |
| Alembic revisions | 11 |
| Independently deployable `services/` runtimes after cleanup | 1 |

The largest remaining maintainability hotspot is `apps/web/app/operator-console.tsx`, now 4,960 lines after its duplicated primitive layer was extracted and consolidated. Screen/data/action decomposition is deliberately listed as remaining work instead of being hidden behind an unrelated large rewrite.

## Resulting Control Flow

```mermaid
flowchart LR
    A["GitHub webhook or operator prompt"] --> B["Authenticate, authorize, minimize, dedupe"]
    B --> C["Triage and bounded repository retrieval"]
    C --> D["Evidence-cited implementation plan"]
    D --> E["Human and policy approval gate"]
    E --> F["Deterministic run orchestrator"]
    F --> G["Implementation read/write tool loop"]
    G --> H["Complete changed-file manifest hash"]
    H --> I["Networkless sandbox validation"]
    I --> J["Patch-bound security gate"]
    J --> K["Local record or credential-gated draft PR"]
    K --> L["Trusted GitHub CI evidence"]
    L --> M["Ready for human review"]
```

Every transition in this flow is persisted. Human gates, workspace writes, sandbox execution, external reads, security gates, and GitHub writes have different permission tiers rather than sharing a generic “agent can call tools” capability.

## Material Gaps Found and Remediated

### 1. Authentication and ownership were too implicit

**Gap:** OAuth login could infer owner authority too broadly, new users defaulted too generously, and session roles could drift from the database. Local header authentication also needed an explicit local-only boundary.

**Remediation:**

- Added explicit `REPOPILOT_GITHUB_OWNER_LOGIN` ownership configuration.
- Preserved existing database roles on return login.
- Allowed first-user owner bootstrap only when there are no OAuth users; denied later unknown users unless provisioned.
- Defaulted ordinary users to `viewer` and resolved session role from the database.
- Restricted header authentication to local development and added logout support.
- Surfaced the owner-login boundary in Settings and readiness.

**Primary files:** `apps/api/app/services/github_oauth.py`, `apps/api/app/services/auth.py`, `apps/api/app/api/routes/auth.py`, `apps/api/app/core/config.py`, `apps/web/app/operator-console.tsx`.

### 2. Object authorization was inconsistent

**Gap:** Several routes loaded plans, issues, runs, pull requests, prompts, and findings without consistently proving that the current user could access the owning repository/workspace.

**Remediation:** Added resource-aware authorization to issue, plan, prompt, run, pull-request, artifact, and security workflows; constrained admin-only recovery controls; and kept local convenience auth from becoming a production bypass.

**Primary files:** `apps/api/app/api/routes/issues.py`, `plans.py`, `prompts.py`, `runs.py`, `prs.py`, `security.py`, `artifacts.py`, and `apps/api/app/services/authorization.py`.

### 3. Webhook delivery was durable but not fully race-safe

**Gap:** Queue failures were not fully durable, task redelivery could reprocess a terminal event, and two concurrent HTTP deliveries could both pass the pre-insert lookup before the unique constraint rejected one.

**Remediation:**

- Added retry count, next-attempt, enqueue timestamp, and redacted last-error persistence.
- Added bounded Celery Beat reconciliation for broker outages.
- Used late acknowledgement and retry backoff for processing tasks.
- Row-locked event processing and returned immediately for processed/ignored/blocked states.
- Wrapped inserts in a savepoint and recovered uniqueness conflicts through the normal duplicate-delivery response path.

**Value:** The HTTP intake, broker handoff, and at-least-once worker semantics now form one idempotent workflow instead of three independent best-effort steps.

**Primary files:** `apps/api/app/api/routes/webhooks.py`, `apps/api/app/services/github_ingestion.py`, `apps/api/app/worker/tasks.py`, `apps/api/app/worker/celery_app.py`, migration `0009_durable_webhook_delivery.py`.

### 4. Repository acquisition was not a safe product workflow

**Gap:** Lower-level indexing accepted server paths, GitHub acquisition was incomplete, and OAuth-discovered repositories looked acquirable even when no GitHub App installation could read their contents.

**Remediation:**

- Added bounded GitHub archive acquisition with download, entry-count, unpacked-size, traversal, symlink, and special-file checks.
- Used repository-scoped locking and atomic canonical-workspace replacement.
- Bound acquired source to the fetched commit.
- Added `POST /repos/{id}/acquire` and the operator-console acquisition action.
- Kept lower-level indexing only for server-managed paths under the canonical repository root.
- Returned explicit `github_app` versus `oauth_discovery` source mode and `acquirable` state. OAuth-only acquisition now fails locally with `409` before any network call.

**Primary files:** `apps/api/app/services/repository_workspace.py`, `apps/api/app/api/routes/repos.py`, `apps/api/app/services/github_app.py`, `apps/web/app/operator-console.tsx`.

### 5. Retrieval did not make enough practical use of the indexed repository

**Gap:** Retrieval could become a repeated full scan and lacked a bounded hybrid candidate strategy, stable embedding dimensions, and useful freshness/reuse signals.

**Remediation:**

- Added content-fingerprint reuse for unchanged indexes.
- Added semantic chunk metadata and deterministic/mock embedding behavior.
- Added HNSW vector candidate selection combined with lexical ranking and cited score breakdowns.
- Fixed embedding storage to 1,536 dimensions and added the vector index migration.
- Kept external source transfer behind explicit opt-in.

**Primary files:** `apps/api/app/services/repo_indexer.py`, `apps/api/app/api/routes/repos.py`, migration `0010_vector_retrieval_index.py`.

### 6. The implementation agent was not a real bounded tool loop

**Gap:** The implementer relied too heavily on a single model response and broad harness behavior. It did not have a disciplined explore-then-write loop, repeated-call defense, or validation feedback for retries.

**Remediation:**

- Added an iterative exploration loop limited to repository grep/list/read/tree tools.
- Bounded tool observations and treated source/tool output as untrusted data.
- Suppressed repeated identical calls.
- Restricted write proposals to `workspace.apply_patch`, `workspace.replace_text`, and `workspace.write_file`.
- Added deterministic fallback only where it can produce a safe, evidence-backed edit.
- Fed failed validation evidence into bounded retry attempts.
- Propagated JSON mode and provider-reported token/cost metadata.
- Supplied the actual Pydantic JSON Schema to initial and repair calls, accepted schema-valid fenced/embedded JSON, and retained the original request during repair so a transient provider fallback does not erase task intent.
- Supplied current tool-registry argument schemas to exploration/write prompts while marking server-injected arguments, and added exact unified-diff/replace/write guidance.
- Fed blocked write-tool evidence into bounded self-correction attempts instead of failing the run at the first malformed call.
- Added a narrow deterministic Markdown-section note capability for explicit, single-approved-file documentation tasks. This executes through the same checked `workspace.replace_text` tool and avoids wasteful model calls without broadening authority.
- Stopped exploration after rounds that produce no new executable read and skipped model/exploration work when a safe deterministic tool plan is already available.

**Primary files:** `apps/api/app/services/implementation_agent.py`, `apps/api/app/services/tools/registry.py`, `apps/api/app/services/model_gateway.py`, `packages/llm_client/repopilot_llm_client/provider_adapters.py`.

### 7. Monorepo paths and validation working directories were incorrect

**Gap:** Legacy path normalization stripped `apps/api/`, which silently targeted the wrong location after full repository acquisition. Validation always ran at repository root even when the project manifest lived deeper in a monorepo.

**Remediation:**

- Preserved canonical repository-root paths everywhere.
- Added a bounded `working_directory` contract from implementation request through tool, API client, Unix-socket request, and runner.
- Selected the deepest plan-related directory containing a supported project manifest, with a safe explicit override.
- Rewrote plan commands relative to that working directory without invoking a shell.
- Rejected absolute, traversal, missing, symlink, or outside-workspace working directories at both client and runner boundaries.

**Primary files:** `packages/shared_contracts/repopilot_contracts/models.py`, `apps/api/app/services/implementation_agent.py`, `apps/api/app/services/sandbox.py`, `apps/api/app/services/tools/registry.py`, `services/sandbox_runner/server.py`.

### 8. Patch authorization and provenance had parser and TOCTOU gaps

**Gap:** A proposed patch could be checked before application without independently proving the actual post-apply file set. The displayed diff was bounded for UI/model use, so hashing only that representation would not safely identify a large patch. A workspace could also change after validation but before a real GitHub write.

**Remediation:**

- Rechecked actual changed files after patch application against approved plan paths, sensitive paths, and the maximum file count.
- Reversed unauthorized changes; if safe rollback cannot be proven, discarded the disposable workspace.
- Added an independent implementer check of the captured changed-file set.
- Snapshot all non-ignored workspace file hashes while storing bounded text only for display/diff generation.
- Derive patch identity from the complete sorted `{path, change_type, before_sha256, after_sha256}` manifest, not the truncated diff.
- Recompute the live workspace manifest immediately before real branch/commit/PR creation and reject mutation.
- Reject binary, sensitive, outside-workspace, and oversized GitHub upload inputs while preserving executable mode.

**Primary files:** `apps/api/app/services/tools/registry.py`, `apps/api/app/services/implementation_agent.py`, `apps/api/app/services/draft_pr.py`, `apps/api/app/services/github_app.py`.

### 9. Validation execution shared too much host authority

**Gap:** A “sandbox” abstraction is not valuable if the API can execute arbitrary host subprocesses or control Docker. Earlier scanner/tool patterns also risked turning agent requests into host commands.

**Remediation:**

- Made source and GHCR deployments use a dedicated non-root runner over an authenticated Unix-domain socket.
- Removed Docker socket access from API and worker.
- Set runner networking to none, root filesystem read-only, all capabilities dropped, `no-new-privileges`, resource limits, and a scrubbed environment.
- Rechecked command policy, UUID workspace equality, nested working directory, request size, timeout, concurrency, and output bounds inside the runner.
- Killed timed-out process groups.
- Removed agent-exposed host Semgrep/dependency-audit subprocess tools. Those scanners remain release/CI evidence; deterministic patch scanning and credentialed CodeQL are the runtime gate.

**Primary files:** `services/sandbox_runner/server.py`, `services/sandbox_runner/Dockerfile`, `apps/api/app/services/sandbox.py`, `docker-compose.yml`, `docker-compose.ghcr.yml`, `scripts/deployment_validate.py`.

### 10. The useful workflow was fragmented across recovery endpoints

**Gap:** The dashboard exposed many pieces, but an approved plan still required manual endpoint choreography to produce a patch, validate it, scan it, and create the draft record.

**Remediation:** Added `RunOrchestrator`, `POST /runs/{id}/execute`, and `repopilot.run.execute`. The deterministic orchestrator persists queued/running/completed evidence, executes the approved implementation lane, validates, scans, opens the draft record or credential-gated PR, and stops at `WAIT_FOR_CI`.

Manual `/start`, `/implement`, `/security-scan`, and `/open-draft-pr` routes remain explicit admin/recovery controls rather than the primary UX.

Blocked/failed orchestration attempts can now create a fresh retry run with the same immutable approved plan. The prior attempt is transitioned to `FAILED`, its evidence is preserved, and the replacement run starts from a new isolated workspace rather than resuming ambiguous partial state.

**Primary files:** `apps/api/app/services/run_orchestrator.py`, `apps/api/app/api/routes/runs.py`, `apps/api/app/worker/tasks.py`, `apps/web/app/operator-console.tsx`.

### 11. CI evidence could be confused with simulation or stale state

**Gap:** Manual CI input could look authoritative; a later failed trusted CI event did not reliably revoke readiness; and late webhook events could resurrect a terminal run.

**Remediation:**

- Made `/prs/{id}/ci` admin-only and explicitly non-promoting.
- Allowed trusted GitHub workflow/check evidence to promote only current-patch runs.
- Fetched only bounded, redacted failure logs for CI diagnosis.
- Constrained model-assisted summaries to evidence present in those logs.
- Made a trusted failure transition `READY_FOR_REVIEW` back to `WAIT_FOR_CI` and block the PR.
- Refused to resurrect terminal runs on late CI events.
- Recorded run state before/after and whether the state change was applied.
- Created fresh revision runs/plans instead of mutating approved history.

**Primary files:** `apps/api/app/services/ci_analyzer.py`, `apps/api/app/services/github_ingestion.py`, `apps/api/app/services/state_machine.py`, `apps/api/app/api/routes/prs.py`, `apps/api/app/services/revision_planner.py`.

### 12. Evidence queries could mix patch generations

**Gap:** Passing validation or a closed finding from an older patch could be displayed or reused after the workspace changed.

**Remediation:**

- Added `patch_hash`, `sandbox_backend`, and timestamps to validation and security records.
- Bound PR readiness, scans, validations, and summaries to the latest implementation patch.
- Added `current_patch_hash` to PR summaries and exposed it in the UI.
- Made missing scan evidence fail closed.

**Primary files:** `apps/api/app/db/models.py`, migration `0008_evidence_provenance.py`, `apps/api/app/api/routes/prs.py`, `apps/api/app/services/security_scanner.py`, `apps/api/app/services/draft_pr.py`.

### 13. Artifacts were persisted but not a complete operator feature

**Gap:** Large evidence could be externalized without a safe authorized retrieval flow, checksum enforcement, or provenance-preserving retention behavior.

**Remediation:**

- Added authorized artifact list and download routes.
- Enforced storage-key containment, checksum verification, no-store responses, and ETags.
- Included actual artifact references in run traces.
- Added scheduled retention with dry-run default and database tombstones; deleted bytes return `410` while provenance remains queryable.

**Primary files:** `apps/api/app/services/artifacts.py`, `apps/api/app/api/routes/artifacts.py`, `apps/api/app/services/observability.py`, migration `0011_artifact_retention_tombstones.py`.

### 14. List endpoints and dashboard polling did avoidable work

**Gap:** Per-row relationship queries created N+1 behavior, and the console refreshed broad data even when the corresponding screen was not active.

**Remediation:**

- Replaced per-row database lookups with bounded bulk queries and in-memory joins.
- Added fixed-query regression tests: runs use 3 queries, pull requests 8, and security findings 6 independent of row count.
- Poll only active-screen data every 30 seconds and keep successful sections when another section fails.
- Refresh selected run traces when the run state or latest step changes, so a completed worker attempt does not leave the timeline frozen at its first six steps.
- Cache runtime secrets with file identity/stat invalidation instead of decrypting unchanged stores repeatedly.

**Primary files:** `apps/api/app/api/routes/runs.py`, `prs.py`, `security.py`, `issues.py`, `repos.py`, `apps/api/tests/test_query_efficiency.py`, `apps/web/app/operator-console.tsx`, `apps/api/app/services/runtime_secrets.py`.

### 15. The operator console mixed real controls with decorative or non-functional UI

**Gap:** The New Task action did not create a real prompt, repository acquisition still asked for host paths, plan/run actions were fragmented, and notification/profile/token/danger controls implied functionality that did not exist.

**Remediation:**

- Connected New Task to `POST /prompts`.
- Added real plan, issue, run, artifact, and PR evidence loading.
- Added state-driven actions and one-click approved-run execution.
- Replaced host-path acquisition with canonical GitHub acquisition.
- Displayed planned versus changed files and current patch identity.
- Labeled/disabled OAuth-only repositories until GitHub App access exists.
- Corrected status/currency/metric presentation, numbering, and SSR cookie forwarding.
- Removed the notification bell and fake profile, personal-token, and danger-zone controls.
- Replaced native browser prompts with an accessible in-app text-action dialog for plan revisions/rejections, CI evidence, CI revision plans, and finding review reasons.
- Removed an unreachable duplicate CI-debugger screen and disabled “explanation unavailable” controls; CI evidence analysis remains on the PR review surface where it has context.
- Added model-catalog search and an 80-row rendering cap, and moved Save before the catalog so a 345-model provider remains operable without scrolling through the entire list.
- Made saved live-provider verification durable in the UI: a successful encrypted-store marker remains `Passed` with its timestamp after page/app reload instead of regressing to the misleading `Not run` session state.
- Made a failed live recheck revoke older success markers so a reload cannot resurrect stale verification evidence.
- Kept filtered model counts exact by showing only actual matches while a search is active; the previously selected model is no longer injected into unrelated results.
- Corrected trace truthfulness: tool-call totals now count only `TOOL_CALL:*` steps, blocked steps count as errors, and the Tools tab filters out lifecycle transitions.

**Primary files:** `apps/web/app/operator-console.tsx`, `apps/web/lib/api.ts`, `apps/web/app/page.tsx`, `apps/web/app/globals.css`.

### 16. Deployment checks did not prove the actual execution boundary

**Gap:** Health alone did not distinguish a running HTTP process from a usable database, Redis, sandbox, repository volume, or artifact volume. Source/GHCR Compose parity and secret propagation also needed enforcement.

**Remediation:**

- Added `/ready` component checks.
- Added one-shot non-root storage initialization.
- Hardened source and GHCR Compose definitions consistently.
- Added environment/source/image boundary validation.
- Built API, worker, beat, sandbox, and production web images from final sources.
- Verified the real Unix-socket sandbox request from a nested project directory.

**Primary files:** `apps/api/app/api/routes/health.py`, `docker-compose.yml`, `docker-compose.ghcr.yml`, `scripts/deployment_validate.py`, `apps/api/Dockerfile`, `apps/web/Dockerfile`.

### 17. The developer verification harness was nondeterministic

**Gap:** `make api-test` executed inside the live API container, inherited configured provider state/secrets, and did not contain the complete repository or frontend toolchain. Running `next build` inside the live dev container also replaced its shared `.next` contents and caused HTTP 500 until restart.

**Remediation:**

- `make api-test` now mounts the complete checkout read-only into the networkless sandbox image and pins mock provider/embedding settings plus nonexistent runtime-secret paths.
- Added `make api-lint` using the same release-shaped image and a temporary Ruff cache.
- Added `make web-build`, which builds the Dockerfile production `runner` target without touching the live development server's `.next` volume.
- Kept `make web-typecheck` as the fast connected check.

**Primary files:** `Makefile`, `services/sandbox_runner/Dockerfile`, `Docs/QUICKSTART.md`, `Docs/RUNBOOK.md`.

### 18. Model context and budget accounting still did avoidable work

**Gap:** Individual implementation-agent observations were bounded, but the cumulative observation/snippet history could still grow across exploration rounds. Models could also request several equivalent single-file reads in one turn, while every budget check issued three aggregate database queries.

**Remediation:**

- Added strict cumulative limits for exploration history and prompt snippets, with per-snippet truncation and explicit omission markers.
- Kept the most recent usable observations when a history exceeds its budget.
- Instructed the implementer to prefer `repo.read_files` and automatically coalesced multiple valid `repo.read_file` calls into one schema-validated batch without widening tool authority.
- Replaced three budget-accounting queries with one count/token/cost aggregate query.

**Primary files:** `apps/api/app/services/implementation_agent.py`, `apps/api/app/services/security_envelope.py`, `apps/api/tests/test_phase9_implementation_agent.py`, `apps/api/tests/test_model_gateway.py`.

### 19. Worker loss could strand an approved run indefinitely

**Gap:** The orchestrator persisted queued/running evidence, but a worker crash or hard timeout between those records and completion could leave a non-terminal run without a trustworthy next action.

**Remediation:**

- Added a Celery Beat reconciliation lease that is constrained to exceed the 900-second worker hard limit.
- Selects only the latest queued/running orchestration attempt per run, row-locks the run, and rechecks the candidate before mutation.
- Persists failed-attempt and audit evidence instead of overwriting history.
- Leaves safe pre-start states requeueable and transitions in-progress states to `FAILED`, where the existing retry endpoint creates a fresh isolated workspace.

**Primary files:** `apps/api/app/services/run_orchestrator.py`, `apps/api/app/worker/tasks.py`, `apps/api/app/worker/celery_app.py`, `apps/api/app/core/config.py`, both Compose files, and `apps/api/tests/test_run_orchestrator.py`.

### 20. Pull-request CI duplicated work and had no stale-run cutoff

**Gap:** A feature-branch push with an open PR triggered the same six-job CI matrix through both `push` and `pull_request`. Superseded commits continued consuming runners, and jobs had no explicit upper bound.

**Remediation:**

- Limited `push` CI to `main`; feature branches now run once through `pull_request`.
- Added workflow/PR-scoped concurrency with cancellation of superseded runs.
- Added explicit 10-20 minute timeouts to all six CI jobs.
- Added a workflow-shape regression test so duplicate matrices and missing timeouts do not quietly return.

**Primary files:** `.github/workflows/ci.yml`, `apps/api/tests/test_ci_workflow.py`.

### 21. The extracted UI primitive layer was unused and had drifted

**Gap:** `operator-console.tsx` retained active local definitions while a second component tree was never imported. The two copies had already diverged in accessibility, routing, visual tone, and click behavior, and several generic abstraction files had no consumers.

**Remediation:**

- Made 20 directly imported component modules the single source of truth while preserving the active markup and behavior.
- Removed the 20 local copies from the console and deleted the unused `button`, `clickable-row`, barrel, panel, risk-row, and tabs variants.
- Removed the entirely dead `RiskRows` implementation and its circular type import.
- Reduced the console by 205 lines and the combined console/component surface by 375 lines; production build, TypeScript, and all frontend tests remain green.

**Primary files:** `apps/web/app/operator-console.tsx`, `apps/web/app/components/ui/`.

### 22. Dependency and CodeQL evidence could be nondeterministic or stale

**Gap:** `pip-audit` resolved range-based declarations through its own temporary virtual environment, which can crash under macOS `ensurepip`. More importantly, a successful historical CodeQL marker was accepted without proving that its head SHA matched the source being certified.

**Remediation:**

- Resolve every discovered Python declaration into one pinned transitive CPython 3.12/Linux set with `uv`, then run `pip-audit` in no-install mode against that exact set.
- Fail if resolution reports success without producing the pinned input; record resolution and audit as separate evidence steps.
- Require CodeQL evidence to carry the same head SHA as the clean current source revision.
- Include `.env.example` in the release source fingerprint and record both source and CodeQL revisions in the scanner report.

**Primary files:** `scripts/security_scanner_snapshot.py`, `.github/workflows/ci.yml`, `apps/api/tests/test_security_scanner_snapshot.py`, `Docs/SECURITY.md`.

## Agent-by-Agent Tool Strategy

Adding tools to every model-driven component would increase authority, latency, token use, and prompt-injection surface without adding value. The resulting design gives tools only where the task requires iterative observation or a controlled side effect.

| Component | Tool decision | Capabilities | Why this is the useful boundary |
|---|---|---|---|
| Triage | No arbitrary model tool loop | Deterministic issue analysis plus bounded structured model enrichment | Triage should classify untrusted text, not browse or mutate the system. Repository work belongs after an issue is accepted for planning. |
| Planning | Service-mediated retrieval, no free-form writes | Ranked `repo.search_context`, cited chunks, policy evaluation, plan persistence | The planner needs evidence, not shell/GitHub authority. Its output remains inert until approval. |
| Implementation | Iterative, capability-scoped tool loop | `repo.grep`, `repo.list_files`, batched `repo.read_file(s)`, `repo.summarize_tree`; approved workspace patch/replace/write; diff capture | This is the one agent that benefits materially from observe-act-observe behavior. Read evidence is cumulatively bounded and coalesced; every write is independently schema, path, plan, policy, and workspace checked. |
| Validation | Deterministic tools only | Allowlisted test/lint/typecheck through the Unix-socket runner | A model may select from approved validation intent, but it cannot execute a shell or record fabricated success. |
| Security | Deterministic gate plus credentialed external evidence | Patch/workspace scanner, finding explanation, CodeQL SARIF/alert ingestion | Agent-exposed host scanners were removed. Security evidence must come from deterministic content checks or a trusted external system. |
| CI diagnosis | One external-read capability | Bounded/redacted GitHub check annotations and workflow logs; evidence-constrained summary | CI needs outside evidence but no write authority. Simulation can never promote readiness. |
| Revision planner | Fresh evidence-constrained plan generation | Stored failure evidence and normal planning/policy path | A revision must create new reviewable history, not edit an already approved plan in place. |
| Run orchestrator | No model tool selection | Deterministic state machine calls into implementation, validation, security, and PR services | Orchestration is control-plane logic. Letting a model choose lifecycle transitions would reduce reliability and auditability. |

The registry's 32 tools use explicit tiers: `READ`, `DB_MUTATION`, `EXTERNAL_READ`, `WORKSPACE_WRITE`, `SANDBOX_EXEC`, `SECURITY_GATE`, `HUMAN_GATE`, and `GITHUB_WRITE`. Inputs forbid extra fields and use bounds; the executor validates actor, run state, approved-plan hash, and capability profile before dispatch.

## Redundant or Low-Value Surface Removed

- Deleted empty `services/agent_orchestrator`, `services/ci_analyzer`, `services/repo_indexer`, `services/security_scanner`, and `services/webhook_ingestion` placeholder documentation/directories. These were not services and implied deployment boundaries that did not exist.
- Removed generic/raw GitHub write tools that bypassed the evidence-gated draft-PR service.
- Removed the fabricated `validation.record_result` capability. Only executed sandbox commands can create passing validation evidence.
- Removed the fake `agent.ask_user` tool. Human interaction remains an explicit approval/control-plane state.
- Removed agent-callable host Semgrep/dependency-audit processes.
- Removed non-functional notification, profile, token, and danger-zone UI.
- Removed arbitrary host-workspace acquisition from the primary repository workflow.
- Prevented manual CI simulation from mutating a run or PR into a trusted-ready state.
- Removed scanner dependencies and virtual-environment setup from the API image; release scanners run in their owned CI/release boundary.
- Consolidated 20 active console primitives into the extracted component modules and deleted six unused/drifted abstraction files plus the dead risk-row implementation.

## Database and Evidence Changes

Four reversible migrations were added:

1. `0008_evidence_provenance`: repository identity for PRs and patch/sandbox provenance for validation/security evidence.
2. `0009_durable_webhook_delivery`: retry/reconciliation metadata for webhook queue handoff.
3. `0010_vector_retrieval_index`: HNSW index for bounded semantic candidates.
4. `0011_artifact_retention_tombstones`: durable artifact deletion metadata.

The entire migration chain was verified on a fresh temporary PostgreSQL database with `upgrade head -> downgrade base -> upgrade head`, then the running database was upgraded to head.

## Verification Evidence

| Check | Result |
|---|---|
| Python compile (`PYTHONPYCACHEPREFIX=/private/tmp/repopilot-pycache python3 -m compileall`) | Passed |
| `git diff --check` | Passed |
| `make api-lint` | Passed, Ruff reported no findings |
| `make api-test` | **354 passed**, 1 upstream Starlette/httpx deprecation warning |
| Focused concurrent webhook regression | 20/20 webhook/triage tests passed |
| `make web-typecheck` | Passed |
| `make web-build` | Passed; production `runner` image built as `repopilot-web:verify` |
| `npm audit --audit-level=high` | 0 vulnerabilities |
| UI truth guard | Passed for both guarded targets |
| `make credential-smoke-strict` | Passed for GitHub OAuth authorization URL, GitHub App installation token, and live model verification |
| `make security-scanner-snapshot-strict` | Passed after commit evidence refresh: Semgrep, pinned-transitive `pip-audit`, npm audit, and revision-matched CodeQL evidence; exact source fingerprint recorded in the generated scanner artifact |
| Source-boundary manifest | Generated successfully for 338 candidate files after the audit artifact was added |
| Release hygiene | 0 failures; 11 expected warnings for ignored local state, Docker mount points, explicit fake PEM fixtures, and the intentionally dirty review worktree |
| API/worker/beat/sandbox image rebuild | Passed |
| Source Compose config | Passed |
| GHCR Compose config | Passed |
| `/ready` | Database, Redis, sandbox, repository storage, and artifact storage all `ok` |
| `/settings/readiness` | `production_ready=true` for local `oss-demo`; GitHub `read_only_verified`, model `live_model_verified`, no blockers; local-only warnings retained |
| Real nested sandbox smoke | `python -m pytest --version` passed from `apps/api` over the authenticated Unix socket in 238 ms |
| `make migration-verify` | Upgrade/downgrade/upgrade passed through revision 0011 |
| `make migrate` | Running database at head |
| `make deployment-validate-strict` | 0 failures, 0 warnings |
| `make deployment-smoke-strict` | 0 failures, 0 warnings |
| Computer Use model-settings regression | Persisted verification rendered `Passed` after reload; `qwen3 coder` rendered exactly 6 of 6 matching OpenRouter rows |

## Post-Audit End-to-End Execution Evidence

Computer Use and direct evidence inspection exercised the complete local product path rather than only calling service methods:

- Saved and live-verified `openrouter/free` from Settings; the check explicitly sent no repository source.
- Selected the GitHub App repository, revised issue #2 to the exact `Docs/RUNBOOK.md` scope, preserved the requested pytest command, approved plan version 3, and queued the run-to-draft-PR workflow.
- Observed the first provider attempt block honestly after repeated 429 responses, then used the new retry control. Subsequent evidence exposed and drove structured-output, tool-contract, and recovery improvements rather than fabricating a patch.
- Final retry run `aed3e333-4933-4858-a09f-ec54d2510f5d` completed to `WAIT_FOR_CI` in 0.58 seconds with zero LLM calls: `workspace.replace_text` changed only `Docs/RUNBOOK.md`, the exact `python -m pytest -q apps/api/tests/test_release_targets.py` command passed in the remote networkless sandbox, security produced zero findings, and local draft PR record #3 was created with patch and validation artifacts.
- Downloaded patch evidence showed exactly one concise note under `## Local Stack`; the source repository and user worktree were not modified.
- The UI displayed all 18 persisted lifecycle steps, the linked PR record, patch identity, validation/security evidence, artifacts, and audit events. Failed predecessors remained visible as `FAILED` rather than being overwritten.
- After the application restart, Settings correctly reconstructed the saved provider verification as `Passed` with its stored timestamp. A Computer Use filter for `qwen3 coder` returned exactly 6 matching OpenRouter rows and did not inject the unrelated saved `openrouter/free` row.

Live provider quality evidence was also generated under `Docs/eval-reports/`:

- The existing five-task planning run for `openrouter/free` recorded a 0% plan-quality pass rate.
- Three-task patch-attempt and applied-patch runs both recorded a 0% patch-quality pass rate.
- The one-task retrieval run recorded 0 context precision because OpenRouter rejected `openrouter/free` as an embedding model with HTTP 400.

These are useful negative results: the free router is acceptable for connectivity experiments but is not a supported RepoPilot planning/patch/retrieval pair. The deterministic scoped-edit lane proved valuable precisely because it does not convert unreliable provider formatting into ambient write authority.

One useful harness defect was exposed during verification: an in-place production build inside the live Next development container replaced its `.next/dev` manifest and temporarily caused HTTP 500. The web service recovered after restart, and `make web-build` now performs this check in a separate image so the failure mode is not repeated.

## Remaining Gaps and Honest Limits

These are not hidden behind a “complete” label. They are the next practical work, ordered by impact.

### High: external proof gates

1. **Credentialed GitHub lifecycle:** Use a disposable repository to prove App archive acquisition, webhook intake, collaborator authorization, branch/commit/draft-PR write, issue comment, and trusted CI promotion with `GITHUB_WRITES_ENABLED` enabled only for the controlled window.
2. **Provider quality:** The full eval shape has now been exercised with `openrouter/free` and failed its quality gates. Select and authorize a stronger completion model plus a real embedding model, rerun the same matrix, and promote only pairs that pass measured gates.
3. **Published-image/fresh-host install:** Publish digest-addressed GHCR images and run `ghcr-start-local` from a clean clone/fresh host.
4. **Production-like deployment:** Prove TLS, secret injection, backups, restore, monitoring/export, rollback, and failure recovery on the target VM/container environment.

### Medium: architectural scale and maintainability

1. **Isolation strength:** The runner is a hardened, dedicated, networkless container with per-command process groups, not a new microVM/container for every command. This is appropriate for the current single-tenant threat model, not mutually hostile tenants.
2. **Frontend decomposition:** Primitive components are now extracted and deduplicated. Next extract screen/data/action domains from `operator-console.tsx` and add component-level tests; the 4,960-line console remains the main maintainability hotspot.
3. **Artifact backend:** Replace or supplement the local filesystem with object storage, lifecycle rules, encryption policy, and short-lived signed retrieval for multi-host deployments.
4. **Distributed rate limiting:** Current application-level rate limiting is process-local. Multi-instance operation needs Redis-backed/global enforcement.
5. **Runner dependency strategy:** The networkless runner cannot install arbitrary repository dependencies at execution time. Add purpose-built language images or a verified dependency cache keyed by lockfile.
6. **Observability operations:** OTLP support exists, but alert rules, dashboards, retention, and incident drills remain deployment responsibilities.

### Low: edge behavior and cleanup

1. Local-only draft PR numbers use database-local allocation and are not a substitute for GitHub's repository sequence. If local-record runs become highly concurrent, add a repository-scoped allocator.
2. Replace the upstream Starlette `TestClient`/httpx deprecation path when the dependency ecosystem's supported migration is selected.
3. Continue decomposing legacy phase-named test modules as the product stabilizes; they are test organization debt, not runtime boundaries.

### Deliberate non-features

- Autonomous merge remains out of scope.
- OAuth discovery alone does not grant source acquisition or write authority; a GitHub App installation is required.
- Arbitrary shell, arbitrary host paths, raw GitHub writes, and self-reported validation success should not be reintroduced as “flexibility.”

## Recommended Next Execution Order

1. Review this change set and report locally.
2. Keep the verified credentialed read-only GitHub path active with writes disabled; perform the disposable write/CI proof only in a controlled window.
3. Use the recorded failed free-router matrix to choose stronger completion and embedding models, then rerun the same quality gates before support is claimed.
4. Publish immutable images and verify a clean-host GHCR deployment.
5. Use one disposable repository for the write/CI lifecycle proof, then turn write mode back off.
6. Capture production-like deployment, restore, and rollback evidence.
7. Split the operator console before adding another major UI domain.

The key engineering principle from this audit is that RepoPilot should become more agentic by improving observation, feedback, state, and evidence—not by giving a model broader ambient authority.
