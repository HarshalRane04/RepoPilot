# RepoPilot Open-Source Production Readiness Plan - June 11, 2026

This plan converts `Docs/IMPROVEMENT_PLAN.md` from a broad execution ledger into the next concrete release path for making RepoPilot credible as an open-source, self-hostable GitHub App by the end of this week.

Current date: Thursday, June 11, 2026. Treat the end-of-week target as Sunday, June 14, 2026 for release-candidate readiness.

## Target Outcome

By the release-candidate cut, a new user should be able to:

1. Clone the GitHub repository.
2. Read a truthful README that does not overclaim live AI/GitHub write readiness.
3. Start RepoPilot locally with Docker Compose.
4. Configure secrets through the dashboard or encrypted runtime secret store, not source files.
5. Create or install a self-hosted GitHub App from clear instructions.
6. Verify GitHub App, OAuth, and model-provider readiness without exposing keys.
7. Run a low-risk disposable issue through plan approval, sandboxed implementation, validation, security scanning, and draft PR creation.
8. Inspect every state transition, prompt/model trace, tool action, validation result, security finding, PR event, and cost/latency metric from the operator console.

The realistic open-source release model for this week is **self-hosted single-tenant RepoPilot**. A maintainer-hosted public GitHub App can be documented as a future operating mode, but it requires a live domain, hosted infrastructure, maintainer-owned credentials, abuse controls, support process, and operational ownership.

## Current Evidence Snapshot

| Area | Evidence | Release Interpretation |
|---|---|---|
| Source state | `git status --short` shows unrelated modified web UI files and untracked `report_a.xls` / `report_b.csv`. | Do not tag until intentional changes are separated and unknown untracked files are removed, ignored, or explicitly retained outside the source boundary. |
| CI | Latest `main` CI for commit `3bfd972fec1ea39f1c4742c674b9db7babf046b3` passed on GitHub Actions run `27069899447`. | Core tests/typecheck/hygiene/package/sandbox checks are green for the pushed baseline. |
| CodeQL | Latest CodeQL workflow is skipped. | Do not claim CodeQL/code-scanning production proof yet. Public repo or private Advanced Security/code-scanning setup is still required. |
| Runtime smoke | Existing local release artifacts show previous local runtime smoke, but Docker is not currently reachable from this session. | Refresh runtime evidence before tagging. Current-session runtime proof is missing. |
| Credentials | `credential-readiness-snapshot` reports `github_mode=missing_credentials`, `model_mode=mock_model`, writes disabled, and credential smoke `blocked`. | The live GitHub/model path remains unproven until secrets are configured and smoke runs pass. |
| Deployment docs | `deployment-validation` reports zero failed findings and zero warnings. | Static deployment topology/docs are in good shape, but production-like hosted smoke remains pending. |
| Security scanner | Scanner posture evidence exists; CodeQL is not live-proven. | Semgrep/dependency-audit posture is credible; CodeQL alert ingestion must be proven or clearly labeled pending. |
| Dashboard | Static screenshots and GIFs exist for core local flows. | UI has demo evidence; live credentialed states and real PR/CI evidence need screenshots after smoke. |

## Release Blocking Gaps

These are the blockers that prevent "anyone can install and use this for actual work" from being true today.

