# RepoPilot Functionality Remediation Report

Date: 2026-07-13
Scope: frontend operator console and the backend contracts that supply its evidence
Status: complete

## Executive outcome

The audited operator-console remediation is complete across all five planned phases. The implementation now preserves entity identity in deep links, dispatches actions to the mutation they advertise, presents conservative validation/security evidence, separates historical evaluation reports from live telemetry, canonicalizes duplicate GitHub identities, refreshes only relevant dependencies, reports currency explicitly, and exposes accessible, truthful controls.

The work also removed redundant or unconsumed frontend behavior: the duplicate Suggested Improvements block is gone; unused health, metrics, and webhook-event requests are no longer fetched or polled; the large model catalog is deferred until the Models settings tab is opened; and default refresh no longer refetches every hidden screen.

All required automated checks, the production web build, browser interaction paths, console-log review, and payload measurements passed.

## Baseline

The required pre-change checks were run against the existing dirty worktree before this remediation began.

| Command | Baseline result |
| --- | --- |
| `make api-test` | Passed: 329 tests; one Starlette/httpx deprecation warning |
| `make api-lint` | Passed |
| `pnpm -C apps/web typecheck` | Passed |
| `python3 scripts/ui_truth_guard.py` | Passed |

The baseline suite did not cover the audited navigation, action mapping, evidence-state, calculation, refresh, search, payload, or accessibility defects. This remediation adds 19 focused frontend cases and expands the API suite from 329 to 342 passing tests.

## Finding-to-code-to-test checklist

