# RepoPilot Open-Source And Production Readiness Audit

Date: 2026-07-01  
Repository: `HarshalRane04/RepoPilot`  
Local checkout: `/Users/harshalrane/Documents/RepoPilot`  
Verdict: public open-source release candidate is valid; production-ready `v1.0.0` is not yet valid.

## Executive Verdict

RepoPilot is in a credible public release-candidate state. The repository is public, has the expected open-source surface, the local Compose stack is running, the API/web checks pass, write mode is enabled locally, and a real GitHub draft PR smoke exists.

It should not be described as production-ready yet. The hard blockers are open GitHub CodeQL alerts, missing branch protection, missing GHCR packages/releases/tags, disabled Dependabot alerting, incomplete provider-backed eval proof, and an observed planning-quality drift during the live prompt smoke. The product is strong enough to demo as a controlled single-tenant RC, but not strong enough to invite production trust without those gates closed.

## Current Public State

| Area | Status | Evidence |
| --- | --- | --- |
| Repository visibility | Pass | `HarshalRane04/RepoPilot` is public and not private. |
| License | Pass | GitHub reports MIT License. |
| Issues and discussions | Pass | Both are enabled. |
| Secret scanning | Partial pass | Secret scanning and push protection are enabled. |
| Dependabot security updates | Fail | GitHub reports `dependabot_security_updates=disabled`. |
| Dependabot alerts | Fail | API reports Dependabot alerts are disabled for the repository. |
| Branch protection | Fail | GitHub API returns `Branch not protected` for `main`. |
| Latest main CI | Pass | Latest `main` CI run succeeded on 2026-06-18. |
| CodeQL workflow execution | Pass | Scheduled CodeQL succeeded on 2026-06-30. |
| CodeQL alert posture | Fail | 48 open code-scanning alerts remain. |
| GitHub releases | Fail | `gh release list` returned no releases. |
| Git tags | Fail | No tags were present locally. |
| GHCR packages | Fail | `repopilot-api`, `repopilot-web`, and `repopilot-sandbox` packages were not found via GitHub Packages API. |

## Local Product Test Results

| Check | Result | Notes |
| --- | --- | --- |
| Docker Compose stack | Pass | API, web, worker, beat, Redis, and Postgres are running. |
| API health | Pass | `GET /health` returned 200 with `status=ok`. |
| Web app availability | Pass | `GET http://127.0.0.1:3001/` returned 200 and 307383 bytes. |
| Runtime readiness | Local pass | `GET /settings/readiness` reports `production_ready=true`, `github_writes_enabled=true`, `github_mode=write_enabled_verified`, and `model_mode=live_model_verified` for `release_profile=oss-demo`. |
| API regression suite | Pass | 81 tests passed, 1 warning. |
| Web typecheck | Pass | `npm -C apps/web run typecheck` passed. |
| Deployment validation | Pass | `scripts/deployment_validate.py` reported all deployment checks passed. |
| Compose config | Pass | `docker compose config --quiet` passed. |
| UI truth guard | Pass | No banned overclaim phrases or missing privacy labels found. |
| Release hygiene | Warning-only | No failures after clearing `.pytest_cache`; 10 warnings remain for local `.env`, `.local`, Docker mount artifacts, fake private-key test fixtures, and dirty git boundary. |
| Web dependency audit | Pass | `npm -C apps/web audit --omit=dev --audit-level=high` found 0 vulnerabilities. |
| Python dependency audit | Blocked | `pip-audit -r apps/api/requirements.txt` crashed while creating its temporary venv through `ensurepip`; result is unproven, not clean. |
| Tracked secrets check | Pass | `git ls-files` matched only `.env.example` for env/local/secret-like tracked path patterns. |

## Write-Mode And Product Exercise

Write mode is enabled and locally verified:

- `/settings/readiness` reports `github_writes_enabled=true`.
- `/settings/readiness` reports GitHub App installation credentials verified for installation `141273777`.
- `/settings/readiness` reports `github_mode=write_enabled_verified`.
- A real live write-mode smoke exists as draft PR [#2](https://github.com/HarshalRane04/RepoPilot/pull/2), titled `RepoPilot live write-mode smoke`.
- PR #2 is open, draft, mergeable, and its checks were green at audit time.

I also exercised the operator prompt flow through the running product:

- Submitted prompt: `Final audit operator prompt smoke`.
- Created issue: `b6dc90d3-b9db-4f85-b047-e636dc212e69`.
- Created triage run: `c975b09d-96d8-406c-a850-576af21379b6`.
- Generated plan: `e62e95bd-92fd-44b9-bc93-5d8c7f0fe695`.
- Generated planning run: `8213de10-e7bd-4feb-8ea6-119b1382c481`.
- Activity feed recorded prompt submission, context retrieval, plan generation, policy review, and plan rejection.
- Run trace exposed steps, LLM traces, prompt hashes, response hashes, token counts, and citations.

Important finding: the prompt asked for a documentation-only verification plan, but the generated plan targeted `smoke_app.py` and `tests/test_smoke_app.py`. I rejected the plan instead of approving it. This is a successful safety behavior for the human approval gate, but it is also a planning-quality blocker before v1. The planner/RAG stack can still overfit to the currently indexed smoke repository instead of the prompt intent.

## Open CodeQL Alerts

GitHub code scanning currently reports 48 open alerts:

| Severity | Count |
| --- | ---: |
| critical | 3 |
| high | 15 |
| medium | 3 |
| error | 12 |
| note | 15 |

Representative high-impact alerts:

| Severity | Rule | Path |
| --- | --- | --- |
| critical | `py/partial-ssrf` | `apps/api/app/services/github_app.py` |
| critical | `py/partial-ssrf` | `apps/api/app/services/model_catalog.py` |
| high | `py/path-injection` | `apps/api/app/services/implementation_agent.py` |
| high | `py/path-injection` | `apps/api/app/services/repo_indexer.py` |
| high | `py/path-injection` | `apps/api/app/services/sandbox.py` |
| high | `py/polynomial-redos` | `apps/api/app/services/ci_analyzer.py` |
| high | `py/weak-sensitive-data-hashing` | `apps/api/app/services/auth.py` |
| high | `py/clear-text-logging-sensitive-data` | provider/eval/smoke scripts |
| high | `py/incomplete-url-substring-sanitization` | `scripts/github_oauth_smoke.py` |

This is the biggest production blocker. Green CodeQL workflow execution only proves analysis ran; it does not prove the code is secure.

## Current Working Tree Boundary

The local working tree is not release-frozen. Before this audit report was added, the dirty tree included:

- Modified docs and env examples: `.env.example`, `README.md`, `Docs/ARCHITECTURE.md`, `Docs/RUNBOOK.md`.
- Modified API/service/test files for prompt, GitHub, implementation, planning, draft PR, DB model, and tool registry behavior.
- Modified web style/UI files: `apps/web/app/components/ui/policy-toggle.tsx`, `apps/web/app/components/ui/threshold.tsx`, `apps/web/app/globals.css`.
- Untracked migration: `apps/api/alembic/versions/0007_issue_body_text.py`.
- Untracked web settings route: `apps/web/app/settings/`.

This does not mean the changes are bad. It means the release source boundary is not frozen, reviewed, committed, pushed, or reproducible from `main`.

## Evaluation State

Local eval reports exist under `Docs/eval-reports/`, including `v1-local-latest`.

The latest visible local eval report shows:

- `benchmark_task_count=31`.
- `task_pass_rate=1.0`.
- `patch_success_rate=0.1351`.
- `plan_approval_rate=0.4483`.
- `context_precision=0.0`.
- `provider_comparison_count=0`.
- `plan_quality_observed_count=0`.
- `patch_quality_observed_count=0`.

That is enough for a local harness demonstration, not enough for production claims. Provider-backed planning, retrieval, patch-attempt, and applied-patch eval reports are still missing from `Docs/eval-reports/`.

## Remaining P0 Blockers Before Production

1. Resolve or explicitly dismiss CodeQL alerts.
   - Fix SSRF, path injection, weak hashing, sensitive logging, redirect sanitization, ReDoS, and type/export alerts.
   - Re-run CodeQL and document zero critical/high open alerts, or document reviewed false positives with reasoning.

2. Freeze and publish the source boundary.
   - Review every dirty file.
   - Commit intentional changes.
   - Keep local-only style edits separate if they are unrelated.
   - Push to `main` or a reviewed PR.
   - Confirm no `.env`, `.local`, runtime secrets, caches, or generated artifacts are tracked.

3. Protect `main`.
   - Require PRs.
   - Require CI and CodeQL checks.
   - Require at least one approving review.
   - Block force pushes and deletions.
   - Consider signed commits or linear history after the RC stabilizes.

4. Enable continuous dependency security.
   - Add `.github/dependabot.yml`.
   - Enable Dependabot alerts and security updates.
   - Re-check the Dependabot API after enabling.
   - Fix or suppress dependency findings with documented rationale.

5. Produce real release artifacts.
   - Create an RC tag, for example `v1.0.0-rc.1`.
   - Run the release workflow with image publishing enabled.
   - Verify GHCR package visibility for API, web, and sandbox images.
   - Create GitHub release notes with image names, tags, digests, source SHA, and workflow URL.

6. Prove fresh-host install.
   - From a clean clone or different account/host, run source Compose.
   - From a clean clone or different account/host, run `make ghcr-start-local` against the published image tag.
   - Archive smoke evidence under `Docs/release-artifacts/` without secrets.

7. Close the provider-backed quality gap.
   - Run provider-backed planning evals.
   - Run provider-backed retrieval evals.
   - Run provider-backed patch-attempt evals.
   - Run provider-backed applied-patch evals.
   - Publish reports under `Docs/eval-reports/`.
   - Require quality gates for plan quality, patch quality, context precision, provider comparison count, and human edit distance.

8. Fix planning/RAG intent drift.
   - Reproduce the prompt-smoke failure where a documentation-only request produced a `smoke_app.py` plan.
   - Add tests that planner output must respect issue type and explicit "documentation-only" constraints.
   - Improve context selection so local smoke repositories do not dominate unrelated prompt intent.
   - Add a revise/clarify path when retrieved context is low-confidence or mismatched.

## Remaining P1 Work Before Public v1

1. Make Python dependency auditing reliable.
   - Fix the `pip-audit` temp-venv crash or use a pinned audit environment.
   - Add a lockfile strategy for API dependencies.
   - Add dependency audit output to release evidence.

2. Improve production readiness semantics.
   - Current local `/settings/readiness` reports `production_ready=true` for `oss-demo`.
   - Keep that local status, but ensure production profile blocks local managed secret keys, model fallback, missing OTEL, and unverified release proof.

3. Finish telemetry and operations proof.
   - Configure OTLP export in a non-local environment.
   - Capture trace evidence from webhook to draft PR.
   - Document log retention and artifact retention cleanup with Celery Beat.

4. Stabilize live GitHub smoke artifacts.
   - Decide whether PR #2 remains as public evidence or should be closed after documentation.
   - Keep a repeatable disposable demo repository path for future live smoke tests.
   - Avoid using the production source repo as the default smoke target after RC.

5. Complete browser QA.
   - Capture dashboard screenshots for desktop and mobile.
   - Verify settings, prompt entry, activity feed, run trace, analytics, security, PR summary, and eval views.
   - Check text overflow and visual polish after the current web style edits are reviewed.

6. Add repository rules and community automation.
   - Add labels and issue forms for bug, feature, security, and agent-task reports.
   - Add stale/triage automation only if it does not create noise for early contributors.
   - Add CODEOWNERS once maintainership is clear.

## Open-Source Surface Status

| Asset | Status |
| --- | --- |
| `LICENSE` | Present |
| `CONTRIBUTING.md` | Present |
| `CODE_OF_CONDUCT.md` | Present |
| `SECURITY.md` | Present |
| PR template | Present |
| Issue template | Present |
| Public roadmap | Present |
| Release checklist | Present |
| Release notes | Present |
| Deployment guide | Present |
| README RC language | Mostly correct; README and docs consistently avoid a final production-ready claim. |

## Acceptance Criteria Status

| Criterion | Status |
| --- | --- |
| Repo visibility is public | Pass |
| Latest CI remains green | Pass |
| CodeQL succeeds | Workflow pass |
| CodeQL alerts resolved | Fail |
| README/release notes say RC, not production-ready | Pass |
| No tracked secrets/local runtime files | Pass |
| Branch protection configured | Fail |
| GHCR fresh-host install complete | Fail |
| Credentialed GitHub write smoke complete | Partial pass |
| Provider evals complete | Fail |
| Full production dependency audit complete | Fail |
| Release tag and GitHub release exist | Fail |

## Recommended Next Sequence

1. Fix CodeQL P0 alerts first. This has the highest trust impact.
2. Split the dirty tree into reviewable commits or PRs.
3. Enable branch protection and Dependabot.
4. Create `v1.0.0-rc.1`, publish GHCR images, and verify packages from a clean environment.
5. Run fresh-host source Compose and GHCR Compose smoke tests.
6. Fix the prompt/planning drift and add regression tests around documentation-only prompts.
7. Run provider-backed evals and publish reports.
8. Only after those pass, consider `v1.0.0`.

## Verification Commands Run

```bash
gh repo view HarshalRane04/RepoPilot --json visibility,isPrivate,url,licenseInfo,hasIssuesEnabled,hasDiscussionsEnabled,defaultBranchRef
gh run list -R HarshalRane04/RepoPilot --branch main --limit 10
gh api repos/HarshalRane04/RepoPilot/code-scanning/alerts --paginate
gh api repos/HarshalRane04/RepoPilot/branches/main/protection
gh api repos/HarshalRane04/RepoPilot
gh release list -R HarshalRane04/RepoPilot --limit 20
gh api /users/HarshalRane04/packages/container/repopilot-api
gh api /users/HarshalRane04/packages/container/repopilot-web
gh api /users/HarshalRane04/packages/container/repopilot-sandbox
gh api repos/HarshalRane04/RepoPilot/dependabot/alerts --paginate

docker compose ps
docker compose config --quiet
curl -sS http://127.0.0.1:8000/health
curl -sS http://127.0.0.1:8000/settings/readiness
curl -sS http://127.0.0.1:3001/

PYTHONDONTWRITEBYTECODE=1 python3 scripts/release_hygiene.py --allow-warnings --allow-failures
PYTHONDONTWRITEBYTECODE=1 python3 scripts/deployment_validate.py --allow-warnings --allow-failures
PYTHONDONTWRITEBYTECODE=1 python3 scripts/ui_truth_guard.py
npm -C apps/web run typecheck
npm -C apps/web audit --omit=dev --audit-level=high
GITHUB_WRITES_ENABLED=false PYTHONDONTWRITEBYTECODE=1 uv run --with-requirements apps/api/requirements.txt python -m pytest apps/api/tests/test_phase9_implementation_agent.py apps/api/tests/test_phase10_to_13_services.py apps/api/tests/test_init_local_env.py apps/api/tests/test_api_routes.py apps/api/tests/test_tool_registry.py apps/api/tests/test_pr_summary_modes.py apps/api/tests/test_webhooks_and_triage.py -q
PYTHONDONTWRITEBYTECODE=1 uv run --with pip-audit pip-audit -r apps/api/requirements.txt

curl -sS -X POST http://127.0.0.1:8000/prompts ...
curl -sS -X POST http://127.0.0.1:8000/plans/e62e95bd-92fd-44b9-bc93-5d8c7f0fe695/reject ...
curl -sS 'http://127.0.0.1:8000/activity?limit=8'
curl -sS 'http://127.0.0.1:8000/runs?limit=5'
curl -sS 'http://127.0.0.1:8000/runs/8213de10-e7bd-4feb-8ea6-119b1382c481/trace'
```
