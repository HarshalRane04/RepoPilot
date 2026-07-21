import type {
  ActivityItem,
  EvalReport,
  IssueResponse,
  OperatorData,
  PullRequestSummary,
  RepositoryResponse,
  RunSummary
} from "../../lib/api.ts";

export type View =
  | "landing"
  | "connect"
  | "setup"
  | "dashboard"
  | "new-task"
  | "repositories"
  | "repository-detail"
  | "issues"
  | "issue-detail"
  | "agent-runs"
  | "run-trace"
  | "pull-requests"
  | "pull-request-detail"
  | "security"
  | "security-detail"
  | "evaluations"
  | "audit-logs"
  | "settings"
  | "profile";

export const SETTINGS_TABS = ["GitHub", "Models", "Policies", "Tool Permissions", "Cost Limits", "Display"] as const;
export type SettingsTab = (typeof SETTINGS_TABS)[number];

export type ConsoleRoute = {
  view: View;
  entityId: string | null;
  settingsTab: SettingsTab | null;
};

const TOP_LEVEL_VIEWS = new Set<View>([
  "landing",
  "connect",
  "setup",
  "dashboard",
  "new-task",
  "repositories",
  "issues",
  "agent-runs",
  "pull-requests",
  "security",
  "evaluations",
  "audit-logs",
  "settings",
  "profile"
]);

const LEGACY_DETAIL_VIEWS = new Set<View>([
  "repository-detail",
  "issue-detail",
  "run-trace",
  "pull-request-detail",
  "security-detail"
]);