| Phase | Reproduced finding | Implemented remediation | Regression proof | Status |
| --- | --- | --- | --- | --- |
| 1 | Detail hashes carried only a view name and selected entities fell back to the first array item after reload or for stale IDs. | Identifier-bearing routes and strict parsing for repositories, issues, runs/traces, pull requests, and security findings; no implicit entity fallback; requested details hydrate by ID. | Frontend route round-trip and invalid/stale-ID tests; browser reload of a repository deep link; stale-ID not-found check. | Complete |
| 1 | Task Queue labels could advertise approve/run/review while every row invoked plan generation. | A typed action decision now maps each label to exactly one handler and mutation contract. | Frontend dispatch and endpoint/method/payload tests. | Complete |
| 1 | Dashboard task/timeline actions and PR activity routed to incomplete or unrelated destinations. | Queue actions target `#issues`, timelines target `#runs/<id>/trace`, and PR activity targets `#pull-requests/<id>`. | Frontend target tests and browser navigation for queue, trace, and PR activity. | Complete |
| 2 | Any passed validation produced a pass; empty security arrays appeared clear; readiness did not prove a scan completed. | Explicit validation and security evidence summaries require current, non-empty, all-applicable success and a completed current-patch security scan. | API evidence-state matrix and CI-readiness tests; frontend presentation tests. | Complete |
| 2 | Pending and unsupported CI states were coerced to failure. | CI contracts and analyzer logic preserve `pending` and `unknown`; trusted failure remains distinct. | API pending/unknown and trusted-failure tests; frontend conclusion tests. | Complete |
| 2 | CI `failure` normalization was inconsistent and reviewer checklists disappeared on navigation. | Status normalization is centralized; checklist state is persisted under a PR-and-patch-scoped key and stale items are rejected. | Frontend CI/checklist tests and browser PR-detail checks. | Complete |
| 3 | Evaluation cards mixed historical report data with live repository/run data; unfinished runs inflated runtime averages. | Historical evaluation reports and live operations are separate models/sections; runtime and cost averages include only valid completed runs. | Frontend evaluation-model and completed-run-statistics tests; browser section-separation check. | Complete |
| 3 | Audit rows mislabeled source as actor, invented Low risk for absent evidence, and hid pagination/completeness. | Authoritative `/activity/audit` contract includes actor type/ID, explicit result, nullable risk, total/offset/limit/has-more/completeness, and full timestamps. | API audit fixture tests and browser audit-trail check. | Complete |
| 4 | OAuth and GitHub App aliases duplicated the same repository/account and inflated counts. | Case-insensitive owner/name and account grouping prefer a writable GitHub App alias while preserving canonical and alias IDs/source metadata. | API repository/installation identity tests; frontend alias-aware filtering test; browser owner/name table check. | Complete |
| 4 | Profile approvals were counted from the current activity page. | `/activity/summary` computes complete aggregate counts independently of activity-page limits. | API summary-contract test and protected-route coverage. | Complete |
| 4 | Refresh dependencies omitted PRs, runs, repositories, policy, and the shared run header in affected views. | Active-view request manifests include each visible dependency and shared run data while avoiding unrelated screens. | Frontend refresh-manifest cases for affected views. | Complete |
| 5 | Profile-to-GitHub navigation wrote a stale tab; Command-K had no behavior; hidden search state survived route changes. | Settings tab selection updates state/hash atomically; Command-K focuses supported search; queries are bounded and cleared across routes. | Frontend settings/search tests and browser profile-to-GitHub plus Command-K checks. | Complete |
| 5 | Repository search was read-only and duplicate/raw arrays drove filtering. | Editable bounded search, Escape/clear behavior, and canonical alias-aware results. | Frontend search/canonical tests and browser search interaction. | Complete |
| 5 | Provider/run costs used an INR symbol without conversion even though source evidence is USD. | USD formatters, explicit `cost_currency`, model `pricing_currency`/`pricing_unit`, and policy cost currency/limit. | Frontend formatting test; API model-catalog and runtime-policy endpoint assertions. | Complete |
| 5 | Selects lacked accessible names; buttons overrode list semantics; tabs lacked state; chevrons/breadcrumbs implied unavailable interaction. | Named controls, native list/button semantics, selected tabs/tabpanels, pressed segments, actionable-only chevrons, and real breadcrumb links. | Frontend source guard, TypeScript/build checks, and browser accessibility snapshot. | Complete |
| 5 | Unused telemetry was fetched/polled and the full live model catalog was embedded in the initial SSR payload. | Removed unconsumed frontend requests/state; deferred model catalog with explicit idle/loading/error/ready states; reduced initial activity limit to 20. | Request-manifest test, consumer search, production build, and response-size measurements. | Complete |
| Follow-up | Repository View issues lost repository context; Last full sync showed a SHA; Needs attention counted a slice and duplicated lifecycle records. | Repository-filtered issue navigation, newest index timestamp, and full issue/run/PR lifecycle deduplication before counting/slicing. | Frontend canonical/timestamp/attention tests and browser repository-to-issues check. | Complete |
| Follow-up | Suggested Improvements duplicated Issue Queue; settings promised editing that does not exist; Docs linked to a nonexistent repository. | Removed the redundant section, made read-only copy explicit, and corrected Docs to the real repository. | Source review, frontend guard, browser settings review, and production build. | Complete |

## Phase 1: identity-safe routing and honest actions

### Root causes

- Hash state encoded a screen but not the selected entity.
- Selected-record expressions used `array[0]` as a universal fallback.
- Queue presentation and mutation selection were separate, allowing labels and behavior to drift.
- Activity navigation lacked an entity-aware PR branch.

### Changes

- Added pure route parsing/building and action helpers in `apps/web/app/lib/operator-console-state.ts`.
- Updated `apps/web/app/operator-console.tsx` to use identifier-bearing hashes and hydrate deep-linked entities.
- Added backend `GET /repos/{id}`; aliases are accepted and resolved to the canonical response.
- Made dashboard queue, trace, and PR activity navigation explicit.
- Routed Task Queue actions through typed handlers and exact request definitions.

### Result

Reloading an identified detail view preserves the same entity. Missing, malformed, legacy, or stale IDs show an explicit unavailable/not-found state rather than silently opening unrelated data. The action a user reads is the action dispatched.

## Phase 2: conservative evidence and CI semantics

### Root causes