| Priority | Gap | Why It Matters | Required Fix Or Proof |
|---|---|---|---|
| P0 | Safe credential onboarding is split across docs. | Some install docs still contain `.env` examples for secret-shaped variables, which can confuse local placeholders with live credentials. | Make all install docs prefer dashboard/runtime-secret storage for live values and reserve `.env` examples for non-secret toggles or local-only placeholders. |
| P0 | Credentialed GitHub App path is unproven. | Real branch, commit, PR, issue comment, collaborator permission, and CI log access are the core product claim. | Run the smoke order in `Docs/CREDENTIAL_HANDOFF.md` against a disposable repository and archive redacted evidence. |
| P0 | Live model/provider path is unproven. | Mock mode proves contracts, not useful AI behavior. | Save provider credentials safely, verify model access, run provider planning/retrieval/patch/applied-patch evals, and publish measured results. |
| P0 | Release gates allow blocked/failing evidence in some local artifact commands. | `--allow-blocked`, `--allow-warnings`, and `--allow-failures` are useful for local placeholder builds, but a release tag needs strict behavior. | Strict release targets now exist in `Makefile`, and tag-triggered release workflow runs now omit blocked/failed-gate allowances. The next proof step is to run them after credentials and Docker runtime are available. |
| P0 | Runtime evidence is stale for this session. | Docker is not reachable now, so current API/web/worker/beat proof cannot be refreshed. | Start Docker Desktop or a compatible daemon, rerun local smoke, and commit refreshed artifacts only if they are part of the release evidence. |
| P0 | Unknown untracked files are present. | `report_a.xls` and `report_b.csv` could accidentally enter a release package or confuse hygiene. | Decide whether to delete, move outside the repo, or document them as intentionally ignored local files. Do not commit them. |
| P1 | "Direct install" path still needs live package proof. | Open-source users need an obvious path from clone or GHCR image pull to configured GitHub App. | `make init-local-env` and `docker-compose.ghcr.yml` now cover local defaults and released-image install commands; next proof is an actual GHCR publish, package visibility check, and fresh-host pull/up/migrate smoke. |
| P1 | Service directories are scaffold-only. | `services/*/README.md` says runtime lives elsewhere; this can look like dead architecture to contributors. | Either extract real runtime entrypoints or relabel these as planned extraction packages and remove them from install-critical docs. |
| P1 | Artifact storage is local filesystem backed. | Production users need retention, cleanup, backup, and possible object-store migration. | Document local retention defaults and add an object-store extension point before making production storage claims. |
| P1 | Code scanning is not proven. | Security claims depend on live scanner evidence. | Prove CodeQL in public repo or explicitly state CodeQL is optional/pending for private repos. |
| P1 | Browser QA is local/static only. | The dashboard must not mislead users in live mode. | Capture screenshots after GitHub/model verification and after the first real draft PR. |
| P2 | Provider/eval metrics are present but not thresholded for release. | "Works for actual work" needs a minimum quality bar. | Define minimum pass rates for plan quality, retrieval precision, applied-patch validation, security block correctness, cost, and latency. |

## Code-Level Hardening Added In This Slice

| Area | Change | Remaining Risk |
|---|---|---|
| Eval execution | `/evals/run` now requires an admin/owner-equivalent role instead of being available to any authenticated viewer. | Provider-backed evals still need live credentials and measured release thresholds. |
| Security findings | Security finding list/detail reads now resolve run access before returning finding details. | The current single-tenant object model is still role-based; deeper per-installation authorization can follow live GitHub smoke. |
| Release workflow | Manual release workflow dispatch remains diagnostic, but tag-triggered runs now fail on failed eval gates or blocked credential smoke. | Tag release still needs credentialed GitHub/model evidence before it can pass. |
| Service scaffolds | `services/*/README.md` now labels each directory as scaffold-only/planned extraction, not a separate deployable service in v1. | Deeper service extraction remains future architecture work. |
| Release profile | `REPOPILOT_RELEASE_PROFILE=production` makes readiness block local-record GitHub write mode instead of treating disabled writes as acceptable demo posture. | Credentialed write smoke is still required before a production profile can be considered ready. |
| Runtime secret key | Non-local readiness now requires `REPOPILOT_RUNTIME_SECRETS_KEY` or an external deployment secret manager instead of accepting the local managed key file. | Secret rotation and backup remain deployment-owner responsibilities. |
| Model fallback | Non-local model calls now fail closed when `ALLOW_MODEL_FALLBACK=false`; deterministic fallback remains available for local/offline demos. | Provider-backed planning, retrieval, patch, and applied-patch evals still need live credentials and published thresholds. |

## Four-Day Release-Candidate Sprint

### Day 1 - Thursday, June 11: Source And Install Hygiene

Goal: Make the repository safe to open-source and easy to understand before any live credentials are used.

Tasks:

1. Clean generated local caches and separate unrelated local files from release work.
2. Update `Docs/GITHUB_APP_SETUP.md` so secrets are saved through dashboard/runtime-secret storage, not copied into `.env`.
3. Add a strict release verification target, separate from local placeholder-friendly targets. Completed locally through `make release-verify`; it is expected to fail until credential smoke and runtime smoke are real.
4. Add a concise `QUICKSTART.md` or README section for the self-hosted path:
   - prerequisites
   - run `make init-local-env`
   - start Compose
   - migrate
   - open dashboard
   - save runtime secrets
   - run smoke checks
5. Label scaffold-only service directories as "planned extraction" in the README or move them out of the critical install path.
6. Refresh `make release-hygiene`, `make source-boundary-manifest`, and GitHub CI evidence.

Exit evidence:

- Clean source boundary.
- No raw secrets in docs or artifacts.
- No unknown untracked release files.
- README/quickstart tells a new user exactly what is real, local-only, or credential-gated.

