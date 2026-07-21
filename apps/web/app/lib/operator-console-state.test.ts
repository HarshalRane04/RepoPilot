import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { INITIAL_DASHBOARD_REQUEST_PATHS } from "../../lib/api.ts";
import type { ActivityItem, IssueResponse, PullRequestSummary, RunSummary } from "../../lib/api.ts";
import {
  activityNavigationTarget,
  activeRefreshKeys,
  boundedSearchQuery,
  ciAnalysisConclusion,
  completedRunStatistics,
  consoleHash,
  dashboardAttentionRecords,
  dashboardNavigationTarget,
  dispatchIssueQueueAction,
  evaluationEvidenceModel,
  formatUsd,
  formatUsdPerToken,
  issueQueueAction,
  issueQueueMutation,
  isCommandSearchShortcut,
  latestRepositoryIndexTimestamp,
  parseConsoleHash,
  parseStoredChecklist,
  providerHasConfiguredApiKey,
  reviewChecklistStorageKey,
  repositoryMatchesId,
  securityEvidencePresentation,
  validationEvidencePresentation,
  viewSupportsSearch
} from "./operator-console-state.ts";

const baseIssue: IssueResponse = {
  id: "issue-1",
  repository_id: "repo-1",
  number: 1,
  title: "Repair routing",
  issue_type: "bug",
  complexity: "medium",
  risk_score: 40,
  status: "agent_ready",
  created_at: "2026-07-13T00:00:00Z"
};

test("entity detail hashes round-trip identifiers for every audited entity", () => {
  const cases = [
    ["repository-detail", "repo/id", "repositories/repo%2Fid"],
    ["issue-detail", "issue id", "issues/issue%20id"],
    ["agent-runs", "run-1", "runs/run-1"],
    ["run-trace", "run-1", "runs/run-1/trace"],
    ["pull-request-detail", "pr-1", "pull-requests/pr-1"],
    ["security-detail", "finding-1", "security/finding-1"]
  ] as const;

  for (const [view, entityId, expectedHash] of cases) {
    const hash = consoleHash(view, { entityId });
    assert.equal(hash, expectedHash);
    assert.deepEqual(parseConsoleHash(`#${hash}`), { view, entityId, settingsTab: null });
  }
});

test("missing, malformed, legacy, and unknown hashes never select an implicit entity", () => {
  assert.deepEqual(parseConsoleHash("#issue-detail"), { view: "issue-detail", entityId: null, settingsTab: null });
  assert.deepEqual(parseConsoleHash("#repositories"), { view: "repositories", entityId: null, settingsTab: null });
  assert.deepEqual(parseConsoleHash("#runs"), { view: "dashboard", entityId: null, settingsTab: null });
  assert.deepEqual(parseConsoleHash("#not-a-route"), { view: "dashboard", entityId: null, settingsTab: null });
});

test("settings hashes preserve the selected tab", () => {
  assert.equal(consoleHash("settings", { settingsTab: "Tool Permissions" }), "settings/tool-permissions");
  assert.deepEqual(parseConsoleHash("#settings/tool-permissions"), {
    view: "settings",
    entityId: null,
    settingsTab: "Tool Permissions"
  });
});

test("dashboard task and timeline actions target the queue and identified run trace", () => {
  assert.deepEqual(dashboardNavigationTarget("view-all-tasks"), {
    view: "issues",
    entityId: null,
    issuesMode: "queue"
  });
  const timeline = dashboardNavigationTarget("open-full-timeline", "run-9");
  assert.deepEqual(timeline, { view: "run-trace", entityId: "run-9", issuesMode: null });
  assert.equal(consoleHash(timeline.view, { entityId: timeline.entityId }), "runs/run-9/trace");
});