- JavaScript `some()` and vacuous `every()` semantics turned partial or empty evidence into success.
- Backend readiness checked only for at least one validation pass and absence of a high finding.
- CI requests lacked pending/unknown values.
- Review checklist state was component-local and unscoped.

### Changes

- Added `apps/api/app/services/evidence_state.py` as the shared validation/security evidence authority.
- Expanded pull-request summary contracts with current patch, validation summary, and security-scan evidence.
- Required every applicable current validation to pass, a completed current security scan, and no blocking finding before readiness.
- Preserved pending/unknown CI conclusions through request validation and analysis.
- Stored checklist selections by PR ID plus patch hash and discarded stale selections.

### Result

Empty, unavailable, pending, incomplete, mixed, stale-patch, and failed evidence remains non-passing. RepoPilot now claims Passed/Clear only when the backend can identify complete evidence for the current patch.

## Phase 3: trustworthy audit and evaluation calculations

### Root causes

- The UI repurposed generic activity fields as audit identity/risk evidence.
- Absent risk was converted to zero.
- Activity pagination limits were invisible.
- Live unfinished durations used the current time and contaminated averages.

### Changes

- Added `AuditLogItem`, `AuditLogPage`, and `ActivitySummaryResponse` shared contracts.
- Added `GET /activity/audit` with explicit actors, outcomes, nullable risk, pagination, and completeness.
- Separated historical evaluation report metrics from the current live-operations snapshot.
- Centralized completed-run statistics and excluded unfinished, reversed, and invalid durations.

### Result

Unknown audit risk remains Unknown, timestamps are complete, and the UI discloses whether the shown audit page is complete. Historical reports are no longer presented as if they describe the current live dataset.

## Phase 4: canonical identity, complete counts, and dependency refresh

### Root causes

- Provider-specific record IDs were treated as GitHub identity.
- Counts and filters consumed raw arrays.
- Profile totals depended on a capped activity page.
- Refresh keys modeled screen names rather than the data visible on each screen.

### Changes

- Canonicalized repositories case-insensitively by owner/name; canonicalized accounts/installations case-insensitively by account identity.
- Prefer the writable GitHub App record while preserving `canonical_id`, `alias_ids`, source aliases, installation aliases, and newest indexing evidence.
- Count open issues uniquely by issue number within each canonical repository.
- Added complete backend activity aggregates.
- Made frontend selection/filtering alias-aware and repository rows owner-qualified.
- Expanded active refresh keys for every visible dependency and immediate view/tab refresh.
- Deduplicated Needs attention across issue, run, and PR lifecycle aliases before total calculation and slicing.

### Result

OAuth/App duplicates no longer inflate logical repository/account counts. Distinct repositories with the same name but different owners remain distinct and visibly owner-qualified.

## Phase 5: practical usability, currency, accessibility, and payload efficiency

### Changes

- Implemented cross-platform Command-K search focus only on searchable views.
- Made repository search editable, bounded to 120 characters, clearable, and Escape-cancellable.
- Fixed profile-to-GitHub settings navigation.
- Added exact USD and USD-per-token formatting; API run, trace, catalog, and runtime-policy responses now state currency/unit explicitly.
- Added accessible names to audited selects, native list/button semantics, tab state, pressed state, real breadcrumb links, and actionable-only chevrons.
- Removed frontend health/metrics/webhook-event fetches after confirming they had no UI consumer. The backend endpoints remain available.
- Deferred model-catalog retrieval until the Models tab and represented idle/loading/error/ready states.
- Reduced initial activity retrieval from 160 to 20 records.
- Changed refresh from broad polling to active-view dependency refresh.
- Removed the redundant Suggested Improvements section and unused presentation helpers.
- Stopped labelling terminal runs as active and removed unrelated fallback activity from the dashboard.

### Result

The console performs less background work, embeds substantially less data in the first HTML response, communicates state more truthfully, and is operable with clearer native accessibility semantics.

## Intentional behavior and contract changes