export function parseConsoleHash(hash: string): ConsoleRoute {
  const rawPath = hash.replace(/^#/, "").split("?", 1)[0]?.replace(/^\/+|\/+$/g, "") ?? "";
  const segments = rawPath.split("/").filter(Boolean).map(safeDecode);
  const first = segments[0] ?? "dashboard";

  if (first === "settings") {
    return { view: "settings", entityId: null, settingsTab: settingsTabFromSlug(segments[1]) };
  }
  if (first === "repositories" && segments.length > 1) {
    return { view: "repository-detail", entityId: segments[1] || null, settingsTab: null };
  }
  if (first === "issues" && segments.length > 1) {
    return { view: "issue-detail", entityId: segments[1] || null, settingsTab: null };
  }
  if (first === "runs" && segments.length > 1) {
    return {
      view: segments[2] === "trace" ? "run-trace" : "agent-runs",
      entityId: segments[1] || null,
      settingsTab: null
    };
  }
  if (first === "pull-requests" && segments.length > 1) {
    return { view: "pull-request-detail", entityId: segments[1] || null, settingsTab: null };
  }
  if (first === "security" && segments.length > 1) {
    return { view: "security-detail", entityId: segments[1] || null, settingsTab: null };
  }

  if (TOP_LEVEL_VIEWS.has(first as View)) {
    return { view: first as View, entityId: null, settingsTab: null };
  }
  if (LEGACY_DETAIL_VIEWS.has(first as View)) {
    // Keep old bookmarks deterministic: a legacy detail hash is a missing-ID
    // route, never permission to substitute the first entity in a collection.
    return { view: first as View, entityId: null, settingsTab: null };
  }
  return { view: "dashboard", entityId: null, settingsTab: null };
}

export function consoleHash(
  view: View,
  options: { entityId?: string | null; settingsTab?: SettingsTab | null } = {}
): string {
  const entityId = options.entityId ? encodeURIComponent(options.entityId) : null;
  switch (view) {
    case "repository-detail":
      return entityId ? `repositories/${entityId}` : "repository-detail";
    case "issue-detail":
      return entityId ? `issues/${entityId}` : "issue-detail";
    case "agent-runs":
      return entityId ? `runs/${entityId}` : "agent-runs";
    case "run-trace":
      return entityId ? `runs/${entityId}/trace` : "run-trace";
    case "pull-request-detail":
      return entityId ? `pull-requests/${entityId}` : "pull-request-detail";
    case "security-detail":
      return entityId ? `security/${entityId}` : "security-detail";
    case "settings":
      return `settings/${settingsSlug(options.settingsTab ?? "GitHub")}`;
    default:
      return view;
  }
}

export function settingsSlug(tab: SettingsTab): string {
  return tab.toLowerCase().replace(/\s+/g, "-");
}

export function settingsTabFromSlug(slug: string | undefined): SettingsTab | null {
  if (!slug) return null;
  const normalized = slug.toLowerCase();
  return SETTINGS_TABS.find((tab) => settingsSlug(tab) === normalized) ?? null;
}

export function dashboardNavigationTarget(
  action: "view-all-tasks" | "open-full-timeline",
  entityId?: string
): { view: "issues" | "run-trace"; entityId: string | null; issuesMode: "queue" | null } {
  if (action === "view-all-tasks") {
    return { view: "issues", entityId: null, issuesMode: "queue" };
  }
  if (!entityId) throw new Error("A run identifier is required to open the full timeline.");
  return { view: "run-trace", entityId, issuesMode: null };
}

export type IssueQueueAction =
  | { kind: "generate-plan"; label: "Generate plan" }
  | { kind: "approve-plan"; label: "Approve plan" }
  | { kind: "open-run"; label: "Open run" }
  | { kind: "open-issue"; label: "Review issue" };

export function issueQueueAction(issue: IssueResponse): IssueQueueAction {
  if (!issue.plan) return { kind: "generate-plan", label: "Generate plan" };
  if (isAwaitingApproval(issue.plan.approval_status)) return { kind: "approve-plan", label: "Approve plan" };
  if (issue.run) return { kind: "open-run", label: "Open run" };
  return { kind: "open-issue", label: "Review issue" };
}

export type IssueQueueHandlers = {
  generatePlan: (issue: IssueResponse) => void;
  approvePlan: (issue: IssueResponse) => void;
  openRun: (runId: string) => void;
  openIssue: (issue: IssueResponse) => void;
};

export type IssueQueueMutation = {
  method: "POST";
  path: string;
  body: undefined;
};

export function issueQueueMutation(issue: IssueResponse, kind: "generate-plan" | "approve-plan"): IssueQueueMutation {
  if (kind === "generate-plan") {
    return { method: "POST", path: `/issues/${encodeURIComponent(issue.id)}/plan`, body: undefined };
  }
  if (!issue.plan) {
    throw new Error("Cannot approve a task without a plan identifier.");
  }
  return { method: "POST", path: `/plans/${encodeURIComponent(issue.plan.id)}/approve`, body: undefined };
}

export function dispatchIssueQueueAction(issue: IssueResponse, handlers: IssueQueueHandlers): IssueQueueAction {
  const action = issueQueueAction(issue);
  switch (action.kind) {
    case "generate-plan":
      handlers.generatePlan(issue);
      break;
    case "approve-plan":
      handlers.approvePlan(issue);
      break;
    case "open-run":
      handlers.openRun(issue.run!.id);
      break;
    case "open-issue":
      handlers.openIssue(issue);
      break;
  }
  return action;
}

export type ActivityNavigationTarget = {
  kind: "issue" | "run" | "pull-request";
  entityId: string;
};

export function activityNavigationTarget(item: ActivityItem): ActivityNavigationTarget | null {
  if (!item.entity_id) return null;
  if (item.entity_type === "issue") return { kind: "issue", entityId: item.entity_id };
  if (item.entity_type === "agent_run") return { kind: "run", entityId: item.entity_id };
  if (item.entity_type === "pull_request") return { kind: "pull-request", entityId: item.entity_id };
  return null;
}

export function repositoryMatchesId(repository: RepositoryResponse, repositoryId: string | null | undefined): boolean {
  if (!repositoryId) return false;
  return repository.id === repositoryId || (repository.alias_ids ?? []).includes(repositoryId);
}

export function latestRepositoryIndexTimestamp(repositories: RepositoryResponse[]): string | null {
  const timestamps = repositories
    .map((repository) => repository.indexed_at ?? null)
    .filter((value): value is string => Boolean(value))
    .filter((value) => Number.isFinite(new Date(value).getTime()))
    .sort((left, right) => new Date(right).getTime() - new Date(left).getTime());
  return timestamps[0] ?? null;
}

export type DashboardAttentionRecord = {
  key: string;
  kind: "issue" | "run" | "pull-request";
  entityId: string;
  title: string;
  detail: string;
  tone: "warning" | "danger" | "info";
  priority: number;
};

export function dashboardAttentionRecords(
  issues: IssueResponse[],
  runs: RunSummary[],
  pullRequests: PullRequestSummary[]
): DashboardAttentionRecord[] {
  const byWork = new Map<string, DashboardAttentionRecord>();
  const runById = new Map(runs.map((run) => [run.id, run]));
  const issueById = new Map(issues.map((issue) => [issue.id, issue]));
  const add = (workKey: string, record: DashboardAttentionRecord) => {
    const current = byWork.get(workKey);
    if (!current || record.priority > current.priority) byWork.set(workKey, record);
  };

  for (const issue of issues) {
    if (!isAwaitingApproval(issue.plan?.approval_status)) continue;
    add(`issue:${issue.id}`, {
      key: `issue-${issue.id}`,
      kind: "issue",
      entityId: issue.id,
      title: `Issue #${issue.number} · ${issue.title}`,
      detail: "Plan awaiting approval",
      tone: "warning",
      priority: 20
    });
  }
  for (const run of runs) {
    const state = run.state.toUpperCase();
    if (!["WAIT_FOR_CI", "FAILED"].includes(state)) continue;
    const issue = run.issue_id ? issueById.get(run.issue_id) : undefined;
    const failed = state === "FAILED";
    add(run.issue_id ? `issue:${run.issue_id}` : `run:${run.id}`, {
      key: `run-${run.id}`,
      kind: "run",
      entityId: run.id,
      title: issue ? `Run · ${issue.title}` : `Run #${shortIdentifier(run.id)}`,
      detail: failed ? "Recovery needed" : "CI evidence pending",
      tone: failed ? "danger" : "warning",
      priority: failed ? 100 : 30
    });
  }
  for (const pr of pullRequests) {
    const ciFailed = ["failed", "failure", "error"].includes((pr.ci_status ?? "").toLowerCase());
    if (pr.status.toLowerCase() !== "draft" && !ciFailed) continue;
    const linkedRun = runById.get(pr.run_id);
    const issueId = pr.issue?.id ?? linkedRun?.issue_id ?? null;
    add(issueId ? `issue:${issueId}` : `pull-request:${pr.pr_id}`, {
      key: `pr-${pr.pr_id}`,
      kind: "pull-request",
      entityId: pr.pr_id,
      title: `Review #${pr.pr_number} · ${pr.issue?.title ?? "Evidence record"}`,
      detail: ciFailed ? "CI failed" : pr.is_local_record ? "Local record ready" : "Draft review ready",
      tone: ciFailed ? "danger" : "info",
      priority: ciFailed ? 110 : 40
    });
  }
  return [...byWork.values()].sort((left, right) => right.priority - left.priority || left.title.localeCompare(right.title));
}

export function activeRefreshKeys(view: View, settingsTab: SettingsTab = "GitHub"): Set<keyof OperatorData> {
  const keys = new Set<keyof OperatorData>(["session", "runs"]);
  const add = (...items: Array<keyof OperatorData>) => items.forEach((item) => keys.add(item));
  if (view === "dashboard") add("readiness", "repositories", "issues", "pullRequests", "securityFindings", "activities");
  if (view === "new-task") add("repositories");
  if (view === "repositories" || view === "repository-detail") add("repositories", "installations", "issues", "pullRequests");
  if (view === "issues" || view === "issue-detail") add("issues", "repositories", "pullRequests");
  if (view === "agent-runs" || view === "run-trace") add("issues", "pullRequests");
  if (view === "pull-requests" || view === "pull-request-detail") add("pullRequests", "repositories", "issues");
  if (view === "security" || view === "security-detail") add("securityFindings", "policy", "pullRequests");
  if (view === "evaluations") add("evalReports", "repositories");
  if (view === "audit-logs") add("auditLogPage");
  if (view === "landing" || view === "connect") add("readiness", "githubOAuthConfig");
  if (view === "setup") add("readiness", "policy", "githubOAuthConfig", "githubAppConfig", "modelConfig", "repositories", "installations");
  if (view === "settings") {
    add("readiness");
    if (settingsTab === "GitHub") add("githubOAuthConfig", "githubAppConfig", "repositories", "installations");
    if (settingsTab === "Models") add("modelCatalog", "modelConfig");
    if (["Policies", "Tool Permissions", "Cost Limits"].includes(settingsTab)) add("policy");
  }
  if (view === "profile") add("activitySummary", "pullRequests", "securityFindings", "installations");
  return keys;
}

const SEARCHABLE_VIEWS = new Set<View>([
  "dashboard",
  "repositories",
  "issues",
  "agent-runs",
  "pull-requests",
  "security"
]);

export function viewSupportsSearch(view: View): boolean {
  return SEARCHABLE_VIEWS.has(view);
}

export function boundedSearchQuery(value: string, maxLength = 120): string {
  return value.slice(0, Math.max(0, maxLength));
}

export function isCommandSearchShortcut(event: {
  key: string;
  metaKey?: boolean;
  ctrlKey?: boolean;
  altKey?: boolean;
}): boolean {
  return !event.altKey && (Boolean(event.metaKey) || Boolean(event.ctrlKey)) && event.key.toLowerCase() === "k";
}

export function providerHasConfiguredApiKey(
  configuredProviderIds: readonly string[] | null | undefined,
  providerId: string | null | undefined
): boolean {
  if (!providerId) return false;
  const normalizedProviderId = providerId.trim().toLowerCase();
  return Boolean(
    normalizedProviderId
    && configuredProviderIds?.some((candidate) => candidate.trim().toLowerCase() === normalizedProviderId)
  );
}

export function formatUsd(value: number): string {
  if (!Number.isFinite(value) || value < 0) return "Unavailable";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    currencyDisplay: "symbol",
    minimumFractionDigits: 2,
    maximumFractionDigits: 8
  }).format(value);
}