test("task queue labels dispatch only their matching handler", () => {
  const called: string[] = [];
  const handlers = {
    generatePlan: () => called.push("generate"),
    approvePlan: () => called.push("approve"),
    openRun: (runId: string) => called.push(`run:${runId}`),
    openIssue: () => called.push("issue")
  };

  assert.deepEqual(issueQueueAction(baseIssue), { kind: "generate-plan", label: "Generate plan" });
  dispatchIssueQueueAction(baseIssue, handlers);

  const awaiting = {
    ...baseIssue,
    plan: { id: "plan-1", approval_status: "waiting_for_approval", version: 1, approved_at: null, plan: {} }
  };
  assert.deepEqual(issueQueueAction(awaiting), { kind: "approve-plan", label: "Approve plan" });
  dispatchIssueQueueAction(awaiting, handlers);

  const running = {
    ...awaiting,
    plan: { ...awaiting.plan, approval_status: "approved" },
    run: { id: "run-1", state: "WAIT_FOR_CI", total_tokens: 0, total_cost: 0, started_at: "2026-07-13T00:00:00Z", completed_at: null }
  };
  assert.deepEqual(issueQueueAction(running), { kind: "open-run", label: "Open run" });
  dispatchIssueQueueAction(running, handlers);

  const review = { ...awaiting, plan: { ...awaiting.plan, approval_status: "approved" } };
  assert.deepEqual(issueQueueAction(review), { kind: "open-issue", label: "Review issue" });
  dispatchIssueQueueAction(review, handlers);

  assert.deepEqual(called, ["generate", "approve", "run:run-1", "issue"]);
});

test("task queue mutations use the exact endpoint, method, and empty payload for their labels", () => {
  assert.deepEqual(issueQueueMutation(baseIssue, "generate-plan"), {
    method: "POST",
    path: "/issues/issue-1/plan",
    body: undefined
  });
  const awaiting = {
    ...baseIssue,
    plan: { id: "plan/1", approval_status: "draft", version: 1, approved_at: null, plan: {} }
  };
  assert.deepEqual(issueQueueMutation(awaiting, "approve-plan"), {
    method: "POST",
    path: "/plans/plan%2F1/approve",
    body: undefined
  });
});

test("PR activity records produce a concrete pull-request navigation target", () => {
  const item: ActivityItem = {
    source: "pull_request",
    action: "PR #3",
    status: "draft",
    created_at: "2026-07-13T00:00:00Z",
    entity_type: "pull_request",
    entity_id: "pr-3",
    metadata: {}
  };
  assert.deepEqual(activityNavigationTarget(item), { kind: "pull-request", entityId: "pr-3" });
});

function prFixture(overrides: Partial<PullRequestSummary> = {}): PullRequestSummary {
  return {
    pr_id: "pr-1",
    run_id: "run-1",
    pr_number: 1,
    url: "local://pr/1",
    pr_mode: "local_record",
    is_local_record: true,
    github_url: null,
    status: "draft",
    ci_status: null,
    risk_score: 20,
    created_at: "2026-07-13T00:00:00Z",
    issue: null,
    repository: null,
    plan: null,
    current_patch_hash: "patch-1",
    changed_files: [],
    planned_files: [],
    validation_results: [],
    security_findings: [],
    ...overrides
  };
}

test("validation success requires a complete, current, non-empty all-pass summary", () => {
  assert.equal(validationEvidencePresentation(prFixture()).state, "unknown");
  assert.equal(validationEvidencePresentation(prFixture({
    validation_evidence: { status: "not_run", patch_hash: "patch-1", total: 0, passed: 0, failed: 0, pending: 0, incomplete: 0 }
  })).state, "not_run");
  assert.equal(validationEvidencePresentation(prFixture({
    validation_evidence: { status: "pending", patch_hash: "patch-1", total: 2, passed: 1, failed: 0, pending: 1, incomplete: 0 }
  })).state, "pending");
  assert.equal(validationEvidencePresentation(prFixture({
    validation_evidence: { status: "failed", patch_hash: "patch-1", total: 2, passed: 1, failed: 1, pending: 0, incomplete: 0 }
  })).state, "failed");
  assert.equal(validationEvidencePresentation(prFixture({
    validation_evidence: { status: "passed", patch_hash: "old-patch", total: 1, passed: 1, failed: 0, pending: 0, incomplete: 0 }
  })).state, "incomplete");
  assert.equal(validationEvidencePresentation(prFixture({
    validation_evidence: { status: "passed", patch_hash: "patch-1", total: 2, passed: 2, failed: 0, pending: 0, incomplete: 0 }
  })).state, "passed");
});