- Detail URLs now include entity IDs. Legacy detail-only hashes no longer select the first record.
- `GET /repos/{id}`, `GET /activity/audit`, and `GET /activity/summary` are new authenticated read endpoints.
- Repository and installation list responses are canonicalized; callers receive preferred records plus alias metadata instead of provider duplicates.
- Pull-request summaries add explicit validation/security evidence and patch provenance.
- CI analysis accepts and preserves `pending` and `unknown`.
- Run and LLM-trace contracts report `cost_currency: "USD"`.
- Dynamic model entries report `pricing_currency: "USD"` and `pricing_unit: "token"`.
- Runtime policy reports `max_cost_per_run` with `cost_currency: "USD"`.
- The model catalog is no longer part of initial server-rendered operator data and loads only when required.
- Default refresh updates only the active view and its shared dependencies.
- Unconsumed frontend telemetry polling and the duplicate Suggested Improvements UI were removed.

All contract additions are additive at the schema level. Canonicalized list cardinality and legacy hash fallback behavior are deliberate semantic changes.

## Files changed for this remediation

The worktree contained broad pre-existing edits. The files below are the implementation and regression surfaces intentionally touched for this audited remediation; this list does not claim ownership of unrelated changes elsewhere in the dirty worktree.

### Frontend

- `apps/web/app/operator-console.tsx` — routing, hydration, actions, evidence presentation, canonical selection/counts, evaluation/audit separation, refresh, search, settings, currency, accessibility, and dead-UI removal.
- `apps/web/app/lib/operator-console-state.ts` — pure route, action, identity, attention, refresh, search, currency, evidence, checklist, and calculation helpers.
- `apps/web/app/lib/operator-console-state.test.ts` — 19 focused frontend regression cases.
- `apps/web/lib/api.ts` — new/expanded contracts, request manifest, deferred catalog loading, audit/activity summary, repository detail, and removed unused requests.
- `apps/web/app/globals.css` — interactive breadcrumb, tab, search, and accessible-control styling required by the corrected semantics.
- `apps/web/package.json` and `apps/web/tsconfig.json` — deterministic Node test entrypoint and TypeScript support for the pure helper test module.

### API and shared contracts

- `apps/api/app/api/routes/activity.py` — authoritative audit page and complete activity aggregates.
- `apps/api/app/api/routes/installations.py` — canonical account/installation grouping and unique repository counts.
- `apps/api/app/api/routes/repos.py` — canonical repositories, alias preservation, detail lookup, unique issue counts, and newest indexing evidence.
- `apps/api/app/api/routes/prs.py` — explicit validation/security evidence in PR summaries.
- `apps/api/app/api/routes/issues.py` — explicit run cost currency in nested issue data.
- `apps/api/app/api/routes/settings.py` — runtime cost limit/currency response.
- `apps/api/app/services/evidence_state.py` — conservative validation and security evidence authority.
- `apps/api/app/services/ci_analyzer.py` — all-applicable readiness and pending/unknown CI behavior.
- `apps/api/app/services/model_catalog.py` — explicit dynamic pricing currency/unit metadata.
- `packages/shared_contracts/repopilot_contracts/models.py` and `packages/shared_contracts/repopilot_contracts/__init__.py` — audit, activity-summary, evidence, CI, and USD cost contracts/exports.

### API regression tests and documentation

- `apps/api/tests/test_activity_audit.py`
- `apps/api/tests/test_evidence_state.py`
- `apps/api/tests/test_phase8_ci_revision.py`
- `apps/api/tests/test_repository_identity.py`
- `apps/api/tests/test_api_routes.py`
- `Docs/FUNCTIONALITY_REMEDIATION_REPORT_2026-07-13.md`

## Automated verification

| Command | Final result |
| --- | --- |
| `make api-test` | Passed: 342 tests; one Starlette/httpx deprecation warning |
| `make api-lint` | Passed: Ruff reports all checks passed |
| `pnpm -C apps/web test` | Passed: 19 tests |
| `pnpm -C apps/web typecheck` | Passed |
| `python3 scripts/ui_truth_guard.py` | Passed |
| `make web-build` | Passed: production runner image `repopilot-web:verify` built |
| `git diff --check` | Passed |