### Day 2 - Friday, June 12: Credentialed GitHub And Model Proof

Goal: Prove the two most important live integrations without exposing secrets.

Tasks:

1. Save GitHub OAuth/App credentials through the dashboard or `make configure-runtime-secrets`.
2. Verify GitHub OAuth/session config.
3. Verify GitHub App installation-token creation.
4. Save model provider credentials through runtime secrets.
5. Verify selected provider/model.
6. Set `REPOPILOT_RELEASE_PROFILE=production`, provide `REPOPILOT_RUNTIME_SECRETS_KEY` through the deployment secret manager, keep `ALLOW_MODEL_FALLBACK=false`, and run `make credential-smoke` in strict mode after secrets are present.
7. Sync a disposable demo repository from the GitHub installation.
8. Deliver a signed issue webhook and verify it is stored, queued, normalized, and visible in Activity.

Exit evidence:

- Redacted credential smoke status is `passed`.
- `/settings/readiness` shows verified GitHub/model modes.
- No raw key appears in terminal logs, docs, artifacts, database traces, screenshots, or PR content.

### Day 3 - Saturday, June 13: Real Issue-To-Draft-PR Demo

Goal: Prove the actual RepoPilot loop on a disposable repository.

Tasks:

1. Use a low-risk demo issue with clear acceptance criteria.
2. Run triage, retrieval, and plan generation.
3. Approve the plan from dashboard and/or `/repopilot approve`.
4. Run executor-mediated implementation in the isolated workspace.
5. Run validation and security scans.
6. Enable write mode only for the disposable demo repository.
7. Open a real draft PR with evidence-backed body content.
8. Ingest CI/check status or record why CI is unavailable.
9. Disable write mode again after smoke unless continuing controlled tests.

Exit evidence:

- Real draft PR URL, branch, head SHA, issue link, validation artifact URI/hash, security summary, audit trail, and run trace.
- `GITHUB_WRITES_ENABLED=false` blocks the same write path when disabled.
- Dashboard screenshots show live verified modes, run trace, PR evidence, and security/eval state.

### Day 4 - Sunday, June 14: Release Candidate Packaging

Goal: Turn proof into an honest open-source release candidate.

Tasks:

1. Run provider planning/retrieval/patch/applied-patch evals.
2. Publish measured quality report under `Docs/eval-reports/`.
3. Refresh release notes, release checklist, demo script, case study, and limitations.
4. Run strict release verification:
   - API tests
   - web typecheck/build
   - migration verification
   - source-boundary manifest
   - release hygiene
   - credential smoke
   - security scanner snapshot
   - deployment validation
   - runtime deployment smoke
   - release workflow dry run
5. Confirm GitHub Actions CI is green on the release candidate commit.
6. Tag only if credentialed evidence, eval evidence, browser evidence, and hygiene gates pass.

Exit evidence:

- `v1.0.0-rc.1` can be created with defensible limitations.
- `v1.0.0` should wait until the same evidence is current and reviewed.

## Functional Hardening Backlog

| ID | Work Item | Release Priority | Acceptance Evidence |
|---|---|---|---|
| PRD-01 | Strict release gates | P0 | `make release-verify` now chains strict hygiene, credential smoke, security scanner, deployment validation, and runtime smoke targets. Run it only when credentials and Docker runtime are ready. |
| PRD-02 | Credential-safe GitHub setup docs | P0 | `Docs/GITHUB_APP_SETUP.md` now routes live secrets to the dashboard/runtime store; continue auditing README and runbooks before tagging. |
| PRD-03 | First-run setup checklist | P1 | Dashboard Settings shows ordered blockers and "next action" for GitHub App, OAuth, model, scanners, and OTLP; docs now include `make init-local-env`, source-build `make up`, and released-image `make ghcr-pull`/`make ghcr-up`/`make ghcr-migrate`. |
| PRD-04 | Demo repository smoke script | P0 | Script or runbook captures real issue-to-draft-PR evidence with redaction. |
| PRD-05 | Provider eval threshold file | P1 | Versioned thresholds for plan, retrieval, patch, security, latency, and cost. |
| PRD-06 | Service scaffold decision | P1 | Runtime docs either map each service directory to real code or mark it explicitly as future extraction. |
| PRD-07 | Artifact retention policy | P1 | Configurable retention and cleanup docs for local artifacts; object-store path documented as future/hardening. |
| PRD-08 | CodeQL proof or honest limitation | P1 | Public CodeQL run or private code-scanning setup evidence; otherwise release notes say CodeQL is not proven. |
| PRD-09 | Browser live-state capture | P1 | Screenshots/GIFs for verified model, verified GitHub, real draft PR, CI state, and security findings. |
| PRD-10 | Contributor issue templates | P2 | Bug/security/setup issue templates guide users to redact logs and avoid posting secrets. |