test("security never becomes clear from an empty array without an explicit completed pass", () => {
  assert.equal(securityEvidencePresentation(prFixture()).state, "unknown");
  assert.equal(securityEvidencePresentation(prFixture({
    security_scan: { status: "not_run", completed: false, patch_hash: "patch-1", finding_count: 0, scanned_files: null, completed_at: null, sources: [] }
  })).state, "not_run");
  assert.equal(securityEvidencePresentation(prFixture({
    security_scan: { status: "passed", completed: false, patch_hash: "patch-1", finding_count: 0, scanned_files: 2, completed_at: null, sources: ["RUN_SECURITY_CHECKS"] }
  })).state, "incomplete");
  assert.equal(securityEvidencePresentation(prFixture({
    security_scan: { status: "passed", completed: true, patch_hash: "patch-1", finding_count: 1, scanned_files: 2, completed_at: "2026-07-13T00:01:00Z", sources: ["RUN_SECURITY_CHECKS"] },
    security_findings: [{ tool: "secret-scan", severity: "high", file_path: null, description: "secret", status: "open", patch_hash: "patch-1" }]
  })).state, "failed");
  assert.deepEqual(securityEvidencePresentation(prFixture({
    security_scan: { status: "passed", completed: true, patch_hash: "patch-1", finding_count: 0, scanned_files: 2, completed_at: "2026-07-13T00:01:00Z", sources: ["RUN_SECURITY_CHECKS"] }
  })), { state: "passed", label: "Clear", tone: "success", passed: true });
});

test("CI evidence preserves pending and unknown conclusions instead of coercing them to failure", () => {
  assert.equal(ciAnalysisConclusion("passed"), "success");
  assert.equal(ciAnalysisConclusion("failure"), "failure");
  assert.equal(ciAnalysisConclusion("pending"), "pending");
  assert.equal(ciAnalysisConclusion("running"), "pending");
  assert.equal(ciAnalysisConclusion("unsupported-provider-state"), "unknown");
  assert.equal(ciAnalysisConclusion(null), "unknown");
});

test("review checklist storage is scoped to PR and patch and ignores stale items", () => {
  const pr = prFixture();
  assert.equal(reviewChecklistStorageKey(pr), "repopilot-review-checklist:pr-1:patch-1");
  assert.deepEqual([...parseStoredChecklist('["Keep", "Stale", 42]', ["Keep", "Other"])], ["Keep"]);
  assert.deepEqual([...parseStoredChecklist("not-json", ["Keep"])], []);
});