Focused API coverage lives in:

- `apps/api/tests/test_activity_audit.py`
- `apps/api/tests/test_evidence_state.py`
- `apps/api/tests/test_phase8_ci_revision.py`
- `apps/api/tests/test_repository_identity.py`
- `apps/api/tests/test_api_routes.py`

Focused frontend coverage lives in `apps/web/app/lib/operator-console-state.test.ts`.

## Browser QA

The local application was exercised through the in-app browser against the running frontend/API:

1. View all tasks opened `#issues` and the Task Queue.
2. Command-K focused the current-view search; switching to Settings cleared the query and disabled unsupported search.
3. Settings → Models lazy-loaded the model catalog and exposed loading/ready behavior.
4. Profile → Manage GitHub access opened `#settings/github` with GitHub selected.
5. Repository search filtered results and Escape cleared the query.
6. Repository rows displayed owner/name, opened `#repositories/<id>`, and preserved the same entity after reload.
7. A stale repository ID rendered an explicit not-found state with no first-record fallback.
8. View issues opened `#issues` with the repository filter selected.
9. Open full timeline opened `#runs/<id>/trace` with Timeline selected.
10. PR activity opened the identified pull-request detail.
11. Audit trail displayed completeness metadata, Unknown risk, and a named risk filter.
12. Evaluations displayed distinct historical-report and live-operation sections.
13. Browser error and warning logs were empty during the audited flows.

## Initial-payload measurement

Measurements are raw response bytes for the local fixture environment, not compressed transfer size or JavaScript bundle size.

| Response | Before | After | Change |
| --- | ---: | ---: | ---: |
| Initial frontend HTML `/` | 350,883 bytes | 196,184 bytes | -154,699 bytes (-44.1%) |
| Deferred `/settings/models/catalog` | Included in initial data | 113,899 bytes on Models-tab demand | Removed from initial response |
| Initial `/activity?limit=20` | Previously requested at limit 160 | 5,987 bytes | Bounded initial activity page |
| `/repos` | — | 12,904 bytes | Canonicalized repository fixture |
| `/activity/summary` | — | 93 bytes | Complete compact aggregates |

The current initial HTML returned HTTP 200 and did not contain the `modelCatalog` payload. Model identifiers that remain in the HTML come from actual run/configuration/readiness records, not the deferred catalog.

## Removed redundancy and dead behavior

- Removed the duplicate Suggested Improvements block that repeated Issue Queue without independent evidence.
- Removed unconsumed frontend health, metrics-overview, and webhook-event state/fetch/poll paths. Their API endpoints were not deleted.
- Removed unused `securityTone`, `securityLabel`, and `metadataRisk` presentation helpers.
- Removed implicit first-entity fallback behavior.
- Removed broad hidden-view refresh as the default.
- Removed unrelated dashboard activity fallback and terminal-run “Active run” overclaim.

## Remaining risks and non-blocking follow-ups

- The repository was already broadly dirty before this remediation. This report identifies the audited surfaces and verification results but does not attribute every pre-existing worktree change to this phase.
- The API suite still emits the existing Starlette/httpx TestClient deprecation warning. It does not affect the green result, but the dependency/test-client migration should be scheduled.
- Repository canonicalization currently uses case-insensitive owner/name because the persistence model does not expose GitHub's immutable numeric repository ID across every provider source. Adding that ID and backfilling it would make identity robust to repository renames/transfers.
- Browser QA used local fixture data and read-only flows. Live GitHub write operations and external provider uptime were intentionally not exercised.
- Payload byte counts vary with fixture cardinality and catalog contents; the durable regression guard is the initial request manifest test plus exclusion of the model catalog from server-rendered data.

No blocker remains for the audited five-phase scope.