## Dead Features And Dead Code Decisions

Use this classification before release:

| Area | Current Shape | Decision |
|---|---|---|
| `services/*` directories | README-only scaffolds; runtime lives in `apps/api/app/services`. | Keep only if README and architecture docs call them future extraction points. Do not imply they are deployable services. |
| Compatibility re-exports | `apps/api/app/services/model_catalog.py`, policy wrappers, and GitHub wrappers preserve API call sites after package extraction. | Keep for now; remove only after credentialed smoke proves deeper package boundaries. |
| Local-record PR mode | Creates local PR records when writes are disabled. | Keep. It is a safety feature, not dead code, but UI must label it clearly. |
| Mock model and mock embeddings | Deterministic default for tests/local mode. | Keep. It is a test harness, not production AI. Release docs must not present it as live agent behavior. |
| Placeholder-friendly artifact commands | `--allow-blocked` and `--allow-failures` keep local docs generation useful. | Keep for local mode, but add strict release gates for tags. |

## Security And Privacy Requirements

1. No raw secrets in source files, docs, shell history artifacts, screenshots, PR bodies, LLM traces, or release artifacts.
2. Runtime secrets stay in `.local/repopilot-secrets` for local Compose or a production secret manager for hosted deployment.
3. The Fernet key and encrypted local store must remain git-ignored and excluded from Docker build context.
4. Dashboard secret fields must be write-only after save; status responses may show configured/missing only.
5. Readiness and smoke artifacts must be redacted by construction.
6. Prompt builders must redact issue/context secrets before model calls.
7. CI logs, workflow logs, and scanner output must be bounded and redacted before model summarization.
8. High/critical security findings block draft PR creation until resolved or explicitly reviewed according to policy.
9. GitHub writes require verified installation credentials, write mode, collaborator permission, approved plan hash, validation evidence, clean security gates, and audit persistence.
10. Open-source docs must tell users never to paste credentials into GitHub issues, discussions, PR comments, screenshots, or public logs.

## Agent Harness Efficiency Requirements

Before claiming production readiness for real work, measure and publish:

| Metric | Why It Matters | Target For RC |
|---|---|---|
| Context precision | Avoids wasting model context and bad edits. | Report current value from provider retrieval eval; set threshold after first live run. |
| Applied patch pass rate | Measures useful codegen, not only valid JSON. | Report across fixture tasks; do not overclaim if below threshold. |
| First validation pass rate | Shows whether the agent loops efficiently. | Capture from fixture/demo runs. |
| Security block correctness | Ensures malicious tasks are stopped. | Security fixtures must block or escalate correctly. |
| Cost per run | Allows users to choose provider/model realistically. | Publish median and max for benchmark runs. |
| Latency per stage | Exposes slow retrieval/model/sandbox phases. | Publish webhook-to-plan and approval-to-PR timings. |
| Retry/fallback rate | Reveals provider instability or schema failures. | Publish fallback counts from LLM traces. |

## Go/No-Go Decision

### Go For Open-Source Release Candidate

RepoPilot can be released as an open-source self-hosted RC if:

- CI is green on the release candidate commit.
- The repo has a clean source boundary.
- Install docs are safe and reproducible.
- Credentialed smoke is either passed or the release is explicitly labeled "local-control-plane preview" rather than production-ready.
- Model/provider evals have current measured evidence.
- The dashboard accurately labels mock/local/live states.
- Known limitations are present in README and release notes.

### No-Go For Production v1.0

Do not tag production `v1.0.0` if any of these are true:

- GitHub App write smoke has not opened a real draft PR.
- Live model/provider quality has not been measured.
- Credential smoke is blocked.
- Runtime deployment smoke cannot be refreshed.
- Unknown untracked files remain in the source boundary.
- Code/security claims exceed actual scanner evidence.
- The UI or docs imply autonomous or ungated writes.

## Immediate Next Commit Scope

The safest next implementation slice is:

1. Add or update quickstart/install docs for self-hosted open-source users.
2. Audit README and runbooks for any remaining `.env` wording that could encourage live secret exposure.
3. Run non-credentialed tests and hygiene checks.
4. Configure credentials safely, then run `make release-verify`.