test("live runtime statistics include only valid completed runs", () => {
  const run = (id: string, startedAt: string, completedAt: string | null, totalCost: number): RunSummary => ({
    id,
    issue_id: null,
    plan_id: null,
    state: completedAt ? "READY_FOR_REVIEW" : "WAIT_FOR_CI",
    model_used: "mock",
    total_tokens: 0,
    total_cost: totalCost,
    started_at: startedAt,
    completed_at: completedAt,
    latest_step: null,
    latest_step_status: null,
    validation_statuses: []
  });
  const stats = completedRunStatistics([
    run("a", "2026-07-13T00:00:00Z", "2026-07-13T00:10:00Z", 1),
    run("b", "2026-07-13T00:00:00Z", "2026-07-13T00:20:00Z", 3),
    run("unfinished", "2020-01-01T00:00:00Z", null, 100),
    run("invalid", "not-a-date", "2026-07-13T00:00:00Z", 100),
    run("negative", "2026-07-13T01:00:00Z", "2026-07-13T00:00:00Z", 100)
  ]);
  assert.deepEqual(stats, {
    completedCount: 2,
    excludedCount: 3,
    averageDurationMs: 900000,
    averageRuntimeLabel: "15m 0s",
    averageCost: 2
  });
  assert.equal(completedRunStatistics([run("pending", "2020-01-01T00:00:00Z", null, 1)]).averageRuntimeLabel, "Unavailable");

  const model = evaluationEvidenceModel({
    id: "eval-1",
    benchmark_version: "fixture-v3",
    metrics: { benchmark_task_count: 20, fixture_repository_count: 2 },
    report_uri: null,
    created_at: "2026-07-12T12:00:00Z"
  }, 99, [run("live", "2026-07-13T00:00:00Z", "2026-07-13T00:01:00Z", 4)]);
  assert.deepEqual(model.historical, {
    available: true,
    benchmarkVersion: "fixture-v3",
    generatedAt: "2026-07-12T12:00:00Z",
    benchmarkTaskCount: 20,
    fixtureRepositoryCount: 2
  });
  assert.equal(model.live.connectedRepositoryCount, 99);
  assert.equal(model.live.completedCount, 1);
  assert.equal(evaluationEvidenceModel(null, 3, []).historical.available, false);
});

test("canonical repository aliases support stable filtering and latest sync evidence", () => {
  const repository = {
    id: "repo-app",
    canonical_id: "octo/demo",
    alias_ids: ["repo-app", "repo-oauth"],
    owner: "octo",
    name: "demo",
    default_branch: "main",
    last_indexed_sha: null,
    issue_count: 2,
    indexed_at: "2026-07-13T08:00:00Z"
  };
  assert.equal(repositoryMatchesId(repository, "repo-app"), true);
  assert.equal(repositoryMatchesId(repository, "repo-oauth"), true);
  assert.equal(repositoryMatchesId(repository, "another-repo"), false);
  assert.equal(latestRepositoryIndexTimestamp([
    repository,
    { ...repository, id: "older", indexed_at: "2026-07-12T08:00:00Z" },
    { ...repository, id: "invalid", indexed_at: "not-a-date" }
  ]), "2026-07-13T08:00:00Z");
});

test("needs-attention records deduplicate issue, run, and PR lifecycle aliases before slicing", () => {
  const issue = {
    ...baseIssue,
    plan: { id: "plan-1", approval_status: "waiting_for_approval", version: 1, approved_at: null, plan: {} }
  };
  const run: RunSummary = {
    id: "run-1",
    issue_id: issue.id,
    plan_id: "plan-1",
    state: "FAILED",
    model_used: "mock",
    total_tokens: 0,
    total_cost: 0,
    started_at: "2026-07-13T00:00:00Z",
    completed_at: "2026-07-13T00:01:00Z",
    latest_step: null,
    latest_step_status: null,
    validation_statuses: []
  };
  const pr = prFixture({
    run_id: run.id,
    ci_status: "failure",
    issue: { id: issue.id, number: issue.number, title: issue.title, status: issue.status }
  });
  const separateIssue = { ...baseIssue, id: "issue-2", number: 2, title: "Separate approval", plan: issue.plan };

  const records = dashboardAttentionRecords([issue, separateIssue], [run], [pr]);

  assert.equal(records.length, 2);
  assert.equal(records[0]?.kind, "pull-request");
  assert.equal(records[0]?.detail, "CI failed");
  assert.equal(records[1]?.entityId, "issue-2");
});