export function formatUsdPerToken(value: string | null | undefined): string | null {
  if (value === null || value === undefined || value.trim() === "") return null;
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric < 0) return null;
  return `${formatUsd(numeric)}/token`;
}

function isAwaitingApproval(status: string | null | undefined): boolean {
  const normalized = (status ?? "").toLowerCase().replace(/[-\s]+/g, "_");
  return ["draft", "waiting", "wait_for_approval", "waiting_for_approval", "awaiting_approval", "pending"].includes(normalized);
}

function safeDecode(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

function shortIdentifier(value: string): string {
  return value.length <= 8 ? value : value.slice(0, 8);
}

export type EvidencePresentation = {
  state: "not_run" | "pending" | "passed" | "failed" | "incomplete" | "unknown";
  label: string;
  tone: "success" | "danger" | "warning" | "neutral";
  passed: boolean;
};

export function validationEvidencePresentation(pr: PullRequestSummary | null | undefined): EvidencePresentation {
  const evidence = pr?.validation_evidence;
  if (!pr || !evidence) return evidencePresentation("unknown", "Unknown");
  if (!pr.current_patch_hash || evidence.patch_hash !== pr.current_patch_hash) {
    return evidencePresentation("incomplete", "Incomplete");
  }
  if (
    evidence.status === "passed"
    && evidence.total > 0
    && evidence.passed === evidence.total
    && evidence.failed === 0
    && evidence.pending === 0
    && evidence.incomplete === 0
  ) {
    return evidencePresentation("passed", "Passed");
  }
  return evidencePresentation(evidence.status === "passed" ? "incomplete" : evidence.status, evidenceLabel(evidence.status === "passed" ? "incomplete" : evidence.status));
}

export function securityEvidencePresentation(pr: PullRequestSummary | null | undefined): EvidencePresentation {
  const scan = pr?.security_scan;
  if (!pr || !scan) return evidencePresentation("unknown", "Unknown");
  if (!pr.current_patch_hash || scan.patch_hash !== pr.current_patch_hash) {
    return evidencePresentation("incomplete", "Incomplete");
  }
  if (scan.finding_count !== pr.security_findings.length) {
    return evidencePresentation("incomplete", "Incomplete");
  }
  const openFindings = pr.security_findings.filter((finding) => finding.status.toLowerCase() === "open");
  if (openFindings.length > 0) {
    return evidencePresentation("failed", `${openFindings.length} open`);
  }
  if (scan.status === "passed" && scan.completed) {
    return evidencePresentation("passed", "Clear");
  }
  return evidencePresentation(scan.status === "passed" ? "incomplete" : scan.status, evidenceLabel(scan.status === "passed" ? "incomplete" : scan.status));
}

export type CIAnalysisConclusion = "success" | "failure" | "cancelled" | "skipped" | "pending" | "unknown";

export function ciAnalysisConclusion(status: string | null | undefined): CIAnalysisConclusion {
  const normalized = (status ?? "").trim().toLowerCase();
  if (["passed", "success", "succeeded"].includes(normalized)) return "success";
  if (["failed", "failure", "error"].includes(normalized)) return "failure";
  if (normalized === "cancelled") return "cancelled";
  if (normalized === "skipped") return "skipped";
  if (["pending", "queued", "running", "in_progress"].includes(normalized)) return "pending";
  return "unknown";
}

export function reviewChecklistStorageKey(pr: PullRequestSummary): string {
  return `repopilot-review-checklist:${encodeURIComponent(pr.pr_id)}:${encodeURIComponent(pr.current_patch_hash ?? "no-patch")}`;
}

export function parseStoredChecklist(raw: string | null, allowedItems: string[]): Set<string> {
  if (!raw) return new Set();
  try {
    const value = JSON.parse(raw);
    if (!Array.isArray(value)) return new Set();
    const allowed = new Set(allowedItems);
    return new Set(value.filter((item): item is string => typeof item === "string" && allowed.has(item)));
  } catch {
    return new Set();
  }
}

export type CompletedRunStatistics = {
  completedCount: number;
  excludedCount: number;
  averageDurationMs: number | null;
  averageRuntimeLabel: string;
  averageCost: number | null;
};

export function completedRunStatistics(runs: RunSummary[]): CompletedRunStatistics {
  const completed = runs.flatMap((run) => {
    if (!run.completed_at) return [];
    const startedAt = new Date(run.started_at).getTime();
    const completedAt = new Date(run.completed_at).getTime();
    if (!Number.isFinite(startedAt) || !Number.isFinite(completedAt) || completedAt < startedAt) return [];
    return [{ durationMs: completedAt - startedAt, cost: Number.isFinite(run.total_cost) && run.total_cost >= 0 ? run.total_cost : null }];
  });
  const averageDurationMs = completed.length
    ? Math.round(completed.reduce((sum, item) => sum + item.durationMs, 0) / completed.length)
    : null;
  const costs = completed.flatMap((item) => item.cost === null ? [] : [item.cost]);
  return {
    completedCount: completed.length,
    excludedCount: runs.length - completed.length,
    averageDurationMs,
    averageRuntimeLabel: averageDurationMs === null ? "Unavailable" : durationLabel(averageDurationMs),
    averageCost: costs.length ? costs.reduce((sum, value) => sum + value, 0) / costs.length : null
  };
}

export type EvaluationEvidenceModel = {
  historical: {
    available: boolean;
    benchmarkVersion: string | null;
    generatedAt: string | null;
    benchmarkTaskCount: number | null;
    fixtureRepositoryCount: number | null;
  };
  live: CompletedRunStatistics & {
    connectedRepositoryCount: number;
  };
};

export function evaluationEvidenceModel(
  report: EvalReport | null | undefined,
  connectedRepositoryCount: number,
  runs: RunSummary[]
): EvaluationEvidenceModel {
  const metrics = report?.metrics ?? {};
  return {
    historical: {
      available: Boolean(report),
      benchmarkVersion: report?.benchmark_version ?? null,
      generatedAt: report?.created_at ?? null,
      benchmarkTaskCount: nonNegativeMetric(metrics.benchmark_task_count),
      fixtureRepositoryCount: nonNegativeMetric(metrics.fixture_repository_count)
    },
    live: {
      connectedRepositoryCount: Math.max(0, Math.trunc(connectedRepositoryCount)),
      ...completedRunStatistics(runs)
    }
  };
}

function evidencePresentation(state: EvidencePresentation["state"], label: string): EvidencePresentation {
  return {
    state,
    label,
    tone: state === "passed" ? "success" : state === "failed" ? "danger" : state === "unknown" ? "neutral" : "warning",
    passed: state === "passed"
  };
}

function evidenceLabel(state: EvidencePresentation["state"]): string {
  if (state === "not_run") return "Not run";
  if (state === "pending") return "Pending";
  if (state === "failed") return "Failed";
  if (state === "incomplete") return "Incomplete";
  if (state === "passed") return "Passed";
  return "Unknown";
}

function durationLabel(durationMs: number): string {
  const seconds = Math.round(durationMs / 1000);
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainder = seconds % 60;
  return hours > 0 ? `${hours}h ${minutes}m ${remainder}s` : `${minutes}m ${remainder}s`;
}

function nonNegativeMetric(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : null;
}