test("active refresh manifests include every visible dependency", () => {
  const repositoryKeys = activeRefreshKeys("repository-detail");
  assert.equal(repositoryKeys.has("runs"), true);
  assert.equal(repositoryKeys.has("issues"), true);
  assert.equal(repositoryKeys.has("pullRequests"), true);
  assert.equal(repositoryKeys.has("installations"), true);

  const evaluationKeys = activeRefreshKeys("evaluations");
  assert.equal(evaluationKeys.has("evalReports"), true);
  assert.equal(evaluationKeys.has("repositories"), true);
  assert.equal(evaluationKeys.has("runs"), true);

  const securityKeys = activeRefreshKeys("security");
  assert.equal(securityKeys.has("policy"), true);
  assert.equal(securityKeys.has("securityFindings"), true);

  const profileKeys = activeRefreshKeys("profile");
  assert.equal(profileKeys.has("activitySummary"), true);

  assert.equal(activeRefreshKeys("settings", "Models").has("modelCatalog"), true);
  assert.equal(activeRefreshKeys("settings", "GitHub").has("installations"), true);
});

test("search shortcuts are bounded, cross-platform, and limited to searchable views", () => {
  assert.equal(isCommandSearchShortcut({ key: "k", metaKey: true }), true);
  assert.equal(isCommandSearchShortcut({ key: "K", ctrlKey: true }), true);
  assert.equal(isCommandSearchShortcut({ key: "k", metaKey: true, altKey: true }), false);
  assert.equal(isCommandSearchShortcut({ key: "j", metaKey: true }), false);
  assert.equal(boundedSearchQuery("abcdef", 4), "abcd");
  assert.equal(viewSupportsSearch("repositories"), true);
  assert.equal(viewSupportsSearch("settings"), false);
});

test("provider-reported costs and catalog rates are formatted explicitly as USD", () => {
  assert.equal(formatUsd(0), "$0.00");
  assert.equal(formatUsd(1.23456789), "$1.23456789");
  assert.equal(formatUsd(-1), "Unavailable");
  assert.equal(formatUsdPerToken("0.00000125"), "$0.00000125/token");
  assert.equal(formatUsdPerToken("unknown"), null);
});

test("configured provider API key state follows the selected provider only", () => {
  const configuredProviders = ["openrouter"];
  assert.equal(providerHasConfiguredApiKey(configuredProviders, "openrouter"), true);
  assert.equal(providerHasConfiguredApiKey(configuredProviders, "OpenRouter"), true);
  assert.equal(providerHasConfiguredApiKey(configuredProviders, "anthropic"), false);
  assert.equal(providerHasConfiguredApiKey([], "openrouter"), false);
  assert.equal(providerHasConfiguredApiKey(configuredProviders, null), false);

  const source = readFileSync(new URL("../operator-console.tsx", import.meta.url), "utf8");
  assert.equal(source.includes("config?.configured_api_key_providers"), true);
  assert.equal(source.includes("placeholder={selectedProviderHasConfiguredKey"), true);
  assert.equal(source.includes("config?.api_key_configured ? \"Already configured"), false);
});

test("audited controls retain native button/list semantics and explicit tab/select names", () => {
  const source = readFileSync(new URL("../operator-console.tsx", import.meta.url), "utf8");
  assert.equal(source.includes('role="listitem"'), false);
  assert.equal(source.includes('role="tablist"'), true);
  assert.equal(source.includes("aria-selected={"), true);
  assert.equal(source.includes('aria-label="Filter tasks by repository"'), true);
  assert.equal(source.includes('aria-label="Filter reviews by CI status"'), true);
  assert.equal(source.includes('aria-label="Filter audit records by risk"'), true);
});

test("initial request manifest excludes unused telemetry and the deferred model catalog", () => {
  const paths: string[] = Object.values(INITIAL_DASHBOARD_REQUEST_PATHS);
  assert.equal(paths.includes("/health"), false);
  assert.equal(paths.includes("/metrics/overview"), false);
  assert.equal(paths.includes("/webhooks/events"), false);
  assert.equal(paths.includes("/settings/models/catalog"), false);
  assert.equal(INITIAL_DASHBOARD_REQUEST_PATHS.activities, "/activity?limit=20");
});
