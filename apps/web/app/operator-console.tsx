"use client";

import {
  AlertCircle,
  AlertTriangle,
  BarChart3,
  Bot,
  Box,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Circle,
  Clock3,
  Code2,
  Database,
  ExternalLink,
  Eye,
  Fingerprint,
  FileCode2,
  FileText,
  GitBranch,
  Github,
  Home,
  KeyRound,
  LayoutGrid,
  ListChecks,
  Lock,
  Mail,
  Play,
  RefreshCcw,
  RotateCcw,
  Save,
  Search,
  Settings,
  Shield,
  ShieldAlert,
  Sparkles,
  Terminal,
  User,
  Wrench,
  X,
  type LucideIcon
} from "lucide-react";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Badge } from "./components/ui/badge";
import { Breadcrumb } from "./components/ui/breadcrumb";
import { EmptyState } from "./components/ui/empty-state";
import { Field } from "./components/ui/field";
import { InfoLine } from "./components/ui/info-line";
import { InfoPanel } from "./components/ui/info-panel";
import { KeyValue } from "./components/ui/key-value";
import { Bullets, NumberedList } from "./components/ui/lists";
import { LogoMark } from "./components/ui/logo-mark";
import { MetaCard } from "./components/ui/meta-card";
import { PanelHeader } from "./components/ui/panel-header";
import { PillList } from "./components/ui/pill-list";
import { PolicyToggle } from "./components/ui/policy-toggle";
import { ScreenHeader } from "./components/ui/screen-header";
import { SecretInput } from "./components/ui/secret-input";
import { Segment } from "./components/ui/segment";
import { StatCard } from "./components/ui/stat-card";
import { SummaryItem } from "./components/ui/summary-item";
import { Threshold } from "./components/ui/threshold";
import {
  SETTINGS_TABS,
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
  parseStoredChecklist,
  parseConsoleHash,
  providerHasConfiguredApiKey,
  reviewChecklistStorageKey,
  repositoryMatchesId,
  securityEvidencePresentation,
  validationEvidencePresentation,
  viewSupportsSearch,
  type ConsoleRoute,
  type SettingsTab,
  type View
} from "./lib/operator-console-state.ts";
import type {
  ActivityItem,
  ActivitySummaryResponse,
  AgentRunDetailResponse,
  AuditLogPage,
  EvalReport,
  GitHubAppConfigStatus,
  GitHubAppVerificationResponse,
  GitHubOAuthConfigStatus,
  GitHubLoginResponse,
  InstallationResponse,
  IssueResponse,
  ModelCatalogModel,
  ModelCatalogResponse,
  ModelProviderConfigStatus,
  ModelProviderVerificationResponse,
  OperatorData,
  PolicyResponse,
  PromptSubmitPayload,
  PromptSubmitResponse,
  PullRequestSummary,
  ReadinessResponse,
  RepositoryResponse,
  RunSummary,
  SecurityFindingResponse,
  SessionResponse,
} from "../lib/api";

type TraceData = {
  run?: {
    id: string;
    state: string;
    model_used: string | null;
    total_tokens: number;
    total_cost: number;
    cost_currency?: "USD";
    started_at: string;
    completed_at: string | null;
  };
  steps?: Array<{
    step_name: string;
    status: string;
    latency_ms: number | null;
    created_at: string;
    output_json: Record<string, unknown> | null;
  }>;
  validation_results?: PullRequestSummary["validation_results"];
  security_findings?: PullRequestSummary["security_findings"];
  artifacts?: Array<{
    id: string;
    artifact_type: string;
    storage_backend: string;
    sha256: string;
    byte_size: number;
    content_type: string;
    metadata: Record<string, unknown>;
    created_at: string;
    deleted_at: string | null;
    available: boolean;
    download_url: string;
  }>;
  pull_requests?: Array<{
    id: string;
    number: number;
    url: string;
    pr_mode?: "local_record" | "real_github";
    is_local_record?: boolean;
    github_url?: string | null;
    status: string;
    ci_status: string | null;
  }>;
  audit_events?: Array<{
    action: string;
    actor_type: string;
    created_at: string;
    metadata: Record<string, unknown>;
  }>;
  llm_traces?: Array<{
    agent_name: string;
    prompt_hash: string;
    response_hash: string | null;
    provider: string;
    model: string;
    mode: string;
    tokens: number;
    cost: number;
    latency_ms: number | null;
    metadata: Record<string, unknown>;
  }>;
};

type ConsoleState = OperatorData;

type GitHubOAuthConfigForm = {
  github_client_id: string;
  github_client_secret: string;
  github_owner_login: string;
  session_secret_key: string;
  github_oauth_callback_url: string;
  web_app_url: string;
  github_api_base_url: string;
  github_web_base_url: string;
};

type GitHubOAuthConfigPayload = Partial<GitHubOAuthConfigForm>;

type GitHubAppConfigPayload = {
  github_webhook_secret?: string;
  github_app_id: string;
  github_app_slug?: string;
  github_private_key?: string;
  github_private_key_path?: string;
  github_installation_id?: string;
};

type ModelProviderConfigPayload = {
  provider: string;
  model: string;
  model_api_key?: string;
  model_base_url?: string;
  model_reasoning_level?: string;
};

type ModelProviderDraft = {
  providerId: string;
  modelId: string;
  reasoningLevel: string;
  apiKey: string;
  baseUrl: string;
  savedConfigSignature: string;
};

type RepoStatusFilter = "all" | "indexed" | "needs-indexing" | "ci-failing";
type IssueRiskFilter = "all" | "low" | "medium" | "high";
type PrStatusFilter = "all" | "draft" | "ready_for_review" | "blocked";
type PrCiFilter = "all" | "passed" | "failed" | "unknown";
type PrSecurityFilter = "all" | "passed" | "open";
type AuditStatusFilter = "all" | "recorded" | "success" | "warning" | "failed";
type AuditRiskFilter = "all" | "unknown" | "low" | "medium" | "high";

const navGroups: Array<{ label: string; items: Array<{ view: View; label: string; icon: LucideIcon }> }> = [
  {
    label: "Work",
    items: [
      { view: "dashboard", label: "Overview", icon: Home },
      { view: "new-task", label: "New task", icon: Sparkles },
      { view: "issues", label: "Tasks", icon: AlertCircle },
      { view: "agent-runs", label: "Runs", icon: Bot }
    ]
  },
  {
    label: "Evidence",
    items: [
      { view: "pull-requests", label: "Reviews", icon: GitBranch },
      { view: "security", label: "Security", icon: Shield }
    ]
  },
  {
    label: "System",
    items: [
      { view: "repositories", label: "Repositories", icon: Database },
      { view: "evaluations", label: "Evaluations", icon: BarChart3 },
      { view: "audit-logs", label: "Audit trail", icon: FileText },
      { view: "settings", label: "Settings", icon: Settings }
    ]
  }
];

const navItems = navGroups.flatMap((group) => group.items);

const stateOrder = [
  "NEW_EVENT",
  "VALIDATE_WEBHOOK",
  "NORMALIZE_EVENT",
  "TRIAGE_ISSUE",
  "RETRIEVE_CONTEXT",
  "GENERATE_PLAN",
  "POLICY_REVIEW_PLAN",
  "WAIT_FOR_APPROVAL",
  "CREATE_BRANCH",
  "IMPLEMENT_PATCH",
  "GENERATE_TESTS",
  "RUN_LOCAL_VALIDATION",
  "RUN_SECURITY_CHECKS",
  "OPEN_DRAFT_PR",
  "WAIT_FOR_CI",
  "READY_FOR_REVIEW"
];

const issueBoardColumns = [
  { key: "needs-info", label: "Needs info", states: ["needs_info"] },
  { key: "ready", label: "Ready", states: ["agent_ready", "planning"] },
  { key: "approval", label: "Approval", states: ["wait_for_approval"] },
  { key: "execution", label: "Execution & review", states: ["in_progress", "pr_opened"] },
  { key: "blocked", label: "Blocked", states: ["blocked"] }
];

type MotionPreference = "no" | "reduced" | "standard" | "enhanced";
type TextDialogRequest = {
  title: string;
  description: string;
  label: string;
  defaultValue: string;
  submitLabel: string;
  minLength?: number;
  multiline?: boolean;
  choice?: {
    label: string;
    defaultValue: string;
    options: Array<{ value: string; label: string }>;
  };
  onSubmit: (value: string, choice?: string) => Promise<void>;
};
type DetailRouteStatus = "idle" | "loading" | "ready" | "missing" | "not-found" | "error";
type ModelCatalogLoadStatus = "idle" | "loading" | "ready" | "error";

class ApiRequestError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
  }
}

const useBrowserLayoutEffect = typeof window === "undefined" ? useEffect : useLayoutEffect;

export function OperatorConsole({ initialData, apiBaseUrl }: { initialData: OperatorData; apiBaseUrl: string }) {
  const [data, setData] = useState<ConsoleState>(initialData);
  const [view, setView] = useState<View>("dashboard");
  const [query, setQuery] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [pendingRunAction, setPendingRunAction] = useState<string | null>(null);
  const pendingRunActionRef = useRef<string | null>(null);
  const [lastRefreshedAt, setLastRefreshedAt] = useState<string | null>(null);
  const [selectedRepoId, setSelectedRepoId] = useState(initialData.repositories[0]?.id ?? "");
  const [selectedIssueId, setSelectedIssueId] = useState(initialData.issues[0]?.id ?? "");
  const [selectedRunId, setSelectedRunId] = useState(initialData.runs[0]?.id ?? "");
  const [selectedPrId, setSelectedPrId] = useState(initialData.pullRequests[0]?.pr_id ?? "");
  const [selectedFindingId, setSelectedFindingId] = useState(initialData.securityFindings[0]?.id ?? "");
  const [routeEntityId, setRouteEntityId] = useState<string | null>(null);
  const [detailRouteStatus, setDetailRouteStatus] = useState<DetailRouteStatus>("idle");
  const [trace, setTrace] = useState<TraceData | null>(null);
  const [traceTab, setTraceTab] = useState<"timeline" | "tools" | "prompts" | "artifacts" | "audit">("timeline");
  const [issuesMode, setIssuesMode] = useState<"board" | "queue">("board");
  const [settingsTab, setSettingsTab] = useState<SettingsTab>("GitHub");
  const [showGithubSecretForm, setShowGithubSecretForm] = useState(false);
  const [showGithubAppSecretForm, setShowGithubAppSecretForm] = useState(false);
  const [selectedAuditKey, setSelectedAuditKey] = useState("");
  const [modelVerification, setModelVerification] = useState<ModelProviderVerificationResponse | null>(null);
  const [githubAppVerification, setGithubAppVerification] = useState<GitHubAppVerificationResponse | null>(null);
  const [modelCatalogLoadStatus, setModelCatalogLoadStatus] = useState<ModelCatalogLoadStatus>(initialData.modelCatalog ? "ready" : "idle");
  const [repoStatusFilter, setRepoStatusFilter] = useState<RepoStatusFilter>("all");
  const [issueRepositoryFilter, setIssueRepositoryFilter] = useState("all");
  const [issueRiskFilter, setIssueRiskFilter] = useState<IssueRiskFilter>("all");
  const [issueTypeFilter, setIssueTypeFilter] = useState("all");
  const [prRepositoryFilter, setPrRepositoryFilter] = useState("all");
  const [prStatusFilter, setPrStatusFilter] = useState<PrStatusFilter>("all");
  const [prRiskFilter, setPrRiskFilter] = useState<IssueRiskFilter>("all");
  const [prCiFilter, setPrCiFilter] = useState<PrCiFilter>("all");
  const [prSecurityFilter, setPrSecurityFilter] = useState<PrSecurityFilter>("all");
  const [auditSourceFilter, setAuditSourceFilter] = useState("all");
  const [auditStatusFilter, setAuditStatusFilter] = useState<AuditStatusFilter>("all");
  const [auditRiskFilter, setAuditRiskFilter] = useState<AuditRiskFilter>("all");
  const [motionPreference, setMotionPreference] = useState<MotionPreference>("standard");
  const [textDialog, setTextDialog] = useState<TextDialogRequest | null>(null);
  const [textDialogValue, setTextDialogValue] = useState("");
  const [textDialogChoice, setTextDialogChoice] = useState("");
  const [textDialogError, setTextDialogError] = useState<string | null>(null);
  const [isTextDialogSubmitting, setIsTextDialogSubmitting] = useState(false);
  const dataRef = useRef(data);
  const activeRouteKeyRef = useRef("");
  const activeRefreshContextRef = useRef("");
  const commandSearchRef = useRef<HTMLInputElement>(null);
  const modelCatalogRequestRef = useRef<Promise<ModelCatalogResponse> | null>(null);
  dataRef.current = data;

  useBrowserLayoutEffect(() => {
    const stored = window.localStorage.getItem("repopilot-motion");
    const resolved = (stored === "no" || stored === "reduced" || stored === "standard" || stored === "enhanced") ? stored : "standard";
    setMotionPreference(resolved);
    document.documentElement.setAttribute("data-motion", resolved);
    document.documentElement.style.setProperty("--motion-level", resolved === "no" ? "0" : resolved === "reduced" ? "0.12" : resolved === "enhanced" ? "1.5" : "1");
  }, []);

  useBrowserLayoutEffect(() => {
    document.documentElement.setAttribute("data-motion", motionPreference);
    document.documentElement.style.setProperty(
      "--motion-level",
      motionPreference === "no" ? "0" : motionPreference === "reduced" ? "0.12" : motionPreference === "enhanced" ? "1.5" : "1"
    );
    window.localStorage.setItem("repopilot-motion", motionPreference);
  }, [motionPreference]);

  useEffect(() => {
    setQuery("");
  }, [view]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (!isCommandSearchShortcut(event) || !viewSupportsSearch(view)) return;
      event.preventDefault();
      commandSearchRef.current?.focus();
      commandSearchRef.current?.select();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [view]);

  const selectedRepo = data.repositories.find((repo) => repositoryMatchesId(repo, selectedRepoId)) ?? null;
  const selectedIssue = data.issues.find((issue) => issue.id === selectedIssueId) ?? null;
  const selectedRun = data.runs.find((run) => run.id === selectedRunId) ?? null;
  const selectedPr = data.pullRequests.find((pr) => pr.pr_id === selectedPrId) ?? null;
  const selectedFinding = data.securityFindings.find((finding) => finding.id === selectedFindingId) ?? null;
  const shellRun = data.runs.find((run) => !isTerminalRunState(run.state)) ?? null;
  const shellIssue = shellRun ? data.issues.find((issue) => issue.id === shellRun.issue_id) ?? null : null;
  const setup = useMemo(() => setupState(data), [data]);

  useBrowserLayoutEffect(() => {
    const syncHash = () => {
      const route = parseConsoleHash(window.location.hash);
      const routeKey = `${route.view}:${route.entityId ?? ""}`;
      activeRouteKeyRef.current = routeKey;
      setView(route.view);
      setRouteEntityId(route.entityId);
      if (route.settingsTab) {
        setSettingsTab(route.settingsTab);
      }
      selectRouteEntity(route);
      if (isEntityRoute(route)) {
        if (!route.entityId) {
          setDetailRouteStatus("missing");
        } else if (routeEntityExists(dataRef.current, route)) {
          setDetailRouteStatus("ready");
        } else {
          setDetailRouteStatus("loading");
          void hydrateDetailRoute(route, routeKey);
        }
      } else {
        setDetailRouteStatus("idle");
      }
      const hashQueryIndex = window.location.hash.indexOf("?");
      if (hashQueryIndex >= 0) {
        const params = new URLSearchParams(window.location.hash.slice(hashQueryIndex + 1));
        if (params.get("github") === "connected") {
          setNotice("GitHub connected. Repository sync completed.");
          setSettingsTab("GitHub");
          void refresh({ quiet: true });
        }
        const githubError = params.get("github_error");
        if (githubError) {
          setNotice(`GitHub connection failed: ${githubError}`);
          setSettingsTab("GitHub");
        }
      }
    };
    syncHash();
    window.addEventListener("hashchange", syncHash);
    return () => window.removeEventListener("hashchange", syncHash);
  }, []);

  function selectRouteEntity(route: ConsoleRoute) {
    if (route.view === "repository-detail") setSelectedRepoId(route.entityId ?? "");
    if (route.view === "issue-detail") setSelectedIssueId(route.entityId ?? "");
    if ((route.view === "agent-runs" || route.view === "run-trace") && route.entityId) setSelectedRunId(route.entityId);
    if (route.view === "run-trace" && !route.entityId) setSelectedRunId("");
    if (route.view === "pull-request-detail") setSelectedPrId(route.entityId ?? "");
    if (route.view === "security-detail") setSelectedFindingId(route.entityId ?? "");
  }

  async function hydrateDetailRoute(route: ConsoleRoute, routeKey: string) {
    const entityId = route.entityId;
    if (!entityId) return;
    try {
      if (route.view === "repository-detail") {
        const repository = await fetchJson<RepositoryResponse>(`/repos/${encodeURIComponent(entityId)}`);
        setData((current) => ({ ...current, repositories: upsertRepository(current.repositories, repository) }));
      } else if (route.view === "issue-detail") {
        const issue = await fetchJson<IssueResponse>(`/issues/${encodeURIComponent(entityId)}`);
        setData((current) => ({ ...current, issues: upsertBy(current.issues, issue, (item) => item.id) }));
      } else if (route.view === "agent-runs" || route.view === "run-trace") {
        const run = await fetchJson<AgentRunDetailResponse>(`/runs/${encodeURIComponent(entityId)}`);
        const latestStep = run.steps.at(-1) ?? null;
        const summary: RunSummary = {
          id: run.id,
          issue_id: run.issue_id,
          plan_id: run.plan_id,
          state: run.state,
          model_used: run.model_used,
          total_tokens: run.total_tokens,
          total_cost: run.total_cost,
          started_at: run.started_at,
          completed_at: run.completed_at,
          latest_step: latestStep?.step_name ?? null,
          latest_step_status: latestStep?.status ?? null,
          validation_statuses: run.validation_results.map((result) => result.status)
        };
        setData((current) => ({ ...current, runs: upsertBy(current.runs, summary, (item) => item.id) }));
      } else if (route.view === "pull-request-detail") {
        const pr = await fetchJson<PullRequestSummary>(`/prs/${encodeURIComponent(entityId)}/summary`);
        setData((current) => ({ ...current, pullRequests: upsertBy(current.pullRequests, pr, (item) => item.pr_id) }));
      } else if (route.view === "security-detail") {
        const finding = await fetchJson<SecurityFindingResponse>(`/security/findings/${encodeURIComponent(entityId)}`);
        setData((current) => ({ ...current, securityFindings: upsertBy(current.securityFindings, finding, (item) => item.id) }));
      }
      if (activeRouteKeyRef.current === routeKey) setDetailRouteStatus("ready");
    } catch (error) {
      if (activeRouteKeyRef.current !== routeKey) return;
      setDetailRouteStatus(error instanceof ApiRequestError && [404, 422].includes(error.status) ? "not-found" : "error");
    }
  }

  useEffect(() => {
    const timer = window.setInterval(() => {
      void refresh({ quiet: true, activeOnly: true });
    }, 30000);
    return () => window.clearInterval(timer);
  }, [settingsTab, view]);

  useEffect(() => {
    const context = `${view}:${settingsTab}`;
    if (!activeRefreshContextRef.current) {
      activeRefreshContextRef.current = context;
      return;
    }
    if (activeRefreshContextRef.current !== context) {
      activeRefreshContextRef.current = context;
      void refresh({ quiet: true, activeOnly: true });
    }
  }, [settingsTab, view]);

  useEffect(() => {
    if (view === "audit-logs" && data.auditLogPage === null) {
      void refresh({ quiet: true, activeOnly: true });
    }
  }, [data.auditLogPage, view]);

  useEffect(() => {
    if (view === "settings" && settingsTab === "Models" && modelCatalogLoadStatus === "idle") {
      void refresh({ quiet: true, activeOnly: true });
    }
  }, [modelCatalogLoadStatus, settingsTab, view]);

  useEffect(() => {
    document.getElementById("main-content")?.scrollTo({ top: 0, behavior: "auto" });
  }, [selectedFindingId, selectedIssueId, selectedPrId, selectedRepoId, selectedRunId, settingsTab, view]);

  useEffect(() => {
    if ((view === "agent-runs" || view === "run-trace") && selectedRun?.id) {
      void loadTrace(selectedRun.id);
    }
  }, [selectedRun?.id, selectedRun?.latest_step, selectedRun?.latest_step_status, selectedRun?.state, view]);

  async function refresh(options?: { quiet?: boolean; activeOnly?: boolean }) {
    if (!options?.quiet) {
      setIsRefreshing(true);
      setNotice(null);
    }
    try {
      const wanted = options?.activeOnly === false ? null : activeRefreshKeys(view, settingsTab);
      const wants = (key: keyof ConsoleState) => wanted === null || wanted.has(key);
      const requests: Array<Promise<Partial<ConsoleState>>> = [];
      const add = <K extends keyof ConsoleState>(key: K, request: () => Promise<ConsoleState[K]>) => {
        if (wants(key)) {
          requests.push(request().then((value) => ({ [key]: value }) as Pick<ConsoleState, K>));
        }
      };
      add("session", () => fetchJson<SessionResponse>("/auth/session"));
      add("repositories", () => fetchJson<RepositoryResponse[]>("/repos"));
      add("installations", () => fetchJson<InstallationResponse[]>("/installations"));
      add("issues", () => fetchJson<IssueResponse[]>("/issues?limit=300"));
      add("pullRequests", () => fetchJson<PullRequestSummary[]>("/prs?limit=200"));
      add("securityFindings", () => fetchJson<SecurityFindingResponse[]>("/security/findings?limit=300"));
      add("activities", () => fetchJson<ActivityItem[]>("/activity?limit=20"));
      add("auditLogPage", () => fetchJson<AuditLogPage>("/activity/audit?limit=500&offset=0"));
      add("activitySummary", () => fetchJson<ActivitySummaryResponse>("/activity/summary"));
      add("runs", () => fetchJson<RunSummary[]>("/runs?limit=80"));
      add("evalReports", () => fetchJson<{ reports: EvalReport[] }>("/evals/reports").then((result) => result.reports));
      add("readiness", () => fetchJson<ReadinessResponse>("/settings/readiness"));
      add("policy", () => fetchJson<PolicyResponse>("/settings/policy"));
      add("githubOAuthConfig", () => fetchJson<GitHubOAuthConfigStatus>("/settings/github/oauth"));
      add("githubAppConfig", () => fetchJson<GitHubAppConfigStatus>("/settings/github/app"));
      add("modelCatalog", requestModelCatalog);
      add("modelConfig", () => fetchJson<ModelProviderConfigStatus>("/settings/models/config"));
      const settled = await Promise.allSettled(requests);
      const updates = settled
        .filter((result): result is PromiseFulfilledResult<Partial<ConsoleState>> => result.status === "fulfilled")
        .map((result) => result.value);
      if (updates.length === 0) {
        const firstFailure = settled.find((result): result is PromiseRejectedResult => result.status === "rejected");
        throw firstFailure?.reason ?? new Error("Refresh failed");
      }
      setData((current) => Object.assign({}, current, ...updates));
      setLastRefreshedAt(new Date().toISOString());
      const failed = settled.length - updates.length;
      if (failed > 0 && !options?.quiet) {
        setNotice(`Refreshed available data; ${failed} source${failed === 1 ? " is" : "s are"} temporarily unavailable.`);
      }
    } catch (error) {
      if (!options?.quiet) {
        setNotice(error instanceof Error ? error.message : "Refresh failed");
      }
    } finally {
      if (!options?.quiet) {
        setIsRefreshing(false);
      }
    }
  }

  function requestModelCatalog(): Promise<ModelCatalogResponse> {
    if (modelCatalogRequestRef.current) return modelCatalogRequestRef.current;
    if (!dataRef.current.modelCatalog) setModelCatalogLoadStatus("loading");
    const request = fetchJson<ModelCatalogResponse>("/settings/models/catalog")
      .then((catalog) => {
        setModelCatalogLoadStatus("ready");
        return catalog;
      })
      .catch((error) => {
        setModelCatalogLoadStatus(dataRef.current.modelCatalog ? "ready" : "error");
        throw error;
      })
      .finally(() => {
        modelCatalogRequestRef.current = null;
      });
    modelCatalogRequestRef.current = request;
    return request;
  }

  async function loadMoreAuditLogs() {
    const current = dataRef.current.auditLogPage;
    if (!current?.has_more) return;
    try {
      const next = await fetchJson<AuditLogPage>(`/activity/audit?limit=500&offset=${current.items.length}`);
      setData((state) => {
        const existing = state.auditLogPage;
        if (!existing) return { ...state, auditLogPage: next };
        const items = [...existing.items, ...next.items.filter((item) => !existing.items.some((currentItem) => currentItem.id === item.id))];
        return {
          ...state,
          auditLogPage: {
            ...next,
            items,
            offset: 0,
            is_complete: items.length >= next.total,
            has_more: items.length < next.total
          }
        };
      });
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "More audit records could not be loaded.");
    }
  }

  async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(`${apiBaseUrl}${path}`, {
      ...init,
      credentials: "include"
    });
    if (!response.ok) {
      const body = await response.text();
      let detail = body;
      try {
        const parsed = JSON.parse(body) as { detail?: string | Array<{ loc?: Array<string | number>; msg?: string }> };
        if (typeof parsed.detail === "string") {
          detail = parsed.detail;
        } else if (Array.isArray(parsed.detail)) {
          detail = parsed.detail
            .map((item) => `${item.loc?.slice(1).join(".") || "request"}: ${item.msg || "invalid value"}`)
            .join("; ");
        }
      } catch {
        // Preserve non-JSON response bodies from proxies and unexpected failures.
      }
      throw new ApiRequestError(response.status, detail || `${response.status} ${response.statusText}`);
    }
    if (response.status === 204) {
      return undefined as T;
    }
    return (await response.json()) as T;
  }

  async function logout() {
    setNotice(null);
    try {
      await fetchJson<void>("/auth/logout", { method: "POST" });
      window.location.href = "/";
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Logout failed");
    }
  }

  function navigate(next: View, entityId?: string | null) {
    setView(next);
    setRouteEntityId(entityId ?? null);
    setDetailRouteStatus(isEntityView(next) ? (entityId ? "ready" : "missing") : "idle");
    window.location.hash = consoleHash(next, { entityId, settingsTab });
  }

  function selectSettingsTab(next: SettingsTab) {
    setSettingsTab(next);
    setView("settings");
    setRouteEntityId(null);
    setDetailRouteStatus("idle");
    window.location.hash = consoleHash("settings", { settingsTab: next });
  }

  async function startGithubFlow() {
    setNotice(null);
    try {
      const result = await fetchJson<GitHubLoginResponse>("/auth/github/login");
      if (result.authorize_url) {
        window.location.href = result.authorize_url;
      } else {
        setNotice(result.next_step);
        setShowGithubSecretForm(true);
        setSettingsTab("GitHub");
        setView("settings");
        window.location.hash = consoleHash("settings", { settingsTab: "GitHub" });
      }
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "GitHub flow is unavailable");
    }
  }

  async function saveGithubOAuthConfig(payload: GitHubOAuthConfigPayload) {
    setNotice(null);
    const status = await fetchJson<GitHubOAuthConfigStatus>("/settings/github/oauth", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-RepoPilot-Intent": "save-oauth-secrets"
      },
      body: JSON.stringify(payload)
    });
    setData((current) => ({ ...current, githubOAuthConfig: status }));
    setShowGithubSecretForm(false);
    setNotice("GitHub OAuth credentials saved in encrypted local storage. You can connect GitHub now.");
    await refresh({ quiet: true });
  }

  async function saveGithubAppConfig(payload: GitHubAppConfigPayload) {
    setNotice(null);
    setGithubAppVerification(null);
    const status = await fetchJson<GitHubAppConfigStatus>("/settings/github/app", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-RepoPilot-Intent": "save-github-app-secrets"
      },
      body: JSON.stringify(payload)
    });
    setData((current) => ({ ...current, githubAppConfig: status }));
    setShowGithubAppSecretForm(false);
    setNotice("GitHub App credentials saved in encrypted local storage. Run verification before enabling live writes.");
    await refresh({ quiet: true });
  }

  async function verifyGithubAppConfig() {
    setNotice(null);
    try {
      const result = await fetchJson<GitHubAppVerificationResponse>("/settings/github/app/verify", { method: "POST" });
      setGithubAppVerification(result);
      setNotice(result.ok ? "GitHub App installation token verified." : result.detail);
      await refresh({ quiet: true });
    } catch (error) {
      setGithubAppVerification(null);
      setNotice(error instanceof Error ? error.message : "GitHub App verification failed");
    }
  }

  async function saveModelProviderConfig(payload: ModelProviderConfigPayload) {
    setNotice(null);
    setModelVerification(null);
    const status = await fetchJson<ModelProviderConfigStatus>("/settings/models/config", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-RepoPilot-Intent": "save-model-provider"
      },
      body: JSON.stringify(payload)
    });
    setData((current) => ({ ...current, modelConfig: status }));
    setNotice(status.api_key_configured ? "Model provider saved. API keys are write-only and stored in encrypted local storage." : "Model provider saved. Add an API key to connect it.");
    await refresh({ quiet: true });
  }

  async function verifyModelProvider() {
    setNotice(null);
    try {
      const result = await fetchJson<ModelProviderVerificationResponse>("/settings/models/verify", { method: "POST" });
      setModelVerification(result);
      setNotice(result.ok ? "Live provider verification succeeded. No repository source is sent for this check." : result.detail);
      await refresh({ quiet: true });
    } catch (error) {
      setModelVerification(null);
      setNotice(error instanceof Error ? error.message : "Model provider verification failed");
    }
  }

  async function submitPrompt(payload: PromptSubmitPayload) {
    setNotice(null);
    const result = await fetchJson<PromptSubmitResponse>("/prompts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    setSelectedIssueId(result.issue.id);
    setSelectedRunId(result.plan?.run_id ?? result.run.id);
    await refresh({ quiet: true });
    setNotice(
      result.plan
        ? `Task #${result.issue.number} created and its plan is ready for review.`
        : `Task #${result.issue.number} created and triaged.`
    );
    navigate("issue-detail", result.issue.id);
  }

  async function indexRepository(repo: RepositoryResponse) {
    setNotice(null);
    try {
      await fetchJson(`/repos/${repo.id}/acquire`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}"
      });
      setNotice(`Source acquired and indexed for ${repo.owner}/${repo.name}.`);
      await refresh();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Repository acquisition failed");
    }
  }

  async function generatePlan(issue: IssueResponse) {
    setNotice(null);
    try {
      const mutation = issueQueueMutation(issue, "generate-plan");
      const response = await fetchJson<{ plan_id: string; run_id: string }>(mutation.path, { method: mutation.method });
      setSelectedRunId(response.run_id);
      setNotice(`Plan generated for issue #${issue.number}.`);
      await refresh();
      navigate("issue-detail", issue.id);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Plan generation failed");
    }
  }

  async function approvePlan(issue: IssueResponse) {
    if (!issue.plan) {
      setNotice("No plan is available for this issue yet.");
      return;
    }
    setNotice(null);
    try {
      const mutation = issueQueueMutation(issue, "approve-plan");
      await fetchJson(mutation.path, { method: mutation.method });
      setNotice(`Plan approved for issue #${issue.number}.`);
      await refresh();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Plan approval failed");
    }
  }

  function openTextDialog(request: TextDialogRequest) {
    setTextDialog(request);
    setTextDialogValue(request.defaultValue);
    setTextDialogChoice(request.choice?.defaultValue ?? "");
    setTextDialogError(null);
    setIsTextDialogSubmitting(false);
  }

  async function submitTextDialog() {
    if (!textDialog || isTextDialogSubmitting) return;
    const value = textDialogValue.trim();
    const minLength = textDialog.minLength ?? 1;
    if (value.length < minLength) {
      setTextDialogError(minLength === 1 ? "This field is required." : `Enter at least ${minLength} characters.`);
      return;
    }
    setTextDialogError(null);
    setIsTextDialogSubmitting(true);
    try {
      await textDialog.onSubmit(value, textDialog.choice ? textDialogChoice : undefined);
      setTextDialog(null);
      setTextDialogValue("");
    } catch (error) {
      setTextDialogError(error instanceof Error ? error.message : "The action could not be completed.");
    } finally {
      setIsTextDialogSubmitting(false);
    }
  }

  async function rejectPlan(issue: IssueResponse) {
    if (!issue.plan) {
      setNotice("No plan is available for this issue yet.");
      return;
    }
    openTextDialog({
      title: "Reject plan",
      description: `Record why plan v${issue.plan.version} for issue #${issue.number} should not proceed.`,
      label: "Rejection reason",
      defaultValue: "Scope or risk needs human revision.",
      submitLabel: "Reject plan",
      minLength: 3,
      multiline: true,
      onSubmit: async (reason) => {
        setNotice(null);
        await fetchJson(`/plans/${issue.plan!.id}/reject`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ reason })
        });
        setNotice(`Plan rejected for issue #${issue.number}.`);
        await refresh();
      }
    });
  }

  async function revisePlan(issue: IssueResponse) {
    if (!issue.plan) {
      setNotice("No plan is available for this issue yet.");
      return;
    }
    openTextDialog({
      title: "Request plan revision",
      description: `Describe the exact scope or evidence changes required for issue #${issue.number}. A fresh plan will require approval.`,
      label: "Revision instructions",
      defaultValue: "Narrow the scope and add validation details.",
      submitLabel: "Create revision",
      minLength: 3,
      multiline: true,
      onSubmit: async (instructions) => {
        setNotice(null);
        const response = await fetchJson<{ new_plan_id: string; version: number }>(`/plans/${issue.plan!.id}/revise`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ instructions })
        });
        setNotice(`Plan revision v${response.version} created for issue #${issue.number}.`);
        await refresh();
      }
    });
  }

  async function runAction(
    run: RunSummary,
    path: string,
    successMessage: string,
    options?: { body?: Record<string, unknown>; actionKey?: string }
  ) {
    if (pendingRunActionRef.current) {
      return;
    }
    const actionKey = `${run.id}:${options?.actionKey ?? path}`;
    pendingRunActionRef.current = actionKey;
    setPendingRunAction(actionKey);
    setNotice(null);
    try {
      await fetchJson(`/runs/${run.id}${path}`, {
        method: "POST",
        ...(options?.body
          ? {
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(options.body)
            }
          : {})
      });
      setNotice(successMessage);
      await refresh({ quiet: true });
      await loadTrace(run.id);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Run action failed");
    } finally {
      pendingRunActionRef.current = null;
      setPendingRunAction(null);
    }
  }

  async function runPrimaryAction(run: RunSummary) {
    const action = primaryRunAction(run);
    if (!action) {
      setNotice(runActionStatus(run.state));
      return;
    }
    if (action.key === "retry") {
      const actionKey = `${run.id}:retry`;
      if (pendingRunActionRef.current) return;
      pendingRunActionRef.current = actionKey;
      setPendingRunAction(actionKey);
      setNotice(null);
      try {
        const response = await fetchJson<{ run_id: string }>(`/runs/${run.id}/retry`, { method: "POST" });
        setSelectedRunId(response.run_id);
        setTrace(null);
        setNotice("A fresh retry run was queued with the same approved plan.");
        await refresh({ quiet: true });
        await loadTrace(response.run_id);
      } catch (error) {
        setNotice(error instanceof Error ? error.message : "Run retry failed");
      } finally {
        pendingRunActionRef.current = null;
        setPendingRunAction(null);
      }
      return;
    }
    await runAction(run, action.path, action.successMessage, {
      actionKey: action.key,
      body: action.body
    });
  }

  async function loadTrace(runId: string) {
    setSelectedRunId(runId);
    try {
      setTrace(await fetchJson<TraceData>(`/runs/${runId}/trace`));
    } catch {
      setTrace(null);
    }
  }

  async function runSecurityReview(pr: PullRequestSummary) {
    setNotice(null);
    try {
      await fetchJson(`/runs/${pr.run_id}/security-scan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({})
      });
      setNotice(`Security scan queued for PR #${pr.pr_number}.`);
      await refresh();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Security scan failed");
    }
  }

  async function analyzeCi(pr: PullRequestSummary) {
    const currentConclusion = ciAnalysisConclusion(pr.ci_status);
    openTextDialog({
      title: "Analyze CI evidence",
      description: `Paste bounded GitHub Actions evidence for PR #${pr.pr_number}. This records evidence; it does not simulate a trusted CI promotion.`,
      label: "CI log evidence",
      defaultValue: latestValidation(pr)?.parsed_summary ?? "",
      submitLabel: "Analyze evidence",
      minLength: 1,
      multiline: true,
      choice: {
        label: "Recorded CI conclusion",
        defaultValue: currentConclusion,
        options: [
          { value: "success", label: "Success" },
          { value: "failure", label: "Failure" },
          { value: "cancelled", label: "Cancelled" },
          { value: "skipped", label: "Skipped" },
          { value: "pending", label: "Pending or still running" },
          { value: "unknown", label: "Unknown or unsupported" }
        ]
      },
      onSubmit: async (logText, conclusion) => {
        setNotice(null);
        await fetchJson(`/prs/${pr.pr_id}/ci`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            workflow_name: "github-actions",
            conclusion: conclusion ?? "unknown",
            log_text: logText
          })
        });
        setNotice(`CI analysis updated for PR #${pr.pr_number}.`);
        await refresh();
      }
    });
  }

  async function createRevisionPlanFromCi(pr: PullRequestSummary) {
    openTextDialog({
      title: "Create CI revision plan",
      description: `Use the recorded failure evidence for PR #${pr.pr_number} to define a fresh, reviewable revision.`,
      label: "Revision instructions",
      defaultValue: "Use CI failure evidence, keep changes inside the approved plan, and rerun validation/security.",
      submitLabel: "Create revision",
      minLength: 3,
      multiline: true,
      onSubmit: async (instructions) => {
        setNotice(null);
        const response = await fetchJson<{ plan_id: string; version: number }>(`/prs/${pr.pr_id}/revision-plan`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ instructions })
        });
        setNotice(`Revision plan v${response.version} created for PR #${pr.pr_number}.`);
        await refresh();
      }
    });
  }

  async function persistSecurityFindingStatus(finding: SecurityFindingResponse, status: string, reason: string) {
    setNotice(null);
    await fetchJson(`/security/findings/${finding.id}/status`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status, reason })
    });
    setNotice(`Security finding marked ${labelize(status)}.`);
    await refresh();
  }

  async function updateSecurityFindingStatus(finding: SecurityFindingResponse, status: string) {
    const needsReason = status === "acknowledged" || status === "false_positive";
    if (!needsReason) {
      try {
        await persistSecurityFindingStatus(finding, status, "");
      } catch (error) {
        setNotice(error instanceof Error ? error.message : "Security finding update failed");
      }
      return;
    }
    openTextDialog({
      title: "Review security finding",
      description: `Explain why this finding should be marked ${labelize(status)}. The reason is retained in the audit trail.`,
      label: "Review reason",
      defaultValue: finding.status_reason ?? "Reviewed by operator.",
      submitLabel: `Mark ${labelize(status)}`,
      minLength: 3,
      multiline: true,
      onSubmit: async (reason) => persistSecurityFindingStatus(finding, status, reason)
    });
  }

  async function runEvaluation() {
    setNotice(null);
    try {
      const response = await fetchJson<{ eval_run_id: string; metrics: Record<string, unknown> }>("/evals/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ benchmark_version: "v1-local", task_count: 31, model_config: { source: "operator-console" } })
      });
      setNotice(`Evaluation report ${shortId(response.eval_run_id)} created with ${numberMetric(response.metrics.benchmark_task_count)} tasks.`);
      await refresh();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Evaluation run failed");
    }
  }

  function selectRepository(repo: RepositoryResponse) {
    setSelectedRepoId(repo.id);
    navigate("repository-detail", repo.id);
  }

  function selectIssue(issue: IssueResponse) {
    setSelectedIssueId(issue.id);
    navigate("issue-detail", issue.id);
  }

  function selectRun(run: RunSummary, target: View = "agent-runs") {
    setSelectedRunId(run.id);
    setTrace(null);
    navigate(target, run.id);
  }

  function selectPr(pr: PullRequestSummary, target: View = "pull-request-detail") {
    setSelectedPrId(pr.pr_id);
    navigate(target, pr.pr_id);
  }

  function selectFinding(finding: SecurityFindingResponse) {
    setSelectedFindingId(finding.id);
    navigate("security-detail", finding.id);
  }

  function openRunById(runId: string, target: View = "agent-runs") {
    setSelectedRunId(runId);
    setTrace(null);
    navigate(target, runId);
  }

  function handleIssueQueueAction(issue: IssueResponse) {
    dispatchIssueQueueAction(issue, {
      generatePlan: (item) => void generatePlan(item),
      approvePlan: (item) => void approvePlan(item),
      openRun: (runId) => openRunById(runId),
      openIssue: selectIssue
    });
  }

  if (view === "landing") {
    return <LandingPage onConnect={startGithubFlow} onConsole={() => navigate("dashboard")} onSecurity={() => navigate("security")} onSignIn={() => navigate("connect")} />;
  }

  if (view === "connect") {
    return <ConnectPage notice={notice} onConnect={startGithubFlow} onSecurity={() => navigate("security")} />;
  }

  return (
    <div className="appShell">
      <a href="#main-content" className="skipLink">Skip to main content</a>
      <aside className="sidebar" aria-label="Sidebar">
        <button className="brandButton" onClick={() => navigate("landing")} type="button" aria-label="RepoPilot AI home">
          <LogoMark />
          <span>RepoPilot AI</span>
        </button>
        <nav className="sidebarNav" aria-label="Primary navigation">
          {navGroups.map((group) => (
            <div className="navGroup" key={group.label}>
              <span className="navGroupLabel">{group.label}</span>
              {group.items.map((item) => {
                const Icon = item.icon;
                const active = isNavActive(view, item.view);
                return (
                  <button className={active ? "navItem active" : "navItem"} key={item.view} onClick={() => navigate(item.view)} type="button" aria-current={active ? "page" : undefined}>
                    <Icon size={19} aria-hidden="true" />
                    <span>{item.label}</span>
                  </button>
                );
              })}
            </div>
          ))}
        </nav>
        <button className="workspaceCard" onClick={() => navigate("profile")} type="button" aria-label={`Open profile for ${data.session?.username ?? "Platform Admin"}`}>
          <span className="avatar small" aria-hidden="true">{initials(data.session?.username ?? "Platform Admin")}</span>
          <span>
            <strong>{workspaceLabel(data.installations)}</strong>
            <small>{data.session?.role ?? "local"}</small>
          </span>
          <ChevronDown size={16} aria-hidden="true" />
        </button>
        <SetupMini setup={setup} onClick={() => navigate("setup")} />
      </aside>

      <section className="mainFrame" aria-label="Main workspace">
        <header className="topbar" role="banner">
          <button className="topbarContext" onClick={() => navigate("repositories")} type="button">
            <small>Context</small>
            <strong>All repositories <ChevronDown size={14} aria-hidden="true" /></strong>
          </button>
          {shellRun ? (
            <button className="topbarRun" onClick={() => selectRun(shellRun)} type="button">
              <small>Active run</small>
              <strong>
                #{shortId(shellRun.id)}
                {shellIssue ? <span>· Issue #{shellIssue.number}</span> : null}
                {!isTerminalRunState(shellRun.state) ? <i aria-label="Live run" /> : null}
              </strong>
            </button>
          ) : (
            <button className="topbarRun" onClick={() => navigate("new-task")} type="button">
              <small>Active run</small>
              <strong>No active run <span>· Create task</span></strong>
            </button>
          )}
          <label className="commandSearch">
            <Search size={20} aria-hidden="true" />
            <input
              aria-label={viewSupportsSearch(view) ? "Search the current RepoPilot view" : "Search is unavailable in this view"}
              disabled={!viewSupportsSearch(view)}
              maxLength={120}
              onChange={(event) => setQuery(boundedSearchQuery(event.target.value))}
              onKeyDown={(event) => { if (event.key === "Escape") setQuery(""); }}
              placeholder={viewSupportsSearch(view) ? "Search this view..." : "Search unavailable"}
              ref={commandSearchRef}
              value={query}
            />
            {viewSupportsSearch(view) ? <kbd aria-label="Keyboard shortcut Command K">⌘ K</kbd> : null}
          </label>
          <button
            className="iconOnly"
            disabled={isRefreshing}
            onClick={() => void refresh()}
            aria-label={`Refresh data snapshot. ${refreshStateLabel(lastRefreshedAt, isRefreshing)}`}
            title={refreshStateLabel(lastRefreshedAt, isRefreshing)}
            type="button"
          >
            <RefreshCcw size={19} aria-hidden="true" className={isRefreshing ? "refreshSpinner" : ""} />
          </button>
          <button className="profileButton" onClick={() => navigate("profile")} type="button" aria-label={`Open profile for ${data.session?.username ?? "Platform Admin"}`}>
            <span className="avatar" aria-hidden="true">{initials(data.session?.username ?? "Platform Admin")}</span>
            <ChevronDown size={16} aria-hidden="true" />
          </button>
        </header>

        <div aria-live="polite" aria-atomic="true">
          {notice ? <div className="noticeBanner" role="status">{notice}</div> : null}
        </div>

        <main className="content" id="main-content">
          {view === "setup" ? <SetupScreen setup={setup} onContinue={() => navigate(nextSetupView(setup))} /> : null}
          {view === "new-task" ? <NewTaskScreen initialRepositoryId={selectedRepo?.id ?? ""} onSubmit={submitPrompt} repositories={data.repositories} /> : null}
          {view === "dashboard" ? (
            <DashboardScreen
              data={data}
              query={query}
              onIssue={selectIssue}
              onNewTask={() => navigate("new-task")}
              onPr={selectPr}
              onRun={selectRun}
              onRunTrace={(run) => {
                const target = dashboardNavigationTarget("open-full-timeline", run.id);
                openRunById(run.id, target.view);
              }}
              onSecurity={() => navigate("security")}
              onTasks={() => {
                const target = dashboardNavigationTarget("view-all-tasks");
                setIssuesMode(target.issuesMode ?? "board");
                navigate(target.view, target.entityId);
              }}
              isRefreshing={isRefreshing}
            />
          ) : null}
          {view === "repositories" ? (
            <RepositoriesScreen
              data={data}
              query={query}
              setQuery={setQuery}
              onConnect={startGithubFlow}
              onRepo={selectRepository}
              statusFilter={repoStatusFilter}
              setStatusFilter={setRepoStatusFilter}
            />
          ) : null}
          {view === "repository-detail" && selectedRepo ? (
            <RepositoryDetailScreen
              issues={data.issues}
              onIndex={indexRepository}
              onIssue={selectIssue}
              onIssues={() => {
                setIssueRepositoryFilter(selectedRepo.id);
                navigate("issues");
              }}
              repo={selectedRepo}
            />
          ) : view === "repository-detail" ? <DetailRouteState entityLabel="repository" requestedId={routeEntityId} status={detailRouteStatus} /> : null}
          {view === "issues" ? (
            <IssuesScreen
              issues={data.issues}
              repositoryFilter={issueRepositoryFilter}
              riskFilter={issueRiskFilter}
              typeFilter={issueTypeFilter}
              mode={issuesMode}
              onIssueAction={handleIssueQueueAction}
              onIssue={selectIssue}
              onNewTask={() => navigate("new-task")}
              query={query}
              repositories={data.repositories}
              setRepositoryFilter={setIssueRepositoryFilter}
              setMode={setIssuesMode}
              setRiskFilter={setIssueRiskFilter}
              setTypeFilter={setIssueTypeFilter}
            />
          ) : null}
          {view === "issue-detail" && selectedIssue ? (
            <IssueDetailScreen issue={selectedIssue} onApprove={approvePlan} onGeneratePlan={generatePlan} onReject={rejectPlan} onRevise={revisePlan} />
          ) : view === "issue-detail" ? <DetailRouteState entityLabel="issue" requestedId={routeEntityId} status={detailRouteStatus} /> : null}
          {view === "agent-runs" && (!routeEntityId || selectedRun) ? (
            <AgentRunsScreen
              issues={data.issues}
              isActionPending={Boolean(pendingRunAction && selectedRun && pendingRunAction.startsWith(`${selectedRun.id}:`))}
              onPrimaryAction={(run) => void runPrimaryAction(run)}
              onRun={selectRun}
              onStop={(run) => void runAction(run, "/stop", "Run cancelled.", { actionKey: "stop" })}
              query={query}
              runs={data.runs}
              selectedRun={selectedRun}
              trace={trace}
            />
          ) : view === "agent-runs" ? <DetailRouteState entityLabel="run" requestedId={routeEntityId} status={detailRouteStatus} /> : null}
          {view === "run-trace" && selectedRun ? (
            <RunTraceScreen selectedRun={selectedRun} setTab={setTraceTab} tab={traceTab} trace={trace} />
          ) : view === "run-trace" ? <DetailRouteState entityLabel="run" requestedId={routeEntityId} status={detailRouteStatus} /> : null}
          {view === "pull-requests" ? (
            <PullRequestsScreen
              ciFilter={prCiFilter}
              prs={data.pullRequests}
              query={query}
              repositories={data.repositories}
              repositoryFilter={prRepositoryFilter}
              riskFilter={prRiskFilter}
              securityFilter={prSecurityFilter}
              setCiFilter={setPrCiFilter}
              setRepositoryFilter={setPrRepositoryFilter}
              setRiskFilter={setPrRiskFilter}
              setSecurityFilter={setPrSecurityFilter}
              setStatusFilter={setPrStatusFilter}
              statusFilter={prStatusFilter}
              onPr={selectPr}
            />
          ) : null}
          {view === "pull-request-detail" && selectedPr ? (
            <PullRequestDetailScreen
              onAnalyzeCi={analyzeCi}
              onOpenIssue={(issueId) => {
                setSelectedIssueId(issueId);
                navigate("issue-detail", issueId);
              }}
              onOpenRun={(runId) => {
                setSelectedRunId(runId);
                navigate("run-trace", runId);
              }}
              onRevisionPlan={createRevisionPlanFromCi}
              onSecurityReview={runSecurityReview}
              pr={selectedPr}
            />
          ) : view === "pull-request-detail" ? <DetailRouteState entityLabel="pull request" requestedId={routeEntityId} status={detailRouteStatus} /> : null}
          {view === "security" ? (
            <SecurityScreen findings={data.securityFindings} onFinding={selectFinding} policy={data.policy} query={query} />
          ) : null}
          {view === "security-detail" && selectedFinding ? <SecurityDetailScreen finding={selectedFinding} onUpdateStatus={updateSecurityFindingStatus} /> : view === "security-detail" ? <DetailRouteState entityLabel="security finding" requestedId={routeEntityId} status={detailRouteStatus} /> : null}
          {view === "evaluations" ? <EvaluationsScreen evalReports={data.evalReports} onRunEvaluation={runEvaluation} repositories={data.repositories} runs={data.runs} /> : null}
          {view === "audit-logs" ? (
            <AuditLogsScreen
              page={data.auditLogPage}
              onLoadMore={() => void loadMoreAuditLogs()}
              riskFilter={auditRiskFilter}
              selectedKey={selectedAuditKey}
              setRiskFilter={setAuditRiskFilter}
              setSelectedKey={setSelectedAuditKey}
              setSourceFilter={setAuditSourceFilter}
              setStatusFilter={setAuditStatusFilter}
              sourceFilter={auditSourceFilter}
              statusFilter={auditStatusFilter}
            />
          ) : null}
          {view === "settings" ? (
            <SettingsScreen
              data={data}
              onGithub={startGithubFlow}
              onSaveGithubApp={saveGithubAppConfig}
              onSaveGithubOAuth={saveGithubOAuthConfig}
              onVerifyGithubApp={verifyGithubAppConfig}
              onSaveModelProvider={saveModelProviderConfig}
              onVerifyModelProvider={verifyModelProvider}
              setShowAppSecretForm={setShowGithubAppSecretForm}
              setShowSecretForm={setShowGithubSecretForm}
              showAppSecretForm={showGithubAppSecretForm}
              showSecretForm={showGithubSecretForm}
              policy={data.policy}
              readiness={data.readiness}
              setTab={selectSettingsTab}
              tab={settingsTab}
              githubAppVerification={githubAppVerification}
              verification={modelVerification}
              onReset={() => void refresh()}
              motionPreference={motionPreference}
              modelCatalogLoadStatus={modelCatalogLoadStatus}
              setMotionPreference={setMotionPreference}
            />
          ) : null}
          {view === "profile" ? (
            <ProfileScreen
              data={data}
              onLogout={logout}
              onSettings={() => {
                selectSettingsTab("GitHub");
              }}
            />
          ) : null}
        </main>
      </section>
      {textDialog ? (
        <TextActionDialog
          error={textDialogError}
          isSubmitting={isTextDialogSubmitting}
          onCancel={() => {
            if (!isTextDialogSubmitting) setTextDialog(null);
          }}
          onSubmit={() => void submitTextDialog()}
          request={textDialog}
          choice={textDialogChoice}
          setChoice={setTextDialogChoice}
          setValue={setTextDialogValue}
          value={textDialogValue}
        />
      ) : null}
    </div>
  );
}

function TextActionDialog({
  choice,
  error,
  isSubmitting,
  onCancel,
  onSubmit,
  request,
  setChoice,
  setValue,
  value
}: {
  choice: string;
  error: string | null;
  isSubmitting: boolean;
  onCancel: () => void;
  onSubmit: () => void;
  request: TextDialogRequest;
  setChoice: (value: string) => void;
  setValue: (value: string) => void;
  value: string;
}) {
  return (
    <div className="dialogBackdrop" role="presentation">
      <section aria-describedby="text-action-dialog-description" aria-labelledby="text-action-dialog-title" aria-modal="true" className="textActionDialog" role="dialog">
        <header className="dialogHeader">
          <div>
            <h2 id="text-action-dialog-title">{request.title}</h2>
            <p id="text-action-dialog-description">{request.description}</p>
          </div>
          <button aria-label="Close dialog" className="iconOnly" disabled={isSubmitting} onClick={onCancel} type="button"><X size={18} /></button>
        </header>
        {request.choice ? (
          <label className="taskField">
            <span>{request.choice.label}</span>
            <select onChange={(event) => setChoice(event.target.value)} value={choice}>
              {request.choice.options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </label>
        ) : null}
        <label className="taskField">
          <span>{request.label}</span>
          {request.multiline ? (
            <textarea autoFocus maxLength={8000} onChange={(event) => setValue(event.target.value)} rows={8} value={value} />
          ) : (
            <input autoFocus maxLength={8000} onChange={(event) => setValue(event.target.value)} value={value} />
          )}
        </label>
        {error ? <div className="connectNotice" role="alert">{error}</div> : null}
        <div className="panelActions dialogActions">
          <button className="ghostAction" disabled={isSubmitting} onClick={onCancel} type="button">Cancel</button>
          <button className="primaryAction" disabled={isSubmitting} onClick={onSubmit} type="button">
            {isSubmitting ? "Working..." : request.submitLabel}
          </button>
        </div>
      </section>
    </div>
  );
}

function LandingPage({
  onConnect,
  onConsole,
  onSecurity,
  onSignIn
}: {
  onConnect: () => void;
  onConsole: () => void;
  onSecurity: () => void;
  onSignIn: () => void;
}) {
  const features: Array<[string, string, LucideIcon]> = [
    ["Issue Triage", "Auto-categorize and prioritize incoming GitHub issues.", AlertCircle],
    ["Plan Approval", "Review and approve clear, structured implementation plans.", FileText],
    ["Draft PR Records", "Create gated draft PR records and evidence-backed change proposals.", GitBranch],
    ["CI Evidence", "Record CI outcomes and create revision plans from supplied failure evidence.", Terminal],
    ["Security Checks", "Run built-in checks, with external scanner adapters gated by configuration.", Shield]
  ];

  return (
    <main className="publicPage">
      <header className="publicNav">
        <div className="publicBrand">
          <LogoMark />
          <span>RepoPilot AI</span>
        </div>
        <nav>
          <button onClick={() => document.getElementById("product-features")?.scrollIntoView({ behavior: "smooth" })} type="button">Product</button>
          <button onClick={onSecurity} type="button">Security</button>
          <button onClick={() => window.open("https://github.com/HarshalRane04/RepoPilot", "_blank", "noopener,noreferrer")} title="View the RepoPilot README for setup and usage." type="button">Docs <span style={{ fontSize: "11px", color: "var(--text-2)" }}>(README)</span></button>
          <button onClick={onSignIn} type="button">
            Sign in
          </button>
        </nav>
      </header>
      <section className="heroGrid">
        <div className="heroCopy">
          <h1>
            GitHub Issue Planning, with <span>Human Control</span>
          </h1>
          <p>RepoPilot AI turns GitHub issues into reviewed plans, validation evidence, security findings, and gated draft PR records while keeping humans in control.</p>
          <div className="heroActions">
            <button className="primaryAction" onClick={onConnect} type="button">
              <Github size={22} />
              Sign in with GitHub
            </button>
            <button className="ghostAction" onClick={onConsole} type="button">
              <Play size={20} />
              Open console
            </button>
          </div>
        </div>
        <div className="workflowCard">
          <div className="workflowHeader">
            <span>RepoPilot AI Workflow</span>
            <Badge tone="success">main</Badge>
          </div>
          {[
            ["Issue Received", "issue"],
            ["Plan Generated", "plan.md"],
            ["Approval Required", "awaiting review"],
            ["Local PR Record", "draft"],
            ["CI Evidence Recorded", "checks"]
          ].map(([label, tag], index) => (
            <div className="workflowStep" key={label}>
              <span className={index === 4 ? "timelineDot done" : "timelineDot"} />
              <span className="workflowIcon">{index + 1}</span>
              <strong>{label}</strong>
              <code>{tag}</code>
            </div>
          ))}
        </div>
      </section>
      <section className="featureStrip" id="product-features">
        {features.map(([title, copy, Icon]) => (
          <article className="featureCard" key={title}>
            <Icon size={30} />
            <strong>{title}</strong>
            <p>{copy}</p>
          </article>
        ))}
      </section>
    </main>
  );
}

function ConnectPage({ notice, onConnect, onSecurity }: { notice: string | null; onConnect: () => void; onSecurity: () => void }) {
  const permissions = [
    ["Repositories", "Imports repositories the authorized user can access.", "Read", Database],
    ["Profile", "Identifies the connected GitHub account.", "Read", User],
    ["Email", "Uses the primary verified email when GitHub exposes it.", "Read", Mail],
    ["Issues", "Lets RepoPilot associate future issue events with imported repositories.", "Read", AlertCircle],
    ["Metadata", "Reads repository names, owners, and default branches.", "Read", Github]
  ] as const;
  return (
    <main className="connectPage">
      <div className="connectBrand">
        <LogoMark />
        <strong>RepoPilot AI</strong>
      </div>
      <section className="connectCard">
        <h1>Connect GitHub</h1>
        <p>Authorize RepoPilot AI to create your GitHub session and sync the repositories available to your account.</p>
        <button className="primaryAction wide" onClick={onConnect} type="button">
          <Github size={24} />
          Continue with GitHub
        </button>
        <button className="linkButton" onClick={onSecurity} type="button">
          <Shield size={18} />
          View security details
          <ChevronRight size={16} />
        </button>
        {notice ? <div className="connectNotice">{notice}</div> : null}
        <div className="permissionList">
          <h2>Required permissions</h2>
          {permissions.map(([title, copy, access, Icon]) => (
            <div className="permissionRow" key={title}>
              <span className="permissionIcon">
                <Icon size={20} />
              </span>
              <span>
                <strong>{title}</strong>
                <small>{copy}</small>
              </span>
              <Badge tone={access === "Read" ? "info" : "success"}>{access}</Badge>
            </div>
          ))}
        </div>
        <div className="approvalCallout">
          <Shield size={23} />
          RepoPilot never merges code automatically. All code changes require human approval.
        </div>
      </section>
      <p className="connectFooter">You can revoke access from GitHub settings at any time.</p>
    </main>
  );
}

function SetupScreen({ setup, onContinue }: { setup: ReturnType<typeof setupState>; onContinue: () => void }) {
  const reasons: Array<[LucideIcon, string]> = [
    [Shield, "Approval policies keep humans in control."],
    [Database, "Repository indexing helps agents understand your code."],
    [Lock, "Security gates prevent risky autonomous changes."]
  ];

  return (
    <div className="screen">
      <ScreenHeader title="Set up RepoPilot AI" subtitle="Complete these steps to start preparing reviewed plans and gated draft PR workflows." />
      <div className="setupGrid">
        <section className="panel setupPanel">
          <div className="progressHeader">
            <span>{setup.completed} of {setup.steps.length} completed</span>
            <div className="progressTrack">
              <span style={{ width: `${setup.percent}%` }} />
            </div>
          </div>
          <div className="setupSteps">
            {setup.steps.map((step, index) => (
              <div className={step.done ? "setupStep done" : index === setup.completed ? "setupStep current" : "setupStep"} key={step.label}>
                <span>{index + 1}</span>
                <strong>{step.label}</strong>
                {step.done ? <CheckCircle2 size={22} /> : <Circle size={22} />}
              </div>
            ))}
          </div>
          <div className="panelActions">
            <button className="primaryAction" onClick={onContinue} type="button">
              Continue setup
            </button>
          </div>
        </section>
        <aside className="panel explainerPanel">
          <h2>Why this matters</h2>
          {reasons.map(([Icon, copy]) => (
            <div className="whyRow" key={copy}>
              <Icon size={26} />
              <span>{copy}</span>
            </div>
          ))}
        </aside>
      </div>
    </div>
  );
}

function NewTaskScreen({
  initialRepositoryId,
  onSubmit,
  repositories
}: {
  initialRepositoryId: string;
  onSubmit: (payload: PromptSubmitPayload) => Promise<void>;
  repositories: RepositoryResponse[];
}) {
  const [repositoryId, setRepositoryId] = useState(initialRepositoryId || repositories[0]?.id || "");
  const [title, setTitle] = useState("");
  const [prompt, setPrompt] = useState("");
  const [autoPlan, setAutoPlan] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const canSubmit = title.trim().length >= 4 && prompt.trim().length >= 8 && !isSubmitting;

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) {
      setError("Add a title of at least 4 characters and task details of at least 8 characters.");
      return;
    }
    setError(null);
    setIsSubmitting(true);
    try {
      await onSubmit({
        repository_id: repositoryId || undefined,
        title: title.trim(),
        prompt: prompt.trim(),
        auto_plan: autoPlan
      });
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Unable to create the task.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="screen">
      <ScreenHeader title="New Task" subtitle="Describe work for RepoPilot to triage and, when appropriate, prepare as a human-reviewed plan." />
      <div className="detailGrid taskComposerGrid">
        <form className="panel taskComposer" onSubmit={(event) => void submit(event)}>
          <label className="taskField">
            <span>Repository</span>
            <select onChange={(event) => setRepositoryId(event.target.value)} value={repositoryId}>
              <option value="">Automatic (latest repository or local task workspace)</option>
              {repositories.map((repo) => (
                <option key={repo.id} value={repo.id}>
                  {repo.owner}/{repo.name} ({repo.source_mode === "github_app" ? "GitHub App" : repo.source_mode === "oauth_discovery" ? "OAuth" : "Local"})
                </option>
              ))}
            </select>
          </label>
          <label className="taskField">
            <span>Task title</span>
            <input
              autoFocus
              maxLength={180}
              minLength={4}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="Fix stale repository status after indexing"
              required
              value={title}
            />
          </label>
          <label className="taskField">
            <span>Task details</span>
            <textarea
              maxLength={8000}
              minLength={8}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder="Describe the problem, expected behavior, constraints, and useful acceptance criteria."
              required
              rows={12}
              value={prompt}
            />
            <small>{prompt.length.toLocaleString()} / 8,000 characters</small>
          </label>
          <label className="taskCheckRow">
            <input checked={autoPlan} onChange={(event) => setAutoPlan(event.target.checked)} type="checkbox" />
            <span>
              <strong>Prepare a plan after triage</strong>
              <small>RepoPilot only creates a plan when triage marks the task ready. Implementation still requires human approval.</small>
            </span>
          </label>
          {error ? <div className="connectNotice" role="alert">{error}</div> : null}
          <div className="panelActions">
            <button className="primaryAction" disabled={!canSubmit} type="submit">
              <Sparkles size={18} />
              {isSubmitting ? "Creating and triaging task..." : "Create task"}
            </button>
          </div>
        </form>
        <aside className="panel contextPanel taskPrivacyPanel">
          <h2>Before you submit</h2>
          <InfoLine icon={Shield} label="Human gate" value="No implementation starts until an authorized reviewer approves the generated plan." />
          <InfoLine icon={Database} label="Repository context" value="Indexed repository snippets may be retrieved to ground the plan." />
          <InfoLine icon={Eye} label="External model boundary" value="If a live provider is configured, task text and selected context may be sent to that provider." />
          <InfoLine icon={Lock} label="Keep secrets out" value="Do not paste credentials, private keys, tokens, or customer-sensitive data into task text." />
        </aside>
      </div>
    </div>
  );
}

function DashboardScreen({
  data,
  query,
  onIssue,
  onNewTask,
  onPr,
  onRun,
  onRunTrace,
  onSecurity,
  onTasks,
  isRefreshing
}: {
  data: ConsoleState;
  query: string;
  onIssue: (issue: IssueResponse) => void;
  onNewTask: () => void;
  onPr: (pr: PullRequestSummary) => void;
  onRun: (run: RunSummary) => void;
  onRunTrace: (run: RunSummary) => void;
  onSecurity: () => void;
  onTasks: () => void;
  isRefreshing: boolean;
}) {
  const matchingIssues = filterIssues(data.issues, query);
  const activeRun = data.runs.find((run) => !isTerminalRunState(run.state)) ?? null;
  const activeIssue = activeRun ? data.issues.find((issue) => issue.id === activeRun.issue_id) ?? null : null;
  const activePr = activeRun ? data.pullRequests.find((pr) => pr.run_id === activeRun.id) ?? null : null;
  const lastEvent = activeRun ? data.activities.find((item) => item.entity_id === activeRun.id) ?? null : null;
  const planApproved = activeIssue?.plan?.approval_status === "approved";
  const reviewReady = activeRun?.state.toUpperCase() === "READY_FOR_REVIEW";
  const currentStage = activeRun ? runStageLabel(activeRun.state) : "No active run";
  const validationEvidence = validationEvidencePresentation(activePr);
  const securityEvidence = securityEvidencePresentation(activePr);
  const lifecycle = activeRun ? [
    { label: "Task", detail: "Complete", state: "done" },
    { label: "Plan", detail: planApproved ? "Approved" : "Approval required", state: planApproved ? "done" : "current" },
    { label: "Run", detail: reviewReady ? "Complete" : currentStage, state: reviewReady ? "done" : planApproved ? "current" : "pending" },
    { label: "Review", detail: reviewReady ? "Ready" : "Pending", state: reviewReady ? "current" : "pending" }
  ] : [];
  const attentionRecords = dashboardAttentionRecords(data.issues, data.runs, data.pullRequests);
  const attentionItems = attentionRecords.slice(0, 4);
  const activity = data.activities.slice(0, 5);

  return (
    <div className={`screen instrumentDashboard${isRefreshing ? " is-loading" : ""}`}>
      {!activeRun || !activeIssue ? (
        <section className="instrumentEmpty">
          <span className="instrumentEyebrow">Evidence-first engineering</span>
          <h1>Start a governed task</h1>
          <p>Describe the outcome once. RepoPilot will triage it, prepare an evidence-backed plan, and wait for explicit approval before implementation.</p>
          <button className="primaryAction" onClick={onNewTask} type="button"><Sparkles size={18} /> Create task</button>
        </section>
      ) : (
        <>
          <section className="runHero" aria-labelledby="active-run-title">
            <div className="runHeroHeading">
              <div>
                <button className="backLink" onClick={() => onRun(activeRun)} type="button">Open full run <ChevronRight size={15} /></button>
                <span className="issuePill">Issue #{activeIssue.number}</span>
                <h1 id="active-run-title">{activeIssue.title}</h1>
                <p>Agent run #{shortId(activeRun.id)} <span>·</span> Started {formatClock(activeRun.started_at)} <span>·</span> Owner {data.session?.username ?? "local"}</p>
              </div>
              <div className={`currentStage ${statusTone(activeRun.state)}`}>
                <Clock3 size={28} aria-hidden="true" />
                <span>
                  <small>Current stage</small>
                  <strong>{currentStage}</strong>
                  <em>{runActionStatus(activeRun.state)}</em>
                </span>
              </div>
            </div>

            <ol className="lifecycleRail" aria-label="Task lifecycle">
              {lifecycle.map((stage, index) => (
                <li className={stage.state} key={stage.label}>
                  <span className="lifecycleNode" aria-hidden="true">{stage.state === "done" ? <Check size={17} /> : index + 1}</span>
                  <div>
                    <strong>{stage.label}</strong>
                    <small>{stage.detail}</small>
                  </div>
                </li>
              ))}
            </ol>

            <div className="runEvidenceStrip">
              <div className="meaningfulEvent">
                <small>Last meaningful event</small>
                <span>
                  <i><Clock3 size={20} /></i>
                  <span>
                    <strong>{lastEvent ? labelize(lastEvent.action) : labelize(activeRun.latest_step ?? activeRun.state)}</strong>
                    <em>{lastEvent ? `${labelize(lastEvent.source)} · ${relativeTime(lastEvent.created_at)}` : "Run state recorded"}</em>
                  </span>
                </span>
              </div>
              <div className="evidenceChecks">
                <small>Validation &amp; security</small>
                <span className={validationEvidence.passed ? "passed" : "pending"}><CheckCircle2 size={19} /> Validation {validationEvidence.label.toLowerCase()}</span>
                <span className={securityEvidence.passed ? "passed" : "pending"}><Shield size={19} /> Security {securityEvidence.label.toLowerCase()}</span>
                <span className={planApproved ? "passed" : "pending"}><CheckCircle2 size={19} /> Policy {planApproved ? "approved" : "pending"}</span>
                <button className="inlineLink" onClick={() => activePr ? onPr(activePr) : onRun(activeRun)} type="button">View proof <ChevronRight size={15} /></button>
              </div>
              <div className="nextSafeAction">
                <small>Next safe action</small>
                <p>{runActionStatus(activeRun.state)}. Review the run evidence and continue only when the trust gates are satisfied.</p>
                <button className="primaryAction" onClick={() => activePr ? onPr(activePr) : onRun(activeRun)} type="button">Review evidence <ExternalLink size={17} /></button>
              </div>
            </div>
          </section>

          <div className="instrumentGrid">
            <section className="ledgerPanel">
              <header>
                <h2>Needs attention <span>{attentionRecords.length}</span></h2>
                <button className="inlineLink" onClick={onNewTask} type="button">New task <Sparkles size={15} /></button>
              </header>
              <div className="attentionLedger">
                {attentionItems.map((item) => {
                  const Icon = item.tone === "danger" ? AlertTriangle : item.kind === "pull-request" ? GitBranch : Clock3;
                  const onClick = () => {
                    if (item.kind === "issue") {
                      const issue = data.issues.find((candidate) => candidate.id === item.entityId);
                      if (issue) onIssue(issue);
                    } else if (item.kind === "run") {
                      const run = data.runs.find((candidate) => candidate.id === item.entityId);
                      if (run) onRun(run);
                    } else {
                      const pr = data.pullRequests.find((candidate) => candidate.pr_id === item.entityId);
                      if (pr) onPr(pr);
                    }
                  };
                  return (
                    <button className="attentionRow" key={item.key} onClick={onClick} type="button">
                      <span className={`attentionIcon ${item.tone}`}><Icon size={18} /></span>
                      <span><strong>{item.title}</strong><small>{item.detail}</small></span>
                      <ChevronRight size={17} aria-hidden="true" />
                    </button>
                  );
                })}
                {attentionRecords.length === 0 ? <EmptyState text="No work needs intervention right now." /> : null}
              </div>
              <button className="ledgerFooter" onClick={onTasks} type="button">View all tasks <ChevronRight size={15} /></button>
            </section>

            <section className="ledgerPanel activityLedgerPanel">
              <header>
                <h2>Activity stream</h2>
                <span className={data.readiness?.production_ready ? "systemState ready" : "systemState"}>{data.readiness?.production_ready ? "Systems ready" : "Local mode"}</span>
              </header>
              <div className="instrumentActivity">
                {activity.map((item, index) => (
                  <button className="instrumentActivityRow" key={`${item.source}-${item.action}-${index}`} onClick={() => maybeOpenActivity(item, data, onIssue, onRun, onPr)} type="button">
                    <i className={statusTone(item.status)} aria-hidden="true" />
                    <span><strong>{labelize(item.action)}</strong><small>{labelize(item.source)} · {labelize(item.status)}</small></span>
                    <time>{formatClock(item.created_at)}</time>
                  </button>
                ))}
                {activity.length === 0 ? <EmptyState text="No activity has been recorded yet." /> : null}
              </div>
              <button className="ledgerFooter" onClick={() => onRunTrace(activeRun)} type="button">Open full timeline <ExternalLink size={15} /></button>
            </section>
          </div>

          <footer className="instrumentFooter">
            <span>Evidence-first AI software engineering control plane.</span>
            <button onClick={onSecurity} type="button"><i /> {data.readiness?.blockers.length ? `${data.readiness.blockers.length} readiness blockers` : "All configured systems operational"}</button>
          </footer>
        </>
      )}
      {matchingIssues.length === 0 && query ? <EmptyState text="No tasks match the current search." /> : null}
    </div>
  );
}

function RepositoriesScreen({
  data,
  query,
  onConnect,
  onRepo,
  setQuery,
  setStatusFilter,
  statusFilter
}: {
  data: ConsoleState;
  query: string;
  onConnect: () => void;
  onRepo: (repo: RepositoryResponse) => void;
  setQuery: (query: string) => void;
  setStatusFilter: (filter: RepoStatusFilter) => void;
  statusFilter: RepoStatusFilter;
}) {
  const repos = data.repositories.filter((repo) => {
    const matchesQuery = searchable(`${repo.owner}/${repo.name} ${repo.language ?? ""} ${repo.framework ?? ""}`, query);
    if (!matchesQuery) return false;
    if (statusFilter === "indexed") return Boolean(repo.last_indexed_sha);
    if (statusFilter === "needs-indexing") return !repo.last_indexed_sha;
    if (statusFilter === "ci-failing") {
      return data.pullRequests.some((pr) => repositoryMatchesId(repo, pr.repository?.id) && failedCi(pr.ci_status));
    }
    return true;
  });
  const indexed = data.repositories.filter((repo) => repo.last_indexed_sha).length;
  const needsIndex = data.repositories.filter((repo) => !repo.last_indexed_sha).length;
  const ciFailing = data.repositories.filter((repo) => data.pullRequests.some((pr) => repositoryMatchesId(repo, pr.repository?.id) && failedCi(pr.ci_status))).length;
  return (
    <div className="screen">
      <ScreenHeader title="Repositories" subtitle="Connected GitHub repositories and indexing status." />
      <GitHubSyncPanel data={data} onConnect={onConnect} compact />
      <div className="toolbar">
        <label className="inlineSearch">
          <Search size={18} />
          <input
            aria-label="Search repositories"
            maxLength={120}
            onChange={(event) => setQuery(boundedSearchQuery(event.target.value))}
            onKeyDown={(event) => { if (event.key === "Escape") setQuery(""); }}
            placeholder="Search repositories..."
            type="search"
            value={query}
          />
          {query ? <button aria-label="Clear repository search" onClick={() => setQuery("")} type="button"><X size={16} /></button> : null}
        </label>
        <Segment label={`All (${data.repositories.length})`} active={statusFilter === "all"} onClick={() => setStatusFilter("all")} />
        <Segment label={`Indexed (${indexed})`} active={statusFilter === "indexed"} onClick={() => setStatusFilter("indexed")} />
        <Segment label={`Needs indexing (${needsIndex})`} active={statusFilter === "needs-indexing"} onClick={() => setStatusFilter("needs-indexing")} />
        <Segment label={`CI failing (${ciFailing})`} active={statusFilter === "ci-failing"} onClick={() => setStatusFilter("ci-failing")} />
        <button className="primaryAction pushRight" onClick={onConnect} type="button">
          <Github size={20} />
          {isGithubAccountConnected(data) ? "Sync GitHub repos" : "Connect GitHub"}
        </button>
      </div>
      <div className="sideGrid">
        <section className="panel tablePanel">
          <table className="reposTable">
            <thead>
              <tr>
                <th scope="col">Repository</th>
                <th scope="col">Language</th>
                <th scope="col">Framework</th>
                <th scope="col">Last indexed</th>
                <th scope="col">Open issues</th>
                <th scope="col">Agent-ready</th>
                <th scope="col">Tests</th>
                <th scope="col">Coverage</th>
                <th scope="col">CI</th>
              </tr>
            </thead>
            <tbody>
              {repos.map((repo) => (
                <tr key={repo.id} onClick={() => onRepo(repo)} tabIndex={0} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onRepo(repo); } }} role="row">
                  <td>
                    <span className="repoName">
                      <Github size={20} />
                      {repo.owner}/{repo.name}
                    </span>
                  </td>
                  <td>{repo.language ?? "Unavailable"}</td>
                  <td>{repo.framework ?? "Unavailable"}</td>
                  <td><code>{repo.last_indexed_sha ? repo.last_indexed_sha.slice(0, 7) : "not indexed"}</code></td>
                  <td>{repo.issue_count}</td>
                  <td className="greenText">{data.issues.filter((issue) => repositoryMatchesId(repo, issue.repository_id) && normalizedStatus(issue.status) === "agent_ready").length}</td>
                  <td>{repo.test_file_count ?? 0}</td>
                  <td>Unavailable</td>
                  <td><Badge tone={repositoryIndexTone(repo)}>{repositoryIndexLabel(repo)}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
          {repos.length === 0 ? <EmptyState text="No repositories are connected yet." /> : null}
        </section>
        <aside className="panel summaryPanel">
          <h2>Indexing Health</h2>
          <SummaryItem icon={Database} label="Indexed repos" onClick={() => setStatusFilter("indexed")} value={indexed} tone="success" />
          <SummaryItem icon={Clock3} label="Needs indexing" onClick={() => setStatusFilter("needs-indexing")} value={needsIndex} tone="warning" />
          <SummaryItem icon={X} label="CI failing repos" onClick={() => setStatusFilter("ci-failing")} value={ciFailing} tone="danger" />
          <SummaryItem icon={RefreshCcw} label="Last full sync" value={lastIndexedLabel(data.repositories)} tone="info" />
        </aside>
      </div>
    </div>
  );
}

function RepositoryDetailScreen({
  repo,
  issues,
  onIndex,
  onIssue,
  onIssues
}: {
  repo: RepositoryResponse | null;
  issues: IssueResponse[];
  onIndex: (repo: RepositoryResponse) => void;
  onIssue: (issue: IssueResponse) => void;
  onIssues: () => void;
}) {
  if (!repo) {
    return <EmptyState text="Select a repository to view details." />;
  }
  const repoIssues = issues.filter((issue) => repositoryMatchesId(repo, issue.repository_id));
  const highRisk = repoIssues.filter((issue) => issue.risk_score >= 70);
  const agentReady = repoIssues.filter((issue) => normalizedStatus(issue.status) === "agent_ready");
  return (
    <div className="screen">
      <Breadcrumb trail={[{ label: "Repositories", view: "repositories" }, { label: repo.name }]} />
      <div className="titleRow">
        <ScreenHeader title={repo.name} subtitle={`${repo.framework ?? repo.language ?? "Repository"} monitored by RepoPilot AI.`} />
        <button
          className="primaryAction"
          disabled={repo.acquirable === false}
          onClick={() => onIndex(repo)}
          title={repo.acquirable === false ? "Install the GitHub App on this OAuth-discovered repository before acquisition." : "Acquire the current GitHub ref and rebuild its index."}
          type="button"
        >
          <RefreshCcw size={20} />
          {repo.acquirable === false ? "GitHub App required" : "Acquire & index"}
        </button>
        <button className="ghostAction" onClick={onIssues} type="button">
          <ListChecks size={20} />
          View issues
        </button>
      </div>
      <section className="metaStrip">
        <MetaCard icon={Code2} label="Language" value={repo.language ?? "Unavailable"} />
        <MetaCard icon={Sparkles} label="Framework" value={repo.framework ?? "Unavailable"} />
        <MetaCard icon={GitBranch} label="Default branch" value={repo.default_branch} />
        <MetaCard icon={Github} label="Source access" value={repo.source_mode === "github_app" ? "GitHub App" : "OAuth discovery only"} />
        <MetaCard icon={FileCode2} label="Last indexed commit" value={repo.last_indexed_sha?.slice(0, 8) ?? "Not indexed"} mono />
        <MetaCard icon={Database} label="Index status" value={repositoryIndexLabel(repo)} tone={repositoryIndexTone(repo)} />
        <MetaCard icon={Box} label="Chunker" value={repo.chunker_version ?? "Unavailable"} mono />
        <MetaCard icon={Fingerprint} label="Fingerprint" value={repo.content_fingerprint?.slice(0, 12) ?? "Unavailable"} mono />
      </section>
      <section className="statGrid six">
        <StatCard label="Files indexed" value={repo.indexed_file_count ?? 0} icon={FileText} />
        <StatCard label="Code chunks" value={repo.code_chunk_count ?? 0} icon={Box} />
        <StatCard label="Tests detected" value={repo.test_file_count ?? 0} icon={Wrench} />
        <StatCard label="Coverage" value="Unavailable" icon={Circle} />
        <StatCard label="Open issues" value={repo.issue_count} icon={AlertCircle} />
        <StatCard label="Agent-ready issues" value={agentReady.length} icon={Bot} />
      </section>
      <div className="dashboardGrid">
        <section className="panel">
          <PanelHeader title="Issue Queue" />
          <div className="compactTable">
            {repoIssues.slice(0, 5).map((issue) => (
              <button className="compactRow" key={issue.id} onClick={() => onIssue(issue)} type="button">
                <code>#{issue.number}</code>
                <strong>{issue.title}</strong>
                <Badge tone={riskTone(issue.risk_score)}>{riskLabel(issue.risk_score)}</Badge>
                <Badge tone={statusTone(issue.status)}>{labelize(issue.status)}</Badge>
              </button>
            ))}
            {repoIssues.length === 0 ? <EmptyState text="This repository has no tracked issues." /> : null}
          </div>
        </section>
        <section className="panel">
          <PanelHeader title="Risk Areas" />
          {highRisk.slice(0, 4).map((issue) => (
            <button className="riskArea" key={issue.id} onClick={() => onIssue(issue)} type="button">
              <ShieldAlert size={24} />
              <span>
                <strong>{issue.issue_type ?? "Uncategorized"}</strong>
                <small>{issue.title}</small>
              </span>
            </button>
          ))}
          {highRisk.length === 0 ? <EmptyState text="No high-risk issue areas are currently open." /> : null}
        </section>
      </div>
    </div>
  );
}

function IssuesScreen({
  issues,
  repositories,
  query,
  mode,
  repositoryFilter,
  riskFilter,
  typeFilter,
  setMode,
  setRepositoryFilter,
  setRiskFilter,
  setTypeFilter,
  onIssue,
  onIssueAction,
  onNewTask
}: {
  issues: IssueResponse[];
  repositories: RepositoryResponse[];
  query: string;
  mode: "board" | "queue";
  repositoryFilter: string;
  riskFilter: IssueRiskFilter;
  typeFilter: string;
  setMode: (mode: "board" | "queue") => void;
  setRepositoryFilter: (filter: string) => void;
  setRiskFilter: (filter: IssueRiskFilter) => void;
  setTypeFilter: (filter: string) => void;
  onIssue: (issue: IssueResponse) => void;
  onIssueAction: (issue: IssueResponse) => void;
  onNewTask: () => void;
}) {
  const issueTypes = Array.from(new Set(issues.map((issue) => issue.issue_type).filter((value): value is string => Boolean(value)))).sort();
  const selectedRepository = repositories.find((repo) => repo.id === repositoryFilter) ?? null;
  const filtered = filterIssues(issues, query).filter((issue) => {
    if (repositoryFilter !== "all" && (!selectedRepository || !repositoryMatchesId(selectedRepository, issue.repository_id))) return false;
    if (riskFilter !== "all" && riskBucket(issue.risk_score) !== riskFilter) return false;
    if (typeFilter !== "all" && issue.issue_type !== typeFilter) return false;
    return true;
  });
  return (
    <div className="screen">
      <ScreenHeader title={mode === "board" ? "Task board" : "Task queue"} subtitle="Move work from triage through approval, execution, and review." />
      {filtered.length === 0 ? (
        <section className="panel emptyActionPanel compact">
          <span>
            <strong>{issues.length === 0 ? "No tasks yet" : "No issues match the current filters"}</strong>
            <small>{issues.length === 0 ? "Create a task to start triage and plan preparation." : "You can create a new task or adjust the filters above the board."}</small>
          </span>
          <button className="primaryAction" onClick={onNewTask} type="button"><Sparkles size={18} /> New task</button>
        </section>
      ) : null}
      <div className="toolbar">
        <select aria-label="Filter tasks by repository" onChange={(event) => setRepositoryFilter(event.target.value)} value={repositoryFilter}>
          <option value="all">All repositories</option>
          {repositories.map((repo) => (
            <option key={repo.id} value={repo.id}>{repo.owner}/{repo.name}</option>
          ))}
        </select>
        <select aria-label="Filter tasks by risk" onChange={(event) => setRiskFilter(event.target.value as IssueRiskFilter)} value={riskFilter}>
          <option value="all">All risks</option>
          <option value="low">Low risk</option>
          <option value="medium">Medium risk</option>
          <option value="high">High risk</option>
        </select>
        <select aria-label="Filter tasks by type" onChange={(event) => setTypeFilter(event.target.value)} value={typeFilter}>
          <option value="all">All types</option>
          {issueTypes.map((type) => <option key={type} value={type}>{labelize(type)}</option>)}
        </select>
        <button aria-pressed={mode === "board"} className={mode === "board" ? "segment active" : "segment"} onClick={() => setMode("board")} type="button">
          <LayoutGrid size={16} /> Board
        </button>
        <button aria-pressed={mode === "queue"} className={mode === "queue" ? "segment active" : "segment"} onClick={() => setMode("queue")} type="button">
          <ListChecks size={16} /> Queue
        </button>
        <button className="primaryAction pushRight" onClick={onNewTask} type="button"><Sparkles size={18} /> New task</button>
      </div>
      {mode === "board" ? (
        <div className="kanban">
          {issueBoardColumns.map((column) => {
            const columnIssues = filtered.filter((issue) => column.states.includes(issueColumn(issue)));
            return (
              <section className="kanbanColumn" key={column.key}>
                <h2>{column.label} <span>{columnIssues.length}</span></h2>
                {columnIssues.map((issue) => (
                  <button className="issueCard" key={issue.id} onClick={() => onIssue(issue)} type="button" aria-label={`Issue #${issue.number} ${issue.title}`}>
                    <small>#{issue.number}</small>
                    <strong>{issue.title}</strong>
                    <span className="cardBadges">
                      <Badge tone="info">{issue.issue_type ?? "Issue"}</Badge>
                      <Badge tone={riskTone(issue.risk_score)}>{riskLabel(issue.risk_score)}</Badge>
                    </span>
                    <span className="cardFooter">
                      <Badge tone={statusTone(issue.status)}>{labelize(issue.status)}</Badge>
                      <span>...</span>
                    </span>
                  </button>
                ))}
              </section>
            );
          })}
        </div>
      ) : (
        <div className="sideGrid">
          <section className="panel tablePanel">
            <table className="issuesTable">
              <thead>
                <tr>
                  <th scope="col">Issue</th>
                  <th scope="col">Title</th>
                  <th scope="col">Type</th>
                  <th scope="col">Complexity</th>
                  <th scope="col">Risk</th>
                  <th scope="col">Status</th>
                  <th scope="col">Repository</th>
                  <th scope="col">Next action</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((issue) => (
                  <tr key={issue.id} onClick={() => onIssue(issue)} tabIndex={0} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onIssue(issue); } }} role="row">
                    <td><code>#{issue.number}</code></td>
                    <td>{issue.title}</td>
                    <td><Badge tone="info">{issue.issue_type ?? "Unknown"}</Badge></td>
                    <td><Badge tone={complexityTone(issue.complexity)}>{issue.complexity ?? "Unknown"}</Badge></td>
                    <td><Badge tone={riskTone(issue.risk_score)}>{riskLabel(issue.risk_score)}</Badge></td>
                    <td><Badge tone={statusTone(issue.status)}>{labelize(issue.status)}</Badge></td>
                    <td>{issue.repository?.name ?? "Unavailable"}</td>
                    <td><button className="rowAction" onClick={(event) => { event.stopPropagation(); onIssueAction(issue); }} type="button">{issueQueueAction(issue).label} <ChevronRight size={16} /></button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
          <aside className="panel summaryPanel">
            <h2>Issue Summary</h2>
            <SummaryItem icon={Bot} label="Agent-ready" value={filtered.filter((issue) => normalizedStatus(issue.status) === "agent_ready").length} tone="success" />
            <SummaryItem icon={Clock3} label="Awaiting approval" value={filtered.filter((issue) => isPlanAwaitingApproval(issue.plan?.approval_status)).length} tone="warning" />
            <SummaryItem icon={X} label="Blocked" value={filtered.filter((issue) => issueColumn(issue) === "blocked").length} tone="danger" />
          <SummaryItem icon={ShieldAlert} label="High risk" onClick={() => setRiskFilter("high")} value={filtered.filter((issue) => issue.risk_score >= 70).length} tone="danger" />
          </aside>
        </div>
      )}
    </div>
  );
}

function IssueDetailScreen({
  issue,
  onGeneratePlan,
  onApprove,
  onReject,
  onRevise
}: {
  issue: IssueResponse | null;
  onGeneratePlan: (issue: IssueResponse) => void;
  onApprove: (issue: IssueResponse) => void;
  onReject: (issue: IssueResponse) => void;
  onRevise: (issue: IssueResponse) => void;
}) {
  if (!issue) {
    return <EmptyState text="Select an issue to view details." />;
  }
  const plan = issue.plan?.plan ?? {};
  const filesToInspect = stringList(plan.files_to_inspect);
  const filesToModify = stringList(plan.files_to_modify);
  const testsToAdd = stringList(plan.tests_to_add);
  const intendedChanges = stringList(plan.intended_changes);
  const commandsToRun = stringList(plan.commands_to_run);
  const validationStrategy = stringList(plan.validation_strategy);
  const assumptions = stringList(plan.assumptions);
  const contextCitations = stringList(plan.context_citations);
  const riskNotes = stringList(plan.risk_notes);
  const planSummary = stringValue(plan.summary);
  const rollbackPlan = stringValue(plan.rollback_plan);
  const planHash = stringValue(plan.approved_plan_hash) || stringValue(plan.plan_hash);
  const policyDecision = recordValue(plan.approval_policy_decision) ?? recordValue(plan.policy_decision);
  const policyLabel = stringValue(policyDecision?.decision) || stringValue(policyDecision?.status) || "Not evaluated";
  const policyNotes = [
    ...stringList(policyDecision?.reasons),
    ...stringList(policyDecision?.matched_patterns),
    ...stringList(policyDecision?.violations)
  ];
  const awaitingApproval = isPlanAwaitingApproval(issue.plan?.approval_status);
  return (
    <div className="screen">
      <Breadcrumb trail={[{ label: "Tasks", view: "issues" }, { label: `#${issue.number}` }]} />
      <div className="titleRow">
        <ScreenHeader title={`#${issue.number} ${issue.title}`} subtitle={issue.repository ? `${issue.repository.owner}/${issue.repository.name}` : "Tracked GitHub issue"} />
        <Badge tone={statusTone(issue.plan?.approval_status ?? issue.status)}>{labelize(issue.plan?.approval_status ?? issue.status)}</Badge>
      </div>
      <div className="detailGrid">
        <section className="detailStack">
          <InfoPanel number="1" title="Original Task">
            <p className="issueBody">{issue.body_text?.trim() || issue.title}</p>
          </InfoPanel>
          <InfoPanel number="2" title="Triage Result">
            <div className="fieldGrid">
              <Field label="Type" value={issue.issue_type ?? "Unavailable"} tone="info" />
              <Field label="Complexity" value={issue.complexity ?? "Unavailable"} tone={complexityTone(issue.complexity)} />
              <Field label="Risk" value={riskLabel(issue.risk_score)} tone={riskTone(issue.risk_score)} />
              <Field label="Area" value={issue.issue_type ?? "Unavailable"} tone="info" />
              <Field label="Recommended action" value={nextIssueAction(issue)} />
            </div>
          </InfoPanel>
          <InfoPanel number="3" title="Plan Summary">
            {planSummary ? <p>{planSummary}</p> : <EmptyState text="Generate a plan to populate the review summary." />}
          </InfoPanel>
          <InfoPanel number="4" title="Retrieved Code Context">
            <PillList items={contextCitations.length ? contextCitations : filesToInspect} empty="No cited repository context is attached to this plan yet." />
          </InfoPanel>
          <div className="threePanels">
            <InfoPanel number="5" title="Intended Changes">
              <NumberedList items={intendedChanges.length ? intendedChanges : filesToModify} empty="Generate a plan to populate intended changes." />
            </InfoPanel>
            <InfoPanel number="6" title="Validation Plan">
              <PillList items={commandsToRun} empty="No validation commands are attached yet." />
              <Bullets items={[...validationStrategy, ...testsToAdd.map((item) => `Test scope: ${item}`)]} empty="No validation strategy is attached yet." />
            </InfoPanel>
            <InfoPanel number="7" title="Security Notes">
              <Bullets items={riskNotes} empty="No security notes are attached yet." />
            </InfoPanel>
          </div>
          <div className="threePanels">
            <InfoPanel number="8" title="Assumptions">
              <Bullets items={assumptions} empty="No plan assumptions are recorded." />
            </InfoPanel>
            <InfoPanel number="9" title="Rollback Plan">
              {rollbackPlan ? <p>{rollbackPlan}</p> : <EmptyState text="No rollback plan is attached yet." />}
            </InfoPanel>
            <InfoPanel number="10" title="Approval Policy">
              <Field label="Decision" value={labelize(policyLabel)} tone={statusTone(policyLabel)} />
              <Bullets items={policyNotes} empty="No additional policy notes are recorded." />
            </InfoPanel>
          </div>
        </section>
        <aside className="panel contextPanel">
          <Field label="Status" value={labelize(issue.plan?.approval_status ?? issue.status)} tone={statusTone(issue.plan?.approval_status ?? issue.status)} />
          <Field label="Plan version" value={issue.plan ? `v${issue.plan.version}` : "Unavailable"} />
          <Field label="Approval recorded" value={issue.plan?.approved_at ? relativeTime(issue.plan.approved_at) : "Not approved"} />
          <Field label="Plan hash" value={planHash ? shortId(planHash) : "Unavailable"} mono />
          <Field label="Risk" value={riskLabel(issue.risk_score)} tone={riskTone(issue.risk_score)} />
          <Field label="Run" value={issue.run ? shortId(issue.run.id) : "Unavailable"} />
          <Field label="Provider-reported cost (USD)" value={issue.run ? formatUsd(issue.run.total_cost) : "Unavailable"} />
          <Field label="Confidence" value={issue.run ? "From trace data" : "Unavailable"} />
          <button className="primaryAction wide" onClick={() => onApprove(issue)} disabled={!awaitingApproval} title={awaitingApproval ? "Approve the current plan and continue." : "Only a plan awaiting approval can be approved."} type="button">
            <Check size={20} />
            Approve Plan
          </button>
          <button className="ghostAction wide" onClick={() => onRevise(issue)} disabled={!issue.plan} title={!issue.plan ? "Generate a plan before requesting a revision." : "Request changes to the current plan."} type="button">
            <RotateCcw size={18} />
            Request Revision
          </button>
          <button className="ghostAction wide" onClick={() => onGeneratePlan(issue)} type="button">
            <RotateCcw size={18} />
            Generate New Plan
          </button>
          <button className="dangerAction wide" onClick={() => onReject(issue)} disabled={!awaitingApproval} title={awaitingApproval ? "Reject the current plan." : "Only a plan awaiting approval can be rejected."} type="button">
            <X size={18} />
            Reject Plan
          </button>
        </aside>
      </div>
    </div>
  );
}

function AgentRunsScreen({
  runs,
  selectedRun,
  trace,
  issues,
  isActionPending,
  onPrimaryAction,
  query,
  onRun,
  onStop
}: {
  runs: RunSummary[];
  selectedRun: RunSummary | null;
  trace: TraceData | null;
  issues: IssueResponse[];
  isActionPending: boolean;
  query: string;
  onPrimaryAction: (run: RunSummary) => void;
  onRun: (run: RunSummary, target?: View) => void;
  onStop: (run: RunSummary) => void;
}) {
  const filtered = filterRuns(runs, issues, query);
  const run = selectedRun ?? filtered[0] ?? null;
  const issue = run ? issues.find((item) => item.id === run.issue_id) : null;
  const primaryAction = run ? primaryRunAction(run) : null;
  const terminal = run ? isTerminalRunState(run.state) : false;
  const planApprovalRequired = run?.state.toUpperCase() === "WAIT_FOR_APPROVAL" && issue?.plan?.approval_status !== "approved";
  const actionUnavailableLabel = planApprovalRequired ? "Approve plan to continue" : run ? runActionStatus(run.state) : "Unavailable";
  return (
    <div className="screen">
      <Breadcrumb trail={[{ label: "Agent Runs", view: "agent-runs" }, { label: run ? shortId(run.id) : "No run" }]} />
      <ScreenHeader title={run ? `Agent Run #${shortId(run.id)}` : "Agent Runs"} subtitle={issue ? `Issue #${issue.number} - ${issue.title}` : "Workflow execution state and evidence."} />
      <section className="statGrid five">
        <StatCard label="Status" value={run ? labelize(run.state) : "Unavailable"} icon={Clock3} />
        <StatCard label="Risk" value={issue ? riskLabel(issue.risk_score) : "Unavailable"} icon={ShieldAlert} />
        <StatCard label="Steps recorded" value={trace?.steps?.length ?? 0} icon={Bot} />
        <StatCard label="Recorded runtime" value={run ? recordedRunDuration(run, trace) : "Unavailable"} icon={Clock3} />
        <StatCard label="Provider cost (USD)" value={run ? formatUsd(run.total_cost) : "Unavailable"} icon={KeyRound} />
      </section>
      <div className="sideGrid">
        <section className="panel">
          <PanelHeader title="Run Timeline" />
          <div className="timelineList">
            {(trace?.steps ?? []).map((step, index) => (
              <button className="timelineRow" key={`${step.step_name}-${index}`} onClick={() => run && onRun(run, "run-trace")} type="button">
                <span className="timelineNumber">{index + 1}</span>
                <span className={step.status === "succeeded" ? "timelineLine done" : "timelineLine"} />
                <strong>{labelize(step.step_name)}</strong>
                <span>{agentName(step.step_name)}</span>
                <time>{formatClock(step.created_at)}</time>
                <Badge tone={statusTone(step.status)}>{labelize(step.status)}</Badge>
                <span className="rowAction">View details <ChevronDown size={16} /></span>
              </button>
            ))}
            {(!trace?.steps || trace.steps.length === 0) ? <EmptyState text="Trace steps are not available for this run yet." /> : null}
          </div>
          {run ? (
            <div className="panelActions">
              <button
                className="primaryAction"
                disabled={!primaryAction || planApprovalRequired || isActionPending}
                onClick={() => onPrimaryAction(run)}
                title={planApprovalRequired ? "Approve the linked plan before starting implementation." : primaryAction?.detail ?? runActionStatus(run.state)}
                type="button"
              >
                <Play size={18} />
                {isActionPending ? "Working..." : planApprovalRequired ? actionUnavailableLabel : primaryAction?.label ?? actionUnavailableLabel}
              </button>
              <button className="ghostAction" onClick={() => onRun(run, "run-trace")} type="button">Open trace</button>
              <button className="dangerAction" disabled={terminal || isActionPending} onClick={() => onStop(run)} type="button">Stop run</button>
            </div>
          ) : null}
        </section>
        <aside className="panel contextPanel">
          <h2>Run Context</h2>
          <Field label="Current state" value={run ? run.state : "Unavailable"} mono />
          <Field label="Plan" value={run?.plan_id ? shortId(run.plan_id) : "Unavailable"} mono />
          <Field label="Pull request" value={trace?.pull_requests?.[0] ? `#${trace.pull_requests[0].number}` : "Unavailable"} />
          <Field label="Next action" value={planApprovalRequired ? actionUnavailableLabel : primaryAction?.label ?? actionUnavailableLabel} />
          {primaryAction ? <p className="mutedText">{planApprovalRequired ? "Review and approve the linked plan before implementation starts." : primaryAction.detail}</p> : null}
          <div className="miniRunList">
            {filtered.slice(0, 8).map((item) => (
              <button className={run?.id === item.id ? "miniRun active" : "miniRun"} key={item.id} onClick={() => onRun(item)} type="button">
                <span>{shortId(item.id)}</span>
                <Badge tone={statusTone(item.state)}>{labelize(item.state)}</Badge>
              </button>
            ))}
          </div>
        </aside>
      </div>
    </div>
  );
}

function RunTraceScreen({
  selectedRun,
  trace,
  tab,
  setTab
}: {
  selectedRun: RunSummary | null;
  trace: TraceData | null;
  tab: "timeline" | "tools" | "prompts" | "artifacts" | "audit";
  setTab: (tab: "timeline" | "tools" | "prompts" | "artifacts" | "audit") => void;
}) {
  const steps = trace?.steps ?? [];
  const llm = trace?.llm_traces ?? [];
  const toolSteps = steps.filter((step) => step.step_name.toUpperCase().startsWith("TOOL_CALL:"));
  const visibleSteps = tab === "tools" ? toolSteps : steps;
  const errors = steps.filter((step) => ["failed", "blocked"].includes(step.status.toLowerCase())).length;
  return (
    <div className="screen">
      <Breadcrumb trail={[
        { label: "Agent Runs", view: "agent-runs" },
        { label: selectedRun ? shortId(selectedRun.id) : "Run", view: "agent-runs", entityId: selectedRun?.id },
        { label: "Trace" }
      ]} />
      <ScreenHeader title={`Trace: ${selectedRun ? shortId(selectedRun.id) : "Unavailable"}`} subtitle="Detailed agent decisions, tool calls, latency, and outputs." />
      <section className="statGrid five">
        <StatCard label="Total tool calls" value={toolSteps.length} icon={Wrench} />
        <StatCard label="LLM calls" value={llm.length} icon={Sparkles} />
        <StatCard label="Tokens" value={trace?.run?.total_tokens ?? selectedRun?.total_tokens ?? 0} icon={Database} />
        <StatCard label="Provider cost (USD)" value={formatUsd(trace?.run?.total_cost ?? selectedRun?.total_cost ?? 0)} icon={KeyRound} />
        <StatCard label="Errors" value={errors} icon={AlertTriangle} />
      </section>
      <div aria-label="Run trace sections" className="tabs" role="tablist">
        {["timeline", "tools", "prompts", "artifacts", "audit"].map((item) => (
          <button aria-controls={`run-trace-panel-${item}`} aria-selected={tab === item} className={tab === item ? "tab active" : "tab"} id={`run-trace-tab-${item}`} key={item} onClick={() => setTab(item as typeof tab)} role="tab" type="button">
            {labelize(item)}
          </button>
        ))}
      </div>
      <div aria-labelledby={`run-trace-tab-${tab}`} className="sideGrid" id={`run-trace-panel-${tab}`} role="tabpanel">
        <section className="panel tablePanel">
          <PanelHeader title={tab === "tools" ? "Tool Call Trace" : `${labelize(tab)} Trace`} />
          {tab === "tools" || tab === "timeline" ? (
            <table className="traceTable">
              <thead>
                <tr>
                  <th scope="col">Time</th>
                  <th scope="col">Lane</th>
                  <th scope="col">Tool</th>
                  <th scope="col">Output summary</th>
                  <th scope="col">Latency</th>
                  <th scope="col">Status</th>
                </tr>
              </thead>
              <tbody>
                {visibleSteps.map((step, index) => (
                  <tr key={`${step.step_name}-${index}`}>
                    <td>{formatClock(step.created_at)}</td>
                    <td>{agentName(step.step_name)}</td>
                    <td><code>{step.step_name.toLowerCase()}</code></td>
                    <td>{summaryFromOutput(step.output_json)}</td>
                    <td>{step.latency_ms ? `${(step.latency_ms / 1000).toFixed(1)}s` : "Unavailable"}</td>
                    <td><Badge tone={statusTone(step.status)}>{labelize(step.status)}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
          {tab === "prompts" ? <TraceJson items={llm.map((item) => ({ ...item, prompt_hash: item.prompt_hash }))} /> : null}
          {tab === "artifacts" ? <TraceJson items={trace?.artifacts ?? []} /> : null}
          {tab === "audit" ? <TraceJson items={trace?.audit_events ?? []} /> : null}
        </section>
        <aside className="panel contextPanel">
          <h2>{tab === "tools" ? "First Tool Call" : "First Trace Step"}</h2>
          {visibleSteps[0] ? (
            <>
              <Field label="Lane" value={agentName(visibleSteps[0].step_name)} />
              <Field label="Tool" value={visibleSteps[0].step_name.toLowerCase()} mono />
              <Field label="Output" value={summaryFromOutput(visibleSteps[0].output_json)} />
              <Field label="Latency" value={visibleSteps[0].latency_ms ? `${(visibleSteps[0].latency_ms / 1000).toFixed(1)}s` : "Unavailable"} />
              <Field label="Status" value={labelize(visibleSteps[0].status)} tone={statusTone(visibleSteps[0].status)} />
            </>
          ) : (
            <EmptyState text={tab === "tools" ? "No tool calls were recorded for this run." : "No trace steps were recorded for this run."} />
          )}
        </aside>
      </div>
    </div>
  );
}

function PullRequestsScreen({
  ciFilter,
  prs,
  query,
  repositories,
  repositoryFilter,
  riskFilter,
  securityFilter,
  setCiFilter,
  setRepositoryFilter,
  setRiskFilter,
  setSecurityFilter,
  setStatusFilter,
  statusFilter,
  onPr
}: {
  ciFilter: PrCiFilter;
  prs: PullRequestSummary[];
  query: string;
  repositories: RepositoryResponse[];
  repositoryFilter: string;
  riskFilter: IssueRiskFilter;
  securityFilter: PrSecurityFilter;
  setCiFilter: (filter: PrCiFilter) => void;
  setRepositoryFilter: (filter: string) => void;
  setRiskFilter: (filter: IssueRiskFilter) => void;
  setSecurityFilter: (filter: PrSecurityFilter) => void;
  setStatusFilter: (filter: PrStatusFilter) => void;
  statusFilter: PrStatusFilter;
  onPr: (pr: PullRequestSummary) => void;
}) {
  const selectedRepository = repositories.find((repo) => repo.id === repositoryFilter) ?? null;
  const filtered = prs.filter((pr) => {
    if (!searchable(`${pr.pr_number} ${pr.issue?.title ?? ""} ${pr.repository?.name ?? ""} ${pr.status} ${prModeLabel(pr)}`, query)) return false;
    if (repositoryFilter !== "all" && (!selectedRepository || !repositoryMatchesId(selectedRepository, pr.repository?.id))) return false;
    if (statusFilter !== "all" && pr.status !== statusFilter) return false;
    if (riskFilter !== "all" && riskBucket(pr.risk_score) !== riskFilter) return false;
    if (ciFilter === "passed" && !passedCi(pr.ci_status)) return false;
    if (ciFilter === "failed" && !failedCi(pr.ci_status)) return false;
    if (ciFilter === "unknown" && pr.ci_status) return false;
    const security = securityEvidencePresentation(pr);
    if (securityFilter === "passed" && !security.passed) return false;
    if (securityFilter === "open" && security.state !== "failed") return false;
    return true;
  });
  return (
    <div className="screen">
      <ScreenHeader title="Reviews" subtitle="Inspect generated changes, validation, security, and CI evidence in one place." />
      <div className="toolbar fiveFilters">
        <select aria-label="Filter reviews by repository" onChange={(event) => setRepositoryFilter(event.target.value)} value={repositoryFilter}>
          <option value="all">All repositories</option>
          {repositories.map((repo) => <option key={repo.id} value={repo.id}>{repo.owner}/{repo.name}</option>)}
        </select>
        <select aria-label="Filter reviews by status" onChange={(event) => setStatusFilter(event.target.value as PrStatusFilter)} value={statusFilter}>
          <option value="all">All statuses</option>
          <option value="draft">Draft</option>
          <option value="ready_for_review">Ready for review</option>
          <option value="blocked">Blocked</option>
        </select>
        <select aria-label="Filter reviews by risk" onChange={(event) => setRiskFilter(event.target.value as IssueRiskFilter)} value={riskFilter}>
          <option value="all">All risks</option>
          <option value="low">Low risk</option>
          <option value="medium">Medium risk</option>
          <option value="high">High risk</option>
        </select>
        <select aria-label="Filter reviews by CI status" onChange={(event) => setCiFilter(event.target.value as PrCiFilter)} value={ciFilter}>
          <option value="all">All CI states</option>
          <option value="passed">CI passed</option>
          <option value="failed">CI failed</option>
          <option value="unknown">CI N/A</option>
        </select>
        <select aria-label="Filter reviews by security status" onChange={(event) => setSecurityFilter(event.target.value as PrSecurityFilter)} value={securityFilter}>
          <option value="all">All security states</option>
          <option value="passed">No open findings</option>
          <option value="open">Open findings</option>
        </select>
      </div>
      <div className="sideGrid">
        <section className="panel reviewLedger" aria-label="Review queue">
          <header className="reviewLedgerHeader">
            <span>Work item</span>
            <span>Trust gates</span>
            <span>Updated</span>
          </header>
          <div>
            {filtered.map((pr) => (
              <button className="reviewRow" key={pr.pr_id} onClick={() => onPr(pr)} type="button">
                <span className="prNumberBadge mono">#{pr.pr_number}</span>
                <span className="reviewIdentity">
                  <strong>{pr.issue?.title ?? `Review #${pr.pr_number}`}</strong>
                  <small>{pr.issue ? `Issue #${pr.issue.number}` : "No linked issue"} · {prModeLabel(pr)}</small>
                </span>
                <span className="reviewGates">
                  <Badge tone={statusTone(pr.status)}>{labelize(pr.status)}</Badge>
                  <Badge tone={statusTone(pr.ci_status ?? "unknown")}>CI {labelize(pr.ci_status ?? "pending")}</Badge>
                  <Badge tone={securityEvidencePresentation(pr).tone}>Security {securityEvidencePresentation(pr).label}</Badge>
                  <Badge tone={riskTone(pr.risk_score)}>{riskLabel(pr.risk_score)}</Badge>
                </span>
                <time>{relativeTime(pr.created_at)}</time>
                <ChevronRight size={17} aria-hidden="true" />
              </button>
            ))}
            {filtered.length === 0 ? <EmptyState text="No reviews match the current filters." /> : null}
          </div>
        </section>
        <aside className="panel summaryPanel">
          <h2>Review summary</h2>
          <SummaryItem icon={FileText} label="Draft records" onClick={() => setStatusFilter("draft")} value={filtered.filter((pr) => pr.status === "draft").length} tone="violet" />
          <SummaryItem icon={Eye} label="Ready for review" onClick={() => setStatusFilter("ready_for_review")} value={filtered.filter((pr) => pr.status === "ready_for_review").length} tone="info" />
          <SummaryItem icon={X} label="Blocked PR records" onClick={() => setStatusFilter("blocked")} value={filtered.filter((pr) => pr.status === "blocked").length} tone="danger" />
          <SummaryItem icon={AlertCircle} label="CI failing" onClick={() => setCiFilter("failed")} value={filtered.filter((pr) => failedCi(pr.ci_status)).length} tone="danger" />
        </aside>
      </div>
    </div>
  );
}

function PullRequestDetailScreen({
  pr,
  onSecurityReview,
  onAnalyzeCi,
  onRevisionPlan,
  onOpenIssue,
  onOpenRun
}: {
  pr: PullRequestSummary | null;
  onSecurityReview: (pr: PullRequestSummary) => void;
  onAnalyzeCi: (pr: PullRequestSummary) => void;
  onRevisionPlan: (pr: PullRequestSummary) => void;
  onOpenIssue: (issueId: string) => void;
  onOpenRun: (runId: string) => void;
}) {
  if (!pr) {
    return <EmptyState text="Select a pull request to view details." />;
  }
  const validationEvidence = validationEvidencePresentation(pr);
  const securityEvidence = securityEvidencePresentation(pr);
  return (
    <div className="screen">
      <Breadcrumb trail={[{ label: "Reviews", view: "pull-requests" }, { label: `#${pr.pr_number}` }]} />
      <div className="titleRow">
        <ScreenHeader title={`PR #${pr.pr_number} ${pr.issue?.title ?? ""}`} subtitle="This tracked PR record includes RepoPilot evidence for human review." />
        <Badge tone={pr.is_local_record ? "warning" : "success"}>{prModeLabel(pr)}</Badge>
        <Badge tone={statusTone(pr.status)}>{labelize(pr.status)}</Badge>
        <Badge tone={riskTone(pr.risk_score)}>{riskLabel(pr.risk_score)}</Badge>
        <Badge tone={statusTone(pr.ci_status ?? "unknown")}>CI {labelize(pr.ci_status ?? "unknown")}</Badge>
        <Badge tone={securityEvidence.tone}>Security {securityEvidence.label}</Badge>
      </div>
      <div className="detailGrid">
        <section className="detailStack">
          <InfoPanel number="1" title="PR Summary">
            <p>{stringValue(pr.plan?.summary) || `PR #${pr.pr_number} linked to ${pr.issue ? `issue #${pr.issue.number}` : "tracked work"}.`}</p>
          </InfoPanel>
          <InfoPanel number="2" title="Linked Issue">
            <button className="linkedRow" disabled={!pr.issue} onClick={() => pr.issue && onOpenIssue(pr.issue.id)} type="button">
              <AlertCircle size={20} />
              {pr.issue ? `#${pr.issue.number} ${pr.issue.title}` : "No linked issue recorded"}
              <ExternalLink size={18} />
            </button>
          </InfoPanel>
          <InfoPanel number="3" title="Changed Files">
            <Field label="Current patch" value={pr.current_patch_hash ? shortId(pr.current_patch_hash) : "Unavailable"} mono />
            <PillList items={pr.changed_files} empty="No generated patch files are attached to this PR record." />
          </InfoPanel>
          <InfoPanel number="4" title="Planned Files">
            <PillList items={pr.planned_files} empty="No planned files are attached to this PR record." />
          </InfoPanel>
          <InfoPanel number="5" title="Test Results">
            <Field label="Validation summary" value={validationEvidence.label} tone={validationEvidence.tone} />
            <div className="resultStrip">
              {pr.validation_results.map((result) => (
                <Field key={result.command} label={result.command} value={labelize(result.status)} tone={statusTone(result.status)} />
              ))}
              {pr.validation_results.length === 0 ? <EmptyState text="No validation results are recorded for this PR." /> : null}
            </div>
          </InfoPanel>
          <InfoPanel number="6" title="Security Results">
            <Field label="Scan status" value={securityEvidence.label} tone={securityEvidence.tone} />
            <div className="resultStrip">
              {pr.security_findings.map((finding) => (
                <Field key={`${finding.tool}-${finding.description}`} label={finding.tool} value={labelize(finding.status)} tone={riskTone(severityScore(finding.severity))} />
              ))}
              {pr.security_findings.length === 0 ? <Field label="Security findings" value={securityEvidence.passed ? "No findings in completed scan" : "No finding records; scan is not proven clear"} tone={securityEvidence.passed ? "success" : "warning"} /> : null}
            </div>
          </InfoPanel>
          <InfoPanel number="7" title="Rollback Notes">
            <p>{stringValue(pr.plan?.rollback_plan) || "No rollback plan is attached to this PR record."}</p>
          </InfoPanel>
          <button className="traceLink" onClick={() => onOpenRun(pr.run_id)} type="button">
            8. Agent Trace <span>View {shortId(pr.run_id)} <ExternalLink size={16} /></span>
          </button>
        </section>
        <aside className="panel contextPanel">
          <h2>Reviewer Checklist</h2>
          <Field label="Record mode" value={prModeDetail(pr)} />
          <ReviewerChecklist pr={pr} />
          <button className="dangerAction wide" onClick={() => onAnalyzeCi(pr)} type="button">
            <FileCode2 size={18} />
            Analyze CI logs
          </button>
          <button className="cyanAction wide" onClick={() => onRevisionPlan(pr)} type="button">
            <RotateCcw size={18} />
            Create CI revision plan
          </button>
          <button className="cyanAction wide" onClick={() => onSecurityReview(pr)} type="button">
            <Shield size={18} />
            Run security review
          </button>
          <button className="ghostAction wide" disabled={!prGithubUrl(pr)} onClick={() => { const url = prGithubUrl(pr); if (url) window.open(url, "_blank", "noopener,noreferrer"); }} title={pr.is_local_record ? "This is a local RepoPilot PR record. No real GitHub PR has been opened yet." : "Open the real GitHub pull request."} type="button">
            <Github size={18} />
            {pr.is_local_record ? "Local PR record" : "Open in GitHub"}
          </button>
        </aside>
      </div>
    </div>
  );
}

function ReviewerChecklist({ pr }: { pr: PullRequestSummary }) {
  const items = reviewChecklist(pr);
  const storageKey = reviewChecklistStorageKey(pr);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [hydratedKey, setHydratedKey] = useState("");

  useBrowserLayoutEffect(() => {
    setChecked(parseStoredChecklist(window.localStorage.getItem(storageKey), items));
    setHydratedKey(storageKey);
  }, [storageKey]);

  useEffect(() => {
    if (hydratedKey !== storageKey) return;
    window.localStorage.setItem(storageKey, JSON.stringify(items.filter((item) => checked.has(item))));
  }, [checked, hydratedKey, items, storageKey]);

  return items.map((item) => (
    <label className="checkRow" key={item}>
      <input
        checked={checked.has(item)}
        onChange={(event) => {
          setChecked((current) => {
            const next = new Set(current);
            if (event.target.checked) next.add(item);
            else next.delete(item);
            return next;
          });
        }}
        type="checkbox"
      />
      <span>{item}</span>
    </label>
  ));
}

function SecurityScreen({
  findings,
  policy,
  query,
  onFinding
}: {
  findings: SecurityFindingResponse[];
  policy: PolicyResponse | null;
  query: string;
  onFinding: (finding: SecurityFindingResponse) => void;
}) {
  const filtered = findings.filter((finding) => searchable(`${finding.description} ${finding.tool} ${finding.repository?.name ?? ""}`, query));
  return (
    <div className="screen">
      <ScreenHeader title="Security" subtitle="Risk controls, open findings, and security evidence from agent workflows." />
      <section className="statGrid six">
        <StatCard label="Open high-risk findings" value={filtered.filter((finding) => severityScore(finding.severity) >= 70 && finding.status === "open").length} icon={ShieldAlert} />
        <StatCard label="Secrets detected" value={filtered.filter((finding) => finding.tool.toLowerCase().includes("secret")).length} icon={KeyRound} />
        <StatCard label="Dependency warnings" value={filtered.filter((finding) => finding.tool.toLowerCase().includes("dependency")).length} icon={AlertTriangle} />
        <StatCard label="CodeQL alerts" value={filtered.filter((finding) => finding.tool.toLowerCase().includes("codeql")).length} icon={Code2} />
        <StatCard label="Prompt injection attempts" value={filtered.filter((finding) => finding.tool.toLowerCase().includes("prompt")).length} icon={Shield} />
        <StatCard label="Workflow path findings" value={filtered.filter((finding) => finding.file_path?.includes(".github/workflows")).length} icon={GitBranch} />
      </section>
      <div className="sideGrid">
        <section className="panel tablePanel">
          <table className="findingsTable">
            <thead>
              <tr>
                <th scope="col">Finding</th>
                <th scope="col">Severity</th>
                <th scope="col">Source</th>
                <th scope="col">Repository</th>
                <th scope="col">Status</th>
                <th scope="col">Linked issue/PR</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((finding) => (
                <tr key={finding.id} onClick={() => onFinding(finding)} tabIndex={0} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onFinding(finding); } }} role="row">
                  <td>{finding.description}</td>
                  <td><Badge tone={riskTone(severityScore(finding.severity))}>{labelize(finding.severity)}</Badge></td>
                  <td>{finding.tool}</td>
                  <td>{finding.repository?.name ?? "Unavailable"}</td>
                  <td><Badge tone={statusTone(finding.status)}>{labelize(finding.status)}</Badge></td>
                  <td>{finding.issue ? `#${finding.issue.number}` : finding.pull_request ? `PR #${finding.pull_request.number}` : "Unavailable"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {filtered.length === 0 ? <EmptyState text="No security findings match the current data." /> : null}
        </section>
        <aside className="panel summaryPanel">
          <h2>Security policy</h2>
          <PolicyToggle label="Require approval for auth changes" enabled={policy?.high_risk_patterns.some((item) => item.includes("auth")) ?? false} />
          <PolicyToggle label="Require approval for CI workflow changes" enabled={policy?.high_risk_patterns.some((item) => item.includes(".github/workflows")) ?? false} />
          <PolicyToggle label="Block secret-reading commands" enabled={policy?.blocked_command_fragments.some((item) => item.includes(".env")) ?? false} />
          <PolicyToggle label="Auto-merge" enabled={false} />
        </aside>
      </div>
    </div>
  );
}

function SecurityDetailScreen({
  finding,
  onUpdateStatus
}: {
  finding: SecurityFindingResponse | null;
  onUpdateStatus: (finding: SecurityFindingResponse, status: string) => void;
}) {
  if (!finding) {
    return <EmptyState text="Select a security finding to view details." />;
  }
  return (
    <div className="screen">
      <Breadcrumb trail={[{ label: "Security", view: "security" }, { label: `Finding ${shortId(finding.id)}` }]} />
      <div className="titleRow">
        <ScreenHeader title={finding.description} />
        <Badge tone={riskTone(severityScore(finding.severity))}>{labelize(finding.severity)}</Badge>
        <Badge tone={statusTone(finding.status)}>{labelize(finding.status)}</Badge>
      </div>
      <div className="detailGrid">
        <section className="detailStack">
          <InfoPanel number="1" title="Finding Summary"><p>{finding.description}</p></InfoPanel>
          <InfoPanel number="2" title="Source"><p>{finding.tool}</p></InfoPanel>
          <InfoPanel number="3" title="Affected file"><PillList items={finding.file_path ? [finding.file_path] : []} empty="No affected file is attached." /></InfoPanel>
          <InfoPanel number="4" title="Linked item"><p>{finding.issue ? `Issue #${finding.issue.number} ${finding.issue.title}` : finding.pull_request ? `PR #${finding.pull_request.number}` : "No linked item recorded."}</p></InfoPanel>
          <InfoPanel number="5" title="Risk reasoning">
            <Bullets items={[finding.description, finding.status === "open" ? "Finding is still open." : `Finding status is ${finding.status}.`, finding.status_reason ? `Review note: ${finding.status_reason}` : "No review note recorded."]} />
          </InfoPanel>
          <InfoPanel number="6" title="Suggested remediation">
            <Bullets items={finding.file_path ? [`Review ${finding.file_path}.`, "Run the configured security scan again after changes."] : ["Review the linked run evidence."]} />
          </InfoPanel>
          <InfoPanel number="7" title="Evidence">
            <pre>{JSON.stringify(finding, null, 2)}</pre>
          </InfoPanel>
        </section>
        <aside className="panel contextPanel">
          <h2>Required action</h2>
          <Field label="Action" value={finding.status === "open" ? "Human security review" : "No active approval required"} tone={finding.status === "open" ? "danger" : "success"} />
          <button className="cyanAction wide" onClick={() => onUpdateStatus(finding, "acknowledged")} type="button">Acknowledge</button>
          <button className="ghostAction wide" onClick={() => onUpdateStatus(finding, "false_positive")} type="button">Mark false positive</button>
          <button className="ghostAction wide" onClick={() => onUpdateStatus(finding, "fixed")} type="button">Mark fixed</button>
          <button className="dangerAction wide" onClick={() => onUpdateStatus(finding, "open")} type="button">Reopen</button>
          {finding.pull_request ? (
            <button
              className="ghostAction wide"
              disabled={finding.pull_request.is_local_record}
              onClick={() => {
                const url = finding.pull_request?.github_url ?? finding.pull_request?.url;
                if (url && !finding.pull_request?.is_local_record) window.open(url, "_blank", "noopener,noreferrer");
              }}
              title={finding.pull_request.is_local_record ? "This linked item is a local RepoPilot PR record, not a real GitHub PR." : "Open the real GitHub pull request."}
              type="button"
            >
              <Github size={18} /> {finding.pull_request.is_local_record ? "Local PR record" : "Open in GitHub"}
            </button>
          ) : null}
          <h2>Policy triggered</h2>
          <Field label="High-risk file pattern" value={finding.file_path ?? "Unavailable"} mono />
          <Field label="Rule" value={finding.tool} mono />
        </aside>
      </div>
    </div>
  );
}

function EvaluationsScreen({
  evalReports,
  onRunEvaluation,
  repositories,
  runs
}: {
  evalReports: EvalReport[];
  onRunEvaluation: () => void;
  repositories: RepositoryResponse[];
  runs: RunSummary[];
}) {
  const latest = evalReports[0];
  const metrics = latest?.metrics ?? {};
  const evidence = evaluationEvidenceModel(latest, repositories.length, runs);
  const bars = [
    ["Task pass rate", metricPercent(metrics.task_pass_rate)],
    ["Patch validation success", metricPercent(metrics.patch_success_rate)],
    ["First-run CI pass rate", metricPercent(metrics.first_run_ci_pass_rate)],
    ["Fixture schema pass", metricPercent(metrics.fixture_schema_pass_rate)],
    ["Security block rate", metricPercent(metrics.security_block_rate)]
  ] as const;
  const taskOutcomes = Array.isArray(metrics.task_outcomes) ? metrics.task_outcomes as Array<Record<string, unknown>> : [];
  return (
    <div className="screen">
      <div className="titleRow">
        <ScreenHeader title="Evaluations" subtitle="Benchmark results for RepoPilot agent workflows." />
        <button className="cyanAction" onClick={onRunEvaluation} type="button"><Play size={18} /> Run benchmark</button>
      </div>
      <div className="reportMetaBar">
        <ReadOnlyMeta label="Benchmark version" value={evidence.historical.benchmarkVersion ?? "No report"} />
        <ReadOnlyMeta label="Report generated" value={evidence.historical.generatedAt ? formatDateTime(evidence.historical.generatedAt) : "No report"} />
        <ReadOnlyMeta label="Benchmark tasks" value={evidence.historical.benchmarkTaskCount === null ? "Unknown" : String(evidence.historical.benchmarkTaskCount)} />
        <ReadOnlyMeta label="Fixture repositories" value={evidence.historical.fixtureRepositoryCount === null ? "Unknown" : String(evidence.historical.fixtureRepositoryCount)} />
      </div>
      {latest ? (
        <section aria-label="Historical benchmark results" className="statGrid five">
          {bars.map(([label, value]) => <StatCard key={label} label={label} value={value.label} />)}
        </section>
      ) : <EmptyState text="No benchmark report is available. Run a benchmark to create historical evaluation evidence." />}
      <div className="dashboardGrid">
        <section className="panel chartPanel">
          <PanelHeader title="Success rate by issue type" />
          <BarChart metrics={metrics} />
        </section>
        <section className="panel">
          <PanelHeader title="Failure reasons" />
          <FailureReasons metrics={metrics} />
        </section>
      </div>
      <section aria-label="Current live operations snapshot" className="panel">
        <PanelHeader title="Current live operations snapshot" />
        <p className="muted">Current connected repositories and completed runs are operational data. They are not part of the historical benchmark report above.</p>
        <div className="statGrid four">
          <StatCard label="Connected repositories" value={String(evidence.live.connectedRepositoryCount)} />
          <StatCard label="Completed runs" value={String(evidence.live.completedCount)} />
          <StatCard label="Avg completed runtime" value={evidence.live.averageRuntimeLabel} />
          <StatCard label="Avg completed-run cost (USD)" value={evidence.live.averageCost === null ? "Unavailable" : formatUsd(evidence.live.averageCost)} />
        </div>
        {evidence.live.excludedCount > 0 ? <p className="muted">Excluded {evidence.live.excludedCount} unfinished or invalid run{evidence.live.excludedCount === 1 ? "" : "s"} from live averages.</p> : null}
      </section>
      <section className="panel tablePanel">
        <PanelHeader title="Benchmark Tasks" />
        {taskOutcomes.length ? (
          <table className="findingsTable">
            <thead>
              <tr>
                <th scope="col">Task</th>
                <th scope="col">Category</th>
                <th scope="col">Status</th>
                <th scope="col">Score</th>
                <th scope="col">Failure reason</th>
              </tr>
            </thead>
            <tbody>
              {taskOutcomes.map((outcome) => (
                <tr key={String(outcome.task_id)}>
                  <td>{String(outcome.task_id)}</td>
                  <td>{labelize(String(outcome.category ?? ""))}</td>
                  <td><Badge tone={statusTone(String(outcome.status ?? ""))}>{labelize(String(outcome.status ?? ""))}</Badge></td>
                  <td>{numberMetric(outcome.score).label}</td>
                  <td>{Array.isArray(outcome.failure_reasons) && outcome.failure_reasons.length ? outcome.failure_reasons.join("; ") : "None"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <TraceJson items={evalReports.map((report) => ({ benchmark_version: report.benchmark_version, created_at: report.created_at, report_uri: report.report_uri, metrics: report.metrics }))} />
        )}
      </section>
    </div>
  );
}

function AuditLogsScreen({
  page,
  onLoadMore,
  riskFilter,
  selectedKey,
  setRiskFilter,
  setSelectedKey,
  setSourceFilter,
  setStatusFilter,
  sourceFilter,
  statusFilter
}: {
  page: AuditLogPage | null;
  onLoadMore: () => void;
  riskFilter: AuditRiskFilter;
  selectedKey: string;
  setRiskFilter: (filter: AuditRiskFilter) => void;
  setSelectedKey: (key: string) => void;
  setSourceFilter: (filter: string) => void;
  setStatusFilter: (filter: AuditStatusFilter) => void;
  sourceFilter: string;
  statusFilter: AuditStatusFilter;
}) {
  const activities = page?.items ?? [];
  const sources = Array.from(new Set(activities.map((item) => item.actor_type))).sort();
  const filtered = activities.filter((item) => {
    if (sourceFilter !== "all" && item.actor_type !== sourceFilter) return false;
    if (statusFilter !== "all" && statusBucket(item.result) !== statusFilter) return false;
    if (riskFilter === "unknown" && item.risk_score !== null) return false;
    if (riskFilter !== "all" && riskFilter !== "unknown" && (item.risk_score === null || riskBucket(item.risk_score) !== riskFilter)) return false;
    return true;
  });
  const selected = filtered.find((item) => item.id === selectedKey) ?? filtered[0] ?? null;
  const completeness = page ? `Showing ${page.items.length} of ${page.total} authoritative audit records.` : "Loading authoritative audit records.";
  return (
    <div className="screen">
      <ScreenHeader title="Audit Logs" subtitle={completeness} />
      <div className="toolbar fiveFilters">
        <select aria-label="Filter audit records by actor type" onChange={(event) => setSourceFilter(event.target.value)} value={sourceFilter}>
          <option value="all">All actor types</option>
          {sources.map((source) => <option key={source} value={source}>{labelize(source)}</option>)}
        </select>
        <select aria-label="Filter audit records by result" onChange={(event) => setStatusFilter(event.target.value as AuditStatusFilter)} value={statusFilter}>
          <option value="all">All results</option>
          <option value="recorded">Recorded (no outcome metadata)</option>
          <option value="success">Successful</option>
          <option value="warning">Pending/review</option>
          <option value="failed">Failed/blocked</option>
        </select>
        <select aria-label="Filter audit records by risk" onChange={(event) => setRiskFilter(event.target.value as AuditRiskFilter)} value={riskFilter}>
          <option value="all">All risk levels</option>
          <option value="unknown">Risk not recorded</option>
          <option value="low">Low risk</option>
          <option value="medium">Medium risk</option>
          <option value="high">High risk</option>
        </select>
      </div>
      <div className="sideGrid">
        <section className="panel tablePanel">
          <table className="auditTable">
            <thead>
              <tr>
                <th scope="col">Time</th>
                <th scope="col">Actor</th>
                <th scope="col">Action</th>
                <th scope="col">Entity</th>
                <th scope="col">Result</th>
                <th scope="col">Risk</th>
                <th scope="col">Trace</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((item) => {
                const actor = item.actor_id ? `${labelize(item.actor_type)} · ${item.actor_id}` : labelize(item.actor_type);
                return (
                  <tr className={item.id === selectedKey ? "selected" : ""} key={item.id} onClick={() => setSelectedKey(item.id)} tabIndex={0} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setSelectedKey(item.id); } }} role="row">
                    <td>{formatDateTime(item.created_at)}</td>
                    <td>{actor}</td>
                    <td>{item.action}</td>
                    <td>{item.entity_id ? shortId(item.entity_id) : item.entity_type}</td>
                    <td><Badge tone={statusTone(item.result)}>{labelize(item.result)}</Badge></td>
                    <td>{item.risk_score === null ? <Badge tone="neutral">Unknown</Badge> : <Badge tone={riskTone(item.risk_score)}>{riskLabel(item.risk_score)}</Badge>}</td>
                    <td><code>{item.entity_type === "agent_run" && item.entity_id ? shortId(item.entity_id) : "none"}</code></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {!page ? <EmptyState text="Audit records are loading." /> : filtered.length === 0 ? <EmptyState text="No audit activity matches the current filters." /> : null}
          {page?.has_more ? <button className="panelLink" onClick={onLoadMore} type="button">Load remaining audit records <ChevronRight size={16} /></button> : null}
        </section>
        <aside className="panel contextPanel">
          <h2>Selected log detail</h2>
          {selected ? (
            <>
              <Field label="Actor type" value={labelize(selected.actor_type)} />
              <Field label="Actor ID" value={selected.actor_id ?? "Not recorded"} mono />
              <Field label="Input" value={selected.entity_type} mono />
              <Field label="Output" value={selected.action} />
              <Field label="Policy" value={stringValue(selected.metadata.policy) || "Unavailable"} />
              <Field label="Result" value={labelize(selected.result)} tone={statusTone(selected.result)} />
              <Field label="Risk" value={selected.risk_score === null ? "Not recorded" : riskLabel(selected.risk_score)} tone={selected.risk_score === null ? "neutral" : riskTone(selected.risk_score)} />
              <Field label="Recorded" value={formatDateTime(selected.created_at)} />
              <Field label="Trace" value={selected.entity_id ? shortId(selected.entity_id) : "Unavailable"} mono />
            </>
          ) : (
            <EmptyState text="Select a log row." />
          )}
        </aside>
      </div>
    </div>
  );
}

function SettingsScreen({
  data,
  githubAppVerification,
  modelCatalogLoadStatus,
  motionPreference,
  onGithub,
  onSaveGithubApp,
  onSaveGithubOAuth,
  onVerifyGithubApp,
  onSaveModelProvider,
  onVerifyModelProvider,
  policy,
  readiness,
  setMotionPreference,
  setShowAppSecretForm,
  setShowSecretForm,
  showAppSecretForm,
  showSecretForm,
  tab,
  setTab,
  verification,
  onReset
}: {
  data: ConsoleState;
  githubAppVerification: GitHubAppVerificationResponse | null;
  modelCatalogLoadStatus: ModelCatalogLoadStatus;
  onGithub: () => void;
  onSaveGithubApp: (payload: GitHubAppConfigPayload) => Promise<void>;
  onSaveGithubOAuth: (payload: GitHubOAuthConfigPayload) => Promise<void>;
  onVerifyGithubApp: () => Promise<void>;
  onSaveModelProvider: (payload: ModelProviderConfigPayload) => Promise<void>;
  onVerifyModelProvider: () => Promise<void>;
  policy: PolicyResponse | null;
  readiness: ReadinessResponse | null;
  setShowAppSecretForm: (show: boolean) => void;
  setShowSecretForm: (show: boolean) => void;
  showAppSecretForm: boolean;
  showSecretForm: boolean;
  tab: SettingsTab;
  setTab: (tab: SettingsTab) => void;
  verification: ModelProviderVerificationResponse | null;
  onReset: () => void;
  motionPreference: MotionPreference;
  setMotionPreference: (pref: MotionPreference) => void;
}) {
  const githubConnected = isGithubAccountConnected(data);
  const githubOAuth = githubOAuthIntegration(readiness);
  const githubApp = readinessIntegration(readiness, "github app installation");
  const githubWriteMode = readinessIntegration(readiness, "github write mode");
  const [modelProviderDraft, setModelProviderDraft] = useState<ModelProviderDraft | null>(null);
  const draftProvider = data.modelCatalog?.providers.find((provider) => provider.id === modelProviderDraft?.providerId) ?? null;
  const draftModel = draftProvider?.models.find((model) => model.id === modelProviderDraft?.modelId) ?? null;
  const modelDraftChanged = Boolean(
    modelProviderDraft?.providerId
      && (
        modelProviderDraft.providerId !== data.modelConfig?.provider
        || modelProviderDraft.modelId !== data.modelConfig?.model
        || modelProviderDraft.baseUrl !== (data.modelConfig?.base_url ?? draftProvider?.default_base_url ?? "")
        || modelProviderDraft.reasoningLevel !== (data.modelConfig?.reasoning_level ?? draftModel?.reasoning_levels[0] ?? "")
        || modelProviderDraft.apiKey
      )
  );
  const modelVerificationPassed = verification?.ok ?? Boolean(data.modelConfig?.verified);
  const modelVerificationFailed = verification ? !verification.ok : false;
  const [activeTab, setActiveTab] = useState<SettingsTab>(tab);
  useEffect(() => {
    setActiveTab(tab);
  }, [tab]);

  function chooseTab(next: SettingsTab) {
    setActiveTab(next);
    setTab(next);
  }

  return (
    <div className="screen">
      <ScreenHeader title="Settings" subtitle="Manage GitHub and model connections, and inspect effective policy, tool, budget, and display controls." />
      <div aria-label="Settings sections" className="tabs" role="tablist">
        {SETTINGS_TABS.map((item) => (
          <button aria-controls={`settings-panel-${item.toLowerCase().replace(/\s+/g, "-")}`} aria-selected={activeTab === item} className={activeTab === item ? "tab active" : "tab"} id={`settings-tab-${item.toLowerCase().replace(/\s+/g, "-")}`} key={item} onClick={() => chooseTab(item)} role="tab" type="button">
            {item}
          </button>
        ))}
      </div>
      <div aria-labelledby={`settings-tab-${activeTab.toLowerCase().replace(/\s+/g, "-")}`} className="settingsGrid" id={`settings-panel-${activeTab.toLowerCase().replace(/\s+/g, "-")}`} role="tabpanel">
        {activeTab === "GitHub" && (
          <>
            <section className="detailStack">
              <GitHubSyncPanel data={data} onConfigure={() => setShowSecretForm(true)} onConnect={onGithub} />
              {(showSecretForm || !githubOAuthConfigured(data.githubOAuthConfig)) ? (
                <GitHubOAuthSecretForm configStatus={data.githubOAuthConfig} onCancel={() => setShowSecretForm(false)} onSave={onSaveGithubOAuth} />
              ) : null}
              {(showAppSecretForm || !githubAppConfigured(data.githubAppConfig)) ? (
                <GitHubAppSecretForm configStatus={data.githubAppConfig} onCancel={() => setShowAppSecretForm(false)} onSave={onSaveGithubApp} />
              ) : null}
              <section className="panel settingsPanel">
                <h2>GitHub App readiness</h2>
                <div className="githubMetricGrid">
                  <MetaCard icon={KeyRound} label="App credentials" value={labelize(githubApp?.state ?? "missing")} />
                  <MetaCard icon={GitBranch} label="GitHub mode" value={labelize(readiness?.github_mode ?? "unavailable")} />
                  <MetaCard icon={Shield} label="Write mode" value={labelize(githubWriteMode?.state ?? "disabled")} />
                </div>
                <div className="securityNotes">
                  <InfoLine icon={KeyRound} label="Credential state" value={githubApp?.detail ?? "GitHub App credentials are not configured."} />
                  <InfoLine icon={GitBranch} label="Write gate" value={githubWriteMode?.detail ?? "Local record mode is active."} />
                  <InfoLine icon={Shield} label="Next action" value={githubWriteMode?.next_step ?? githubApp?.next_step ?? "Configure and verify a GitHub App installation."} />
                </div>
                {githubAppVerification ? <div className="connectNotice">{githubAppVerification.detail}</div> : null}
                <div className="panelActions">
                  <button className="ghostAction" onClick={() => setShowAppSecretForm(true)} type="button">
                    <Lock size={18} />
                    Configure GitHub App
                  </button>
                  <button className="cyanAction" onClick={() => void onVerifyGithubApp()} type="button">
                    <CheckCircle2 size={18} />
                    Verify GitHub App
                  </button>
                </div>
              </section>
              <section className="panel settingsPanel">
                <h2>Repository sync</h2>
                <div className="githubMetricGrid">
                  <MetaCard icon={Database} label="Repositories imported" value={String(data.repositories.length)} />
                  <MetaCard icon={Box} label="GitHub accounts" value={String(data.installations.length)} />
                  <MetaCard icon={AlertCircle} label="Tracked issues" value={String(data.issues.length)} />
                </div>
                <div className="accountList">
                  {data.installations.map((installation) => (
                    <div className="accountRow" key={installation.id}>
                      <Github size={20} />
                      <span>
                        <strong>{installation.account_name}</strong>
                        <small>{installation.repository_count} repositories</small>
                      </span>
                      <Badge tone={installation.github_installation_id.startsWith("oauth:") ? "success" : "info"}>
                        {installation.github_installation_id.startsWith("oauth:") ? "OAuth" : "App"}
                      </Badge>
                    </div>
                  ))}
                  {data.installations.length === 0 ? <EmptyState text="No GitHub accounts are connected yet." /> : null}
                </div>
              </section>
            </section>
            <aside className="panel contextPanel">
              <h2>GitHub status</h2>
              <div className={githubConnected ? "statusHero" : "statusHero warning"}>
                {githubConnected ? <CheckCircle2 size={32} /> : <AlertTriangle size={32} />}
                <strong>{githubConnected ? "Connected" : githubOAuth?.state === "configured" ? "OAuth ready" : "Not connected"}</strong>
              </div>
              <Field label="Session" value={data.session?.github_user_id ? "GitHub OAuth" : "Local development"} tone={data.session?.github_user_id ? "success" : "warning"} />
              <Field label="OAuth" value={labelize(githubOAuth?.state ?? "missing")} tone={statusTone(githubOAuth?.state ?? "missing")} />
              <Field label="GitHub App" value={labelize(githubApp?.state ?? "missing")} tone={statusTone(githubApp?.state ?? "missing")} />
              <Field label="Mode" value={labelize(readiness?.github_mode ?? "unavailable")} tone={readiness?.github_mode?.includes("unverified") ? "warning" : readiness?.github_mode?.includes("verified") ? "success" : "info"} />
              <Field label="Environment" value={readiness?.environment ?? "Unavailable"} />
              <button className="primaryAction wide" onClick={onGithub} type="button">
                <Github size={18} />
                {githubConnected ? "Sync repositories" : "Connect GitHub"}
              </button>
              <button className="ghostAction wide" onClick={onReset} type="button">
                <RefreshCcw size={18} />
                Refresh status
              </button>
            </aside>
          </>
        )}

        {activeTab === "Policies" && (
          <>
            <section className="detailStack">
              <section className="panel settingsPanel">
                <h2>Human Approval Policies</h2>
                <p className="mutedText">Read-only snapshot of the effective runtime policy. Change the deployment policy configuration to modify these controls.</p>
                <PolicyToggle label="Require approval before code changes" enabled />
                <PolicyToggle label="Require approval for auth changes" enabled={policy?.high_risk_patterns.some((item) => item.includes("auth")) ?? false} />
                <PolicyToggle label="Require approval for CI/CD workflow changes" enabled={policy?.high_risk_patterns.some((item) => item.includes(".github/workflows")) ?? false} />
                <PolicyToggle label="Require approval for dependency changes" enabled={policy?.high_risk_patterns.some((item) => item.includes("migrations")) ?? false} />
                <PolicyToggle label={`Require approval if more than ${policy?.max_files_changed_without_approval ?? 0} files changed`} enabled />
              </section>
              <section className="panel settingsPanel">
                <h2>Risk Thresholds</h2>
                <Threshold label="Low risk: auto-plan allowed" tone="success" value="Low" />
                <Threshold label="Medium risk: approval required" tone="warning" value="Medium" />
                <Threshold label="High risk: security approval required" tone="danger" value="High" />
                <Threshold label="Critical risk: blocked by default" tone="danger" value="Critical" />
              </section>
            </section>
            <aside className="panel contextPanel">
              <h2>Policy status</h2>
              <div className="statusHero">
                <CheckCircle2 size={32} />
                <strong>{readiness?.production_ready ? "Readiness checks passed" : "Local policy active"}</strong>
              </div>
              <p className="mutedText">Environment: {readiness?.environment ?? "Unavailable"}</p>
              <button className="primaryAction wide" onClick={onReset} type="button">
                <RefreshCcw size={18} />
                Refresh effective policy
              </button>
            </aside>
          </>
        )}

        {activeTab === "Tool Permissions" && (
          <>
            <section className="detailStack">
              <section className="panel settingsPanel">
                <h2>Tool Permissions</h2>
                <p className="mutedText">Read-only snapshot of the effective command allowlist and blocklist enforced by the backend.</p>
                <div className="permissionGrid">
                  <CommandList title="Allowed commands" items={policy?.allowed_commands ?? []} tone="success" />
                  <CommandList title="Blocked commands" items={policy?.blocked_command_fragments ?? []} tone="danger" />
                </div>
              </section>
            </section>
            <aside className="panel contextPanel">
              <h2>Permissions status</h2>
              <div className="statusHero">
                <CheckCircle2 size={32} />
                <strong>{policy ? "Permissions active" : "Config missing"}</strong>
              </div>
              <p className="mutedText">Environment: {readiness?.environment ?? "Unavailable"}</p>
              <button className="primaryAction wide" onClick={onReset} type="button">
                <RefreshCcw size={18} />
                Refresh effective permissions
              </button>
            </aside>
          </>
        )}

        {activeTab === "Cost Limits" && (
          <>
            <section className="detailStack">
              <section className="panel settingsPanel">
                <h2>Cost Limits</h2>
                <p className="mutedText">Read-only snapshot of effective backend safety limits. Provider-reported costs are denominated in USD.</p>
                <KeyValue label="Max provider cost per run (USD)" value={policy ? formatUsd(policy.max_cost_per_run) : "Unavailable"} />
                <KeyValue label="Max commands without approval" value={String(policy?.max_commands_without_approval ?? "Unavailable")} />
                <KeyValue label="Max files changed without approval" value={String(policy?.max_files_changed_without_approval ?? "Unavailable")} />
              </section>
            </section>
            <aside className="panel contextPanel">
              <h2>Budget status</h2>
              <div className={policy ? "statusHero" : "statusHero warning"}>
                {policy ? <CheckCircle2 size={32} /> : <AlertTriangle size={32} />}
                <strong>{policy ? "Policy limits loaded" : "Policy unavailable"}</strong>
              </div>
              <p className="mutedText">Environment: {readiness?.environment ?? "Unavailable"}</p>
              <button className="primaryAction wide" onClick={onReset} type="button">
                <RefreshCcw size={18} />
                Refresh effective limits
              </button>
            </aside>
          </>
        )}

        {activeTab === "Models" && (
          <>
            <section className="detailStack">
              <ModelProviderForm
                catalog={data.modelCatalog}
                catalogLoadStatus={modelCatalogLoadStatus}
                config={data.modelConfig}
                draft={modelProviderDraft}
                onSave={onSaveModelProvider}
                setDraft={setModelProviderDraft}
              />
            </section>
            <aside className="panel contextPanel">
              <h2>Saved model status</h2>
              {modelDraftChanged ? (
                <p className="mutedText">
                  Unsaved draft: {draftProvider?.name ?? modelProviderDraft?.providerId} / {draftModel?.name ?? modelProviderDraft?.modelId}
                </p>
              ) : null}
              <div className={data.modelConfig?.status === "configured" ? "statusHero" : "statusHero warning"}>
                {data.modelConfig?.status === "configured" ? <CheckCircle2 size={32} /> : <AlertTriangle size={32} />}
                <strong>{data.modelConfig?.status === "configured" ? "Configured" : "Not connected"}</strong>
              </div>
              <Field label="Provider" value={data.modelConfig?.provider_name ?? "N/A"} tone={data.modelConfig?.model_configured ? "success" : "warning"} />
              <Field label="Model" value={data.modelConfig?.model_configured ? data.modelConfig.model : "N/A"} />
              <Field label="Reasoning level" value={data.modelConfig?.reasoning_supported ? data.modelConfig.reasoning_level ?? "Default" : "N/A"} tone={data.modelConfig?.reasoning_supported ? "info" : "warning"} />
              <Field label="API key" value={data.modelConfig?.api_key_configured ? "Configured" : "Missing"} tone={data.modelConfig?.api_key_configured ? "success" : "danger"} />
              <Field label="Base URL" value={data.modelConfig?.base_url ?? "N/A"} />
              <Field
                label="Live verification"
                value={modelVerificationPassed ? "Passed" : modelVerificationFailed ? "Failed" : "Not run"}
                tone={modelVerificationPassed ? "success" : modelVerificationFailed ? "danger" : "warning"}
              />
              {verification ? <p className="mutedText">{verification.detail}</p> : null}
              {!verification && data.modelConfig?.verified_at ? (
                <p className="mutedText">Last passed {formatDateTime(data.modelConfig.verified_at)}. Reverify after changing provider credentials or model settings.</p>
              ) : null}
              <p className="mutedText">Environment: {readiness?.environment ?? "Unavailable"}</p>
              <button className="cyanAction wide" disabled={!data.modelConfig?.api_key_configured} onClick={() => void onVerifyModelProvider()} title={data.modelConfig?.api_key_configured ? "Runs a live provider verification request using the saved key. No repository source is sent during verification." : "Save a provider API key before verification."} type="button">
                <Sparkles size={18} />
                Verify with live call
              </button>
              {data.modelConfig?.docs_url ? (
                <button className="ghostAction wide" onClick={() => window.open(data.modelConfig?.docs_url ?? "", "_blank", "noopener,noreferrer")} type="button">
                  <ExternalLink size={18} />
                  Provider docs
                </button>
              ) : null}
              <button className="primaryAction wide" onClick={onReset} type="button">
                <RefreshCcw size={18} />
                Refresh config
              </button>
            </aside>
          </>
        )}

        {activeTab === "Display" && (
          <>
            <section className="detailStack">
              <section className="panel settingsPanel">
                <h2>Motion preference</h2>
                <p className="mutedText" style={{ marginBottom: "16px" }}>Control animation speed across the console. Reduced motion uses simpler transitions and disables staggered reveals.</p>
                <div style={{ display: "grid", gap: "12px" }}>
                  {([
                    ["no", "No motion", "Instant transitions, no animations, no staggered reveals."],
                    ["reduced", "Reduced", "Quick fades only. Staggered entrance animations are disabled."],
                    ["standard", "Standard", "Full motion system with staggered stat cards and press feedback."],
                    ["enhanced", "Enhanced", "Longer, more expressive transitions throughout the console."]
                  ] as const).map(([value, label, description]) => (
                    <label
                      key={value}
                      style={{
                        display: "grid",
                        gridTemplateColumns: "auto minmax(0, 1fr)",
                        alignItems: "center",
                        gap: "14px",
                        minHeight: "52px",
                        padding: "10px 16px",
                        border: motionPreference === value ? "1px solid rgba(79, 140, 255, 0.62)" : "1px solid var(--border)",
                        borderRadius: "var(--radius-lg)",
                        background: motionPreference === value ? "rgba(79, 140, 255, 0.08)" : "rgba(10, 15, 21, 0.5)",
                        cursor: "pointer"
                      }}
                    >
                      <input
                        type="radio"
                        name="motion"
                        value={value}
                        checked={motionPreference === value}
                        onChange={() => setMotionPreference(value)}
                        style={{ accentColor: "var(--blue)", width: "18px", height: "18px", cursor: "pointer" }}
                      />
                      <span>
                        <strong style={{ display: "block", fontSize: "14px" }}>{label}</strong>
                        <small style={{ display: "block", marginTop: "4px", color: "var(--text-2)", fontSize: "12px" }}>{description}</small>
                      </span>
                    </label>
                  ))}
                </div>
              </section>
            </section>
            <aside className="panel contextPanel">
              <h2>Motion status</h2>
              <div className="statusHero">
                <CheckCircle2 size={32} />
                <strong>{motionPreference === "no" ? "No motion" : motionPreference === "reduced" ? "Reduced" : motionPreference === "enhanced" ? "Enhanced" : "Standard"} active</strong>
              </div>
              <p className="mutedText">System preference (prefers-reduced-motion) is always respected and overrides this setting.</p>
              <button className="ghostAction wide" onClick={() => { setMotionPreference("standard"); }} type="button">
                <RefreshCcw size={18} />
                Reset to standard
              </button>
            </aside>
          </>
        )}
      </div>
    </div>
  );
}

function GitHubSyncPanel({
  data,
  onConfigure,
  onConnect,
  compact
}: {
  data: ConsoleState;
  onConfigure?: () => void;
  onConnect: () => void;
  compact?: boolean;
}) {
  const connected = isGithubAccountConnected(data);
  const oauth = githubOAuthIntegration(data.readiness);
  const configReady = githubOAuthConfigured(data.githubOAuthConfig);
  const account = data.session?.github_user_id ? data.session.username : null;
  const credentialsReady = oauth?.state === "configured" || configReady;
  return (
    <section className={compact ? "panel githubSyncPanel compact" : "panel githubSyncPanel"}>
      <div className="githubSyncIcon">
        <Github size={28} />
      </div>
      <div className="githubSyncBody">
        <div className="githubSyncTitle">
          <h2>GitHub connection</h2>
          <Badge tone={connected ? "success" : credentialsReady ? "warning" : "danger"}>
            {connected ? "Connected" : credentialsReady ? "Ready to connect" : "Setup required"}
          </Badge>
        </div>
        <div className="githubSyncMeta">
          <span>{account ?? (data.installations.length ? "Repository records imported; no active OAuth session" : "No GitHub account connected")}</span>
          <span>{data.repositories.length} repositories imported</span>
          <span>{labelize(oauth?.state ?? "missing")} credentials</span>
        </div>
      </div>
      <div className="githubSyncActions">
        <button className="primaryAction" onClick={onConnect} type="button">
          {connected ? <RefreshCcw size={20} /> : <Github size={20} />}
          {connected ? "Sync repositories" : "Connect GitHub"}
        </button>
        {onConfigure ? (
          <button className="ghostAction" onClick={onConfigure} type="button">
            <Lock size={18} />
            Configure secrets
          </button>
        ) : null}
      </div>
    </section>
  );
}

function ModelProviderForm({
  catalog,
  catalogLoadStatus,
  config,
  draft,
  onSave,
  setDraft
}: {
  catalog: ModelCatalogResponse | null;
  catalogLoadStatus: ModelCatalogLoadStatus;
  config: ModelProviderConfigStatus | null;
  draft: ModelProviderDraft | null;
  onSave: (payload: ModelProviderConfigPayload) => Promise<void>;
  setDraft: (draft: ModelProviderDraft | null) => void;
}) {
  const providers = catalog?.providers ?? [];
  const configuredProvider = providers.find((provider) => provider.id === config?.provider);
  const defaultProvider = configuredProvider ?? providers[0] ?? null;
  const savedConfigSignature = modelProviderConfigSignature(config, catalog);
  const activeDraft = draft?.savedConfigSignature === savedConfigSignature ? draft : null;
  const hydratedConfigSignature = useRef<string | null>(null);
  const [providerId, setProviderId] = useState(activeDraft?.providerId ?? defaultProvider?.id ?? "");
  const provider = providers.find((candidate) => candidate.id === providerId) ?? defaultProvider;
  const configuredModel = provider?.models.find((model) => model.id === config?.model);
  const [modelId, setModelId] = useState(activeDraft?.modelId ?? configuredModel?.id ?? provider?.models[0]?.id ?? "");
  const selectedModel = provider?.models.find((model) => model.id === modelId) ?? null;
  const reasoningLevels = selectedModel?.reasoning_levels ?? [];
  const [reasoningLevel, setReasoningLevel] = useState(activeDraft?.reasoningLevel ?? config?.reasoning_level ?? reasoningLevels[0] ?? "");
  const [apiKey, setApiKey] = useState(activeDraft?.apiKey ?? "");
  const [baseUrl, setBaseUrl] = useState(activeDraft?.baseUrl ?? config?.base_url ?? provider?.default_base_url ?? "");
  const [modelQuery, setModelQuery] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const selectedProviderHasConfiguredKey = providerHasConfiguredApiKey(
    config?.configured_api_key_providers,
    provider?.id
  );
  const selectedProviderKeyReady = selectedProviderHasConfiguredKey || Boolean(apiKey.trim());
  const normalizedModelQuery = modelQuery.trim().toLowerCase();
  const matchingModels = (provider?.models ?? []).filter((model) => (
    !normalizedModelQuery
    || `${model.name} ${model.id} ${model.capabilities.join(" ")}`.toLowerCase().includes(normalizedModelQuery)
  ));
  const visibleModels = matchingModels.slice(0, 80);
  if (!normalizedModelQuery && selectedModel && !visibleModels.some((model) => model.id === selectedModel.id)) {
    visibleModels.unshift(selectedModel);
    if (visibleModels.length > 80) visibleModels.pop();
  }
  const pricingLabel = (model: ModelCatalogModel): string | null => {
    if (!model.pricing) {
      return null;
    }
    const prompt = model.pricing.prompt;
    const completion = model.pricing.completion;
    if (!prompt && !completion) {
      return null;
    }
    const promptLabel = formatUsdPerToken(prompt);
    const completionLabel = formatUsdPerToken(completion);
    const currency = model.pricing_currency ?? "USD";
    return `Prompt ${currency} ${promptLabel ?? "unknown"} | Completion ${currency} ${completionLabel ?? "unknown"}`;
  };

  useEffect(() => {
    if (hydratedConfigSignature.current === savedConfigSignature) {
      return;
    }
    hydratedConfigSignature.current = savedConfigSignature;
    if (activeDraft) {
      setProviderId(activeDraft.providerId);
      setModelId(activeDraft.modelId);
      setReasoningLevel(activeDraft.reasoningLevel);
      setBaseUrl(activeDraft.baseUrl);
      setApiKey(activeDraft.apiKey);
      return;
    }
    const nextProvider = providers.find((candidate) => candidate.id === config?.provider) ?? providers[0] ?? null;
    const nextModel = nextProvider?.models.find((model) => model.id === config?.model) ?? nextProvider?.models[0] ?? null;
    const nextDraft = {
      providerId: nextProvider?.id ?? "",
      modelId: nextModel?.id ?? "",
      reasoningLevel: config?.reasoning_level ?? nextModel?.reasoning_levels[0] ?? "",
      apiKey: "",
      baseUrl: config?.base_url ?? nextProvider?.default_base_url ?? "",
      savedConfigSignature
    };
    setProviderId(nextDraft.providerId);
    setModelId(nextDraft.modelId);
    setReasoningLevel(nextDraft.reasoningLevel);
    setBaseUrl(nextDraft.baseUrl);
    setApiKey("");
    setDraft(nextDraft);
  }, [activeDraft, config, providers, savedConfigSignature, setDraft]);

  function updateDraft(nextDraft: Omit<ModelProviderDraft, "savedConfigSignature">) {
    setDraft({ ...nextDraft, savedConfigSignature });
  }

  function chooseProvider(nextProviderId: string) {
    const nextProvider = providers.find((candidate) => candidate.id === nextProviderId) ?? null;
    const nextModel = nextProvider?.models[0] ?? null;
    const nextDraft = {
      providerId: nextProviderId,
      modelId: nextModel?.id ?? "",
      reasoningLevel: nextModel?.reasoning_levels[0] ?? "",
      apiKey: "",
      baseUrl: nextProvider?.default_base_url ?? ""
    };
    setProviderId(nextDraft.providerId);
    setModelId(nextDraft.modelId);
    setReasoningLevel(nextDraft.reasoningLevel);
    setBaseUrl(nextDraft.baseUrl);
    setApiKey("");
    setModelQuery("");
    updateDraft(nextDraft);
    setError(null);
  }

  function chooseModel(nextModelId: string) {
    const nextModel = provider?.models.find((model) => model.id === nextModelId) ?? null;
    const nextReasoningLevel = nextModel?.reasoning_levels[0] ?? "";
    setModelId(nextModelId);
    setReasoningLevel(nextReasoningLevel);
    updateDraft({ providerId, modelId: nextModelId, reasoningLevel: nextReasoningLevel, apiKey, baseUrl });
  }

  function chooseReasoningLevel(nextReasoningLevel: string) {
    setReasoningLevel(nextReasoningLevel);
    updateDraft({ providerId, modelId, reasoningLevel: nextReasoningLevel, apiKey, baseUrl });
  }

  function updateApiKey(nextApiKey: string) {
    setApiKey(nextApiKey);
    updateDraft({ providerId, modelId, reasoningLevel, apiKey: nextApiKey, baseUrl });
  }

  function updateBaseUrl(nextBaseUrl: string) {
    setBaseUrl(nextBaseUrl);
    updateDraft({ providerId, modelId, reasoningLevel, apiKey, baseUrl: nextBaseUrl });
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!provider || !modelId) {
      setError("Select a provider and model before saving.");
      return;
    }
    setError(null);
    setIsSaving(true);
    try {
      await onSave({
        provider: provider.id,
        model: modelId,
        model_api_key: apiKey || undefined,
        model_base_url: baseUrl || provider.default_base_url,
        model_reasoning_level: reasoningLevels.length ? reasoningLevel : undefined
      });
      setApiKey("");
      updateDraft({ providerId, modelId, reasoningLevel, apiKey: "", baseUrl });
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Unable to save model provider");
    } finally {
      setIsSaving(false);
    }
  }

  if (providers.length === 0) {
    const loading = catalogLoadStatus === "idle" || catalogLoadStatus === "loading";
    return (
      <section className="panel settingsPanel">
        <h2>Inference providers</h2>
        <p className="mutedText" style={{ marginBottom: "16px" }}>
          {loading
            ? "Loading the provider catalog on demand. It is intentionally excluded from the initial console payload."
            : "The catalog is unavailable, so live provider setup is disabled. When configured, live model calls may send prompts, issue/PR context, selected repository snippets, and embedding inputs to the selected provider."}
        </p>
        <div className="securityNotes">
          <InfoLine icon={KeyRound} label="Write-only key" value="Saved API keys are never returned to the browser." />
          <InfoLine icon={Eye} label="External data transfer" value="Repository chunks stay local unless live embeddings are enabled with source-transfer consent." />
        </div>
        <EmptyState text={loading ? "Loading model provider catalog…" : "The model provider catalog is unavailable."} />
      </section>
    );
  }

  return (
    <form className="panel modelProviderPanel" onSubmit={(event) => void submit(event)}>
      <div className="secretFormHeader">
        <span className="githubSyncIcon"><Sparkles size={24} /></span>
        <span>
          <h2>Inference provider</h2>
          <p>Select the provider used for live model calls. API keys are write-only and saved in encrypted local storage.</p>
          <p>Live model calls may send issue text, prompts, selected repository context, and model outputs to the configured provider; provider-backed embeddings require explicit source-transfer opt-in.</p>
        </span>
        <Badge tone={selectedProviderKeyReady ? "success" : "warning"}>
          {selectedProviderHasConfiguredKey ? "API key configured" : apiKey.trim() ? "New API key entered" : "API key required"}
        </Badge>
      </div>

      <details className="settingsDisclosure">
        <summary>
          <span><strong>Change provider</strong><small>{provider?.name ?? "No provider selected"} · {providers.length} available</small></span>
          <ChevronDown size={17} aria-hidden="true" />
        </summary>
        <div className="modelProviderGrid">
          {providers.map((candidate) => (
            <button
              className={candidate.id === provider?.id ? "modelProviderCard active" : "modelProviderCard"}
              key={candidate.id}
              onClick={() => chooseProvider(candidate.id)}
              type="button"
            >
              <span>
                <strong>{candidate.name}</strong>
                <small>{candidate.models.length} models</small>
              </span>
              {candidate.id === provider?.id ? <CheckCircle2 size={18} /> : <Circle size={18} />}
            </button>
          ))}
        </div>
      </details>

      <div className="modelConfigGrid">
        <label className="secretInput">
          <span>Provider</span>
          <div>
            <select value={provider?.id ?? ""} onChange={(event) => chooseProvider(event.target.value)}>
              {providers.map((candidate) => <option key={candidate.id} value={candidate.id}>{candidate.name}</option>)}
            </select>
          </div>
        </label>
        <label className="secretInput">
          <span>Model</span>
          <div>
            <select value={modelId} onChange={(event) => chooseModel(event.target.value)}>
              {(provider?.models ?? []).map((model) => (
                <option key={model.id} value={model.id}>
                  {model.name} - {model.id}{model.is_free ? " (Free)" : ""}
                </option>
              ))}
            </select>
          </div>
        </label>
        {reasoningLevels.length ? (
          <label className="secretInput">
            <span>Reasoning level</span>
            <div>
              <select value={reasoningLevel} onChange={(event) => chooseReasoningLevel(event.target.value)}>
                {reasoningLevels.map((level) => <option key={level} value={level}>{labelize(level)}</option>)}
              </select>
            </div>
          </label>
        ) : null}
        <SecretInput
          label="Provider API Key"
          name="model-api-key"
          onChange={updateApiKey}
          placeholder={selectedProviderHasConfiguredKey ? "Already configured for this provider; enter a new key to rotate" : "Paste provider API key"}
          secret
          value={apiKey}
        />
        <SecretInput
          label="Base URL"
          name="model-base-url"
          onChange={updateBaseUrl}
          placeholder={provider?.default_base_url ?? "https://api.provider.example"}
          value={baseUrl}
        />
      </div>

      {provider ? (
        <div className="modelDetails">
          <div>
            <strong>{provider.name}</strong>
            <p>{provider.description}</p>
          </div>
          <a href={provider.docs_url} rel="noreferrer" target="_blank"><ExternalLink size={16} /> Official docs</a>
        </div>
      ) : null}

      {error ? <div className="connectNotice">{error}</div> : null}
      <div className="panelActions modelSaveActions">
        <button className="primaryAction" disabled={isSaving} type="submit">
          <Save size={18} />
          {isSaving ? "Saving..." : "Save model provider"}
        </button>
      </div>

      <details className="settingsDisclosure catalogDisclosure">
        <summary>
          <span><strong>Browse model catalog</strong><small>{provider?.models.length ?? 0} models · search by name, ID, or capability</small></span>
          <ChevronDown size={17} aria-hidden="true" />
        </summary>
        {(provider?.models.length ?? 0) > 20 ? (
          <div className="modelOptionsHeader">
            <label className="secretInput modelSearchInput">
              <span>Filter model catalog</span>
              <input
                onChange={(event) => setModelQuery(event.target.value)}
                placeholder="Search model name, ID, or capability"
                type="search"
                value={modelQuery}
              />
            </label>
            <span className="mutedText">
              Showing {visibleModels.length} of {matchingModels.length} matching models ({provider?.models.length ?? 0} total)
            </span>
          </div>
        ) : null}

        <div className="modelOptionsTable">
          {visibleModels.map((model) => (
            <button className={model.id === modelId ? "modelOptionRow active" : "modelOptionRow"} key={model.id} onClick={() => chooseModel(model.id)} type="button">
              <span>
                <strong>
                  {model.name}
                  {model.is_free ? <em className="modelFreeBadge">Free</em> : null}
                </strong>
                <small>{model.id}</small>
              </span>
              <span>{model.context_window}</span>
              <span>
                {model.reasoning_levels.length
                  ? `Reasoning: ${model.reasoning_levels.map(labelize).join(", ")}`
                  : pricingLabel(model) ?? model.capabilities.join(", ")}
              </span>
            </button>
          ))}
          {visibleModels.length === 0 ? <EmptyState text="No models match this filter." /> : null}
        </div>
      </details>

      <div className="securityNotes">
        <InfoLine icon={Database} label="Backend catalog" value="Provider and model IDs come from the backend catalog. This does not verify provider privacy terms or data handling." />
        <InfoLine icon={KeyRound} label="Write-only key" value="API keys are never returned to the browser after saving." />
        <InfoLine icon={Shield} label="Encrypted storage" value="Provider settings and API keys are saved in encrypted local storage through the runtime secret store." />
        <InfoLine icon={Eye} label="External data transfer" value="Live runs may send prompts, repository source snippets, issue/PR context, and embedding inputs to the selected provider." />
        <InfoLine icon={Database} label="Explicit source transfer" value="Repository chunks stay local unless live embeddings are enabled with source-transfer consent." />
      </div>

    </form>
  );
}

function GitHubOAuthSecretForm({
  configStatus,
  onCancel,
  onSave
}: {
  configStatus: GitHubOAuthConfigStatus | null;
  onCancel: () => void;
  onSave: (payload: GitHubOAuthConfigPayload) => Promise<void>;
}) {
  const [form, setForm] = useState<GitHubOAuthConfigForm>({
    github_client_id: "",
    github_client_secret: "",
    github_owner_login: "",
    session_secret_key: "",
    github_oauth_callback_url: "http://localhost:8000/auth/github/callback",
    web_app_url: "http://127.0.0.1:3001",
    github_api_base_url: "https://api.github.com",
    github_web_base_url: "https://github.com"
  });
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function updateField(field: keyof GitHubOAuthConfigForm, value: string) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsSaving(true);
    try {
      const payload = Object.fromEntries(
        Object.entries(form).filter(([, value]) => value.trim() !== "")
      ) as GitHubOAuthConfigPayload;
      await onSave(payload);
      setForm((current) => ({
        ...current,
        github_client_secret: "",
        session_secret_key: ""
      }));
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Unable to save GitHub OAuth secrets");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <form className="panel secretForm" onSubmit={(event) => void submit(event)}>
      <div className="secretFormHeader">
        <span className="githubSyncIcon"><Lock size={24} /></span>
        <span>
          <h2>GitHub OAuth secrets</h2>
          <p>Saved values are encrypted locally and never returned to the browser. Leave this screen after saving to clear typed secret values from the UI.</p>
        </span>
        <Badge tone={configStatus?.encrypted ? "success" : "warning"}>{configStatus?.encrypted ? "Encrypted" : "Local only"}</Badge>
      </div>
      <div className="secretStatusGrid">
        {(configStatus?.fields ?? []).map((field) => (
          <span className="secretStatus" key={field.name}>
            <strong>{fieldLabel(field.name)}</strong>
            <Badge tone={field.configured ? "success" : "danger"}>{field.configured ? "Configured" : "Missing"}</Badge>
          </span>
        ))}
      </div>
      <div className="secretInputGrid">
        <SecretInput
          label="GitHub Client ID"
          name="github-client-id"
          onChange={(value) => updateField("github_client_id", value)}
          placeholder="OAuth app client ID"
          value={form.github_client_id}
        />
        <SecretInput
          label="GitHub Client Secret"
          name="github-client-secret"
          onChange={(value) => updateField("github_client_secret", value)}
          placeholder="OAuth app client secret"
          secret
          value={form.github_client_secret}
        />
        <SecretInput
          label="Authorized Owner Login"
          name="github-owner-login"
          onChange={(value) => updateField("github_owner_login", value)}
          placeholder="Exact GitHub login allowed into this workspace"
          value={form.github_owner_login}
        />
        <SecretInput
          action={<button className="rowAction" onClick={() => updateField("session_secret_key", generatedSecret())} type="button">Generate</button>}
          label="Session Secret Key"
          name="session-secret-key"
          onChange={(value) => updateField("session_secret_key", value)}
          placeholder="At least 32 high-entropy characters"
          secret
          value={form.session_secret_key}
        />
        <SecretInput
          label="OAuth Callback URL"
          name="github-oauth-callback-url"
          onChange={(value) => updateField("github_oauth_callback_url", value)}
          placeholder="http://localhost:8000/auth/github/callback"
          value={form.github_oauth_callback_url}
        />
        <SecretInput
          label="Web App URL"
          name="web-app-url"
          onChange={(value) => updateField("web_app_url", value)}
          placeholder="http://127.0.0.1:3001"
          value={form.web_app_url}
        />
        <SecretInput
          label="GitHub API Base URL"
          name="github-api-base-url"
          onChange={(value) => updateField("github_api_base_url", value)}
          placeholder="https://api.github.com"
          value={form.github_api_base_url}
        />
        <SecretInput
          label="GitHub Web Base URL"
          name="github-web-base-url"
          onChange={(value) => updateField("github_web_base_url", value)}
          placeholder="https://github.com"
          value={form.github_web_base_url}
        />
      </div>
      <div className="securityNotes">
        <InfoLine icon={Shield} label="Write-only API" value="The save response only returns configured/missing flags." />
        <InfoLine icon={KeyRound} label="Encrypted at rest" value="Secrets are encrypted with a managed local Fernet key and files are hardened to owner-only permissions." />
        <InfoLine icon={Eye} label="No reveal control" value="Saved values are never rendered back into inputs or status views." />
      </div>
      {error ? <div className="connectNotice">{error}</div> : null}
      <div className="panelActions">
        <button className="primaryAction" disabled={isSaving} type="submit">
          <Save size={18} />
          {isSaving ? "Saving..." : "Save secrets securely"}
        </button>
        <button className="ghostAction" onClick={onCancel} type="button">
          Cancel
        </button>
      </div>
    </form>
  );
}

function GitHubAppSecretForm({
  configStatus,
  onCancel,
  onSave
}: {
  configStatus: GitHubAppConfigStatus | null;
  onCancel: () => void;
  onSave: (payload: GitHubAppConfigPayload) => Promise<void>;
}) {
  const [form, setForm] = useState<GitHubAppConfigPayload>({
    github_webhook_secret: "",
    github_app_id: "",
    github_app_slug: "",
    github_private_key: "",
    github_private_key_path: "",
    github_installation_id: ""
  });
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function updateField(field: keyof GitHubAppConfigPayload, value: string) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsSaving(true);
    try {
      await onSave({
        ...form,
        github_private_key: form.github_private_key || undefined,
        github_private_key_path: form.github_private_key_path || undefined,
        github_app_slug: form.github_app_slug || undefined,
        github_installation_id: form.github_installation_id || undefined,
        github_webhook_secret: form.github_webhook_secret || undefined
      });
      setForm((current) => ({
        ...current,
        github_webhook_secret: "",
        github_private_key: ""
      }));
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Unable to save GitHub App credentials");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <form className="panel secretForm" onSubmit={(event) => void submit(event)}>
      <div className="secretFormHeader">
        <span className="githubSyncIcon"><KeyRound size={24} /></span>
        <span>
          <h2>GitHub App credentials</h2>
          <p>Save installation-token credentials separately from OAuth. Verify them before enabling real branch, commit, PR, or comment writes.</p>
        </span>
        <Badge tone={configStatus?.encrypted ? "success" : "warning"}>{configStatus?.encrypted ? "Encrypted" : "Local only"}</Badge>
      </div>
      <div className="secretStatusGrid">
        {(configStatus?.fields ?? []).map((field) => (
          <span className="secretStatus" key={field.name}>
            <strong>{fieldLabel(field.name)}</strong>
            <Badge tone={field.configured ? "success" : field.name.includes("VERIFIED") ? "warning" : "danger"}>
              {field.configured ? "Configured" : field.name.includes("VERIFIED") ? "Unverified" : "Missing"}
            </Badge>
          </span>
        ))}
      </div>
      <div className="secretInputGrid">
        <SecretInput
          label="Webhook Secret"
          name="github-webhook-secret"
          onChange={(value) => updateField("github_webhook_secret", value)}
          placeholder="GitHub App webhook secret"
          secret
          value={form.github_webhook_secret ?? ""}
        />
        <SecretInput
          label="GitHub App ID"
          name="github-app-id"
          onChange={(value) => updateField("github_app_id", value)}
          placeholder="Numeric GitHub App ID"
          value={form.github_app_id}
        />
        <SecretInput
          label="GitHub App Slug"
          name="github-app-slug"
          onChange={(value) => updateField("github_app_slug", value)}
          placeholder="Optional app slug"
          value={form.github_app_slug ?? ""}
        />
        <SecretInput
          label="Installation ID"
          name="github-installation-id"
          onChange={(value) => updateField("github_installation_id", value)}
          placeholder="Installation ID from the demo repo"
          value={form.github_installation_id ?? ""}
        />
        <SecretInput
          label="Private Key"
          name="github-app-private-key"
          onChange={(value) => updateField("github_private_key", value)}
          placeholder="Paste PEM private key or use a key path"
          secret
          value={form.github_private_key ?? ""}
        />
        <SecretInput
          label="Private Key Path"
          name="github-private-key-path"
          onChange={(value) => updateField("github_private_key_path", value)}
          placeholder="~/keys/repopilot-app.private-key.pem"
          value={form.github_private_key_path ?? ""}
        />
      </div>
      <div className="securityNotes">
        <InfoLine icon={Lock} label="Write mode" value="GITHUB_WRITES_ENABLED remains the hard gate for real GitHub mutations." />
        <InfoLine icon={CheckCircle2} label="Verification" value="Verification creates an installation token and stores only a timestamp marker." />
        <InfoLine icon={Eye} label="No reveal control" value="Private keys and webhook secrets are write-only in the dashboard." />
      </div>
      {error ? <div className="connectNotice">{error}</div> : null}
      <div className="panelActions">
        <button className="primaryAction" disabled={isSaving} type="submit">
          <Save size={18} />
          {isSaving ? "Saving..." : "Save GitHub App credentials"}
        </button>
        <button className="ghostAction" onClick={onCancel} type="button">
          Cancel
        </button>
      </div>
    </form>
  );
}

function ProfileScreen({ data, onLogout, onSettings }: { data: ConsoleState; onLogout: () => void; onSettings: () => void }) {
  const username = data.session?.username ?? "Platform Admin";
  const githubConnected = isGithubAccountConnected(data);
  return (
    <div className="screen">
      <ScreenHeader title="Profile" subtitle="Review your RepoPilot account and workspace access." />
      <div className="profileGrid">
        <section className="panel profilePanel">
          <div className="profileHero">
            <span className="avatar huge">{initials(username)}</span>
            <span>
              <h2>{username}</h2>
              <Badge tone="info">{data.session?.role ?? "local"}</Badge>
            </span>
          </div>
          <KeyValue icon={User} label="Workspace" value={workspaceLabel(data.installations)} />
          <KeyValue icon={Github} label="GitHub username" value={githubConnected ? username : "Not connected"} />
          <KeyValue icon={Mail} label="Email" value={data.session?.email ?? "N/A"} />
        </section>
        <section className="panel profilePanel">
          <h2>Activity summary</h2>
          <div className="activitySummary">
            <SummaryItem icon={FileText} label="Plans approved" value={data.activitySummary?.plans_approved ?? "Unavailable"} tone="info" />
            <SummaryItem icon={GitBranch} label="PR records" value={data.activitySummary?.pull_request_records ?? "Unavailable"} tone="violet" />
            <SummaryItem icon={Play} label="Agent runs" value={data.activitySummary?.agent_runs ?? "Unavailable"} tone="info" />
            <SummaryItem icon={Shield} label="Reviewed findings" value={data.activitySummary?.reviewed_security_findings ?? "Unavailable"} tone="warning" />
          </div>
        </section>
        <section className="panel profilePanel">
          <h2>API and access</h2>
          <KeyValue icon={Github} label="GitHub OAuth session" value={githubConnected ? "Active" : "Not connected"} />
          <KeyValue icon={Database} label="Imported GitHub accounts" value={String(data.installations.length)} />
          <button className="ghostAction wide" onClick={onSettings} type="button"><Github size={18} /> Manage GitHub access</button>
          {githubConnected ? <button className="ghostAction wide" onClick={onLogout} type="button"><Lock size={18} /> Sign out</button> : null}
        </section>
      </div>
    </div>
  );
}

function DetailRouteState({
  entityLabel,
  requestedId,
  status
}: {
  entityLabel: string;
  requestedId: string | null;
  status: DetailRouteStatus;
}) {
  if (status === "loading") {
    return <div className="screen"><EmptyState text={`Loading ${entityLabel}…`} /></div>;
  }
  if (status === "error") {
    return <div className="screen"><EmptyState text={`The ${entityLabel} could not be loaded. Refresh to retry.`} /></div>;
  }
  if (!requestedId || status === "missing") {
    return <div className="screen"><EmptyState text={`This ${entityLabel} URL is missing its identifier.`} /></div>;
  }
  return <div className="screen"><EmptyState text={`The ${entityLabel} “${requestedId}” was not found. It may be stale or no longer accessible.`} /></div>;
}

function SetupMini({ setup, onClick }: { setup: ReturnType<typeof setupState>; onClick: () => void }) {
  return (
    <button className="setupMini" onClick={onClick} type="button">
      <span className="ring" style={{ "--progress": `${setup.percent}%` } as React.CSSProperties} />
      <span>
        <strong>Setup in progress</strong>
        <small>{setup.completed} of {setup.steps.length} completed</small>
      </span>
    </button>
  );
}

function CommandList({ title, items, tone }: { title: string; items: string[]; tone: string }) {
  return (
    <div className={`commandList ${tone}`}>
      <h3>{title}</h3>
      {items.map((item, index) => <code key={`${item}-${index}`}>{item}</code>)}
      {items.length === 0 ? <EmptyState text="No commands are configured." /> : null}
    </div>
  );
}

function ReadOnlyMeta({ label, value }: { label: string; value: string }) {
  return <div className="reportMetaItem"><span>{label}</span><strong>{value}</strong></div>;
}

function TraceJson({ items }: { items: Array<Record<string, unknown>> }) {
  if (items.length === 0) {
    return <EmptyState text="No records are available for this tab." />;
  }
  return <pre className="jsonBlock">{JSON.stringify(items, null, 2)}</pre>;
}

function BarChart({ metrics }: { metrics: Record<string, unknown> }) {
  const categoryRates = recordValue(metrics.category_pass_rates);
  const data = Object.entries(categoryRates ?? {})
    .filter(([, value]) => typeof value === "number" && Number.isFinite(value))
    .map(([label, value]) => [labelize(label), metricPercent(value).value] as const)
    .sort(([left], [right]) => left.localeCompare(right));
  if (data.length === 0) {
    return <EmptyState text="No issue-type success metrics are present in the latest eval report." />;
  }
  return (
    <div className="barChart">
      {data.map(([label, value]) => (
        <div className="barColumn" key={label}>
          <span style={{ height: `${value}%` }} />
          <strong>{value}%</strong>
          <small>{label}</small>
        </div>
      ))}
    </div>
  );
}

function FailureReasons({ metrics }: { metrics: Record<string, unknown> }) {
  const raw = metrics.failure_reasons;
  if (!Array.isArray(raw)) {
    return <EmptyState text="No failure reason breakdown is present in the latest eval report." />;
  }
  return (
    <div className="compactTable">
      {raw.map((item, index) => {
        const record = typeof item === "object" && item !== null ? item as Record<string, unknown> : {};
        return (
          <div className="compactRow" key={index}>
            <strong>{stringValue(record.reason) || "Unknown"}</strong>
            <span>{numberMetric(record.count).label}</span>
            <span>{metricPercent(record.percent).label}</span>
          </div>
        );
      })}
    </div>
  );
}

function setupState(data: ConsoleState) {
  const steps = [
    { label: "Connect GitHub account", done: isGithubAccountConnected(data) },
    { label: "Sync GitHub repositories", done: data.repositories.length > 0 },
    { label: "Select repository", done: data.repositories.length > 0 },
    { label: "Configure model provider", done: Boolean(["configured", "verified"].includes(data.readiness?.integrations.find((item) => item.name.toLowerCase().includes("model"))?.state ?? "")) },
    { label: "Set approval policies", done: Boolean(data.policy) },
    { label: "Index repository", done: data.repositories.some((repo) => Boolean(repo.last_indexed_sha)) },
    { label: "Create first agent-ready issue", done: data.issues.some((issue) => normalizedStatus(issue.status) === "agent_ready") }
  ];
  const completed = steps.filter((step) => step.done).length;
  return { steps, completed, percent: Math.round((completed / steps.length) * 100) };
}

function nextSetupView(setup: ReturnType<typeof setupState>): View {
  const next = setup.steps.findIndex((step) => !step.done);
  if (next <= 1) return "connect";
  if (next === 2 || next === 5) return "repositories";
  if (next === 3 || next === 4) return "settings";
  if (next === 6) return "issues";
  return "dashboard";
}

function isEntityView(view: View) {
  return ["repository-detail", "issue-detail", "run-trace", "pull-request-detail", "security-detail"].includes(view);
}

function isEntityRoute(route: ConsoleRoute) {
  return isEntityView(route.view) || (route.view === "agent-runs" && Boolean(route.entityId));
}

function routeEntityExists(data: ConsoleState, route: ConsoleRoute) {
  const entityId = route.entityId;
  if (!entityId) return false;
  if (route.view === "repository-detail") return data.repositories.some((item) => repositoryMatchesId(item, entityId));
  if (route.view === "issue-detail") return data.issues.some((item) => item.id === entityId);
  if (route.view === "agent-runs" || route.view === "run-trace") return data.runs.some((item) => item.id === entityId);
  if (route.view === "pull-request-detail") return data.pullRequests.some((item) => item.pr_id === entityId);
  if (route.view === "security-detail") return data.securityFindings.some((item) => item.id === entityId);
  return false;
}

function upsertBy<T>(items: T[], next: T, key: (item: T) => string): T[] {
  const nextKey = key(next);
  const index = items.findIndex((item) => key(item) === nextKey);
  if (index < 0) return [next, ...items];
  return items.map((item, itemIndex) => itemIndex === index ? next : item);
}

function upsertRepository(items: RepositoryResponse[], next: RepositoryResponse): RepositoryResponse[] {
  const nextIds = new Set([next.id, ...(next.alias_ids ?? [])]);
  return [next, ...items.filter((item) => ![item.id, ...(item.alias_ids ?? [])].some((id) => nextIds.has(id)))];
}

function modelProviderConfigSignature(config: ModelProviderConfigStatus | null, catalog: ModelCatalogResponse | null) {
  const catalogSignature = (catalog?.providers ?? [])
    .map((provider) => `${provider.id}:${provider.default_base_url}:${provider.models.map((model) => model.id).join(",")}`)
    .join("|");
  const configSignature = [
    config?.provider ?? "",
    config?.model ?? "",
    config?.base_url ?? "",
    config?.reasoning_level ?? "",
    config?.api_key_configured ? "api-key" : "no-api-key",
    config?.configured_api_key_providers.join(",") ?? ""
  ].join(":");
  return `${catalogSignature}::${configSignature}`;
}

function isGithubAccountConnected(data: ConsoleState) {
  return Boolean(data.session?.github_user_id);
}

function githubOAuthIntegration(readiness: ReadinessResponse | null) {
  return readiness?.integrations.find((item) => item.name.toLowerCase().includes("github oauth")) ?? null;
}

function readinessIntegration(readiness: ReadinessResponse | null, needle: string) {
  return readiness?.integrations.find((item) => item.name.toLowerCase().includes(needle.toLowerCase())) ?? null;
}

function githubOAuthConfigured(status: GitHubOAuthConfigStatus | null) {
  const required = ["GITHUB_CLIENT_ID", "GITHUB_CLIENT_SECRET", "REPOPILOT_GITHUB_OWNER_LOGIN", "GITHUB_OAUTH_CALLBACK_URL", "WEB_APP_URL", "SESSION_SECRET_KEY"];
  return required.every((name) => status?.fields.some((field) => field.name === name && field.configured));
}

function githubAppConfigured(status: GitHubAppConfigStatus | null) {
  const required = ["GITHUB_APP_ID", "GITHUB_INSTALLATION_ID"];
  const hasRequired = required.every((name) => status?.fields.some((field) => field.name === name && field.configured));
  const hasKey = status?.fields.some((field) => ["GITHUB_APP_PRIVATE_KEY", "GITHUB_PRIVATE_KEY_PATH"].includes(field.name) && field.configured) ?? false;
  return hasRequired && hasKey;
}

function fieldLabel(name: string) {
  const labels: Record<string, string> = {
    GITHUB_WEBHOOK_SECRET: "Webhook Secret",
    GITHUB_APP_ID: "App ID",
    GITHUB_APP_SLUG: "App Slug",
    GITHUB_APP_PRIVATE_KEY: "Private Key",
    GITHUB_PRIVATE_KEY_PATH: "Private Key Path",
    GITHUB_INSTALLATION_ID: "Installation ID",
    GITHUB_APP_VERIFIED_AT: "App Verified At",
    GITHUB_APP_VERIFIED_INSTALLATION_ID: "Verified Installation",
    GITHUB_WRITE_SMOKE_VERIFIED_AT: "Write Smoke Verified",
    GITHUB_CLIENT_ID: "Client ID",
    REPOPILOT_GITHUB_OWNER_LOGIN: "Authorized owner",
    GITHUB_CLIENT_SECRET: "Client Secret",
    GITHUB_OAUTH_CALLBACK_URL: "Callback URL",
    WEB_APP_URL: "Web App URL",
    SESSION_SECRET_KEY: "Session Key",
    GITHUB_API_BASE_URL: "API Base",
    GITHUB_WEB_BASE_URL: "Web Base"
  };
  return labels[name] ?? name;
}

function generatedSecret() {
  const bytes = new Uint8Array(48);
  window.crypto.getRandomValues(bytes);
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function isNavActive(view: View, item: View) {
  if (item === "repositories") return view === item || view === "repository-detail";
  if (item === "issues") return view === item || view === "issue-detail";
  if (item === "agent-runs") return view === item || view === "run-trace";
  if (item === "pull-requests") return view === item || view === "pull-request-detail";
  if (item === "security") return view === item || view === "security-detail";
  return view === item;
}

function filterIssues(issues: IssueResponse[], query: string) {
  return issues.filter((issue) => searchable(`${issue.number} ${issue.title} ${issue.repository?.name ?? ""} ${issue.issue_type ?? ""} ${issue.status}`, query));
}

function filterRuns(runs: RunSummary[], issues: IssueResponse[], query: string) {
  return runs.filter((run) => {
    const issue = issues.find((item) => item.id === run.issue_id);
    return searchable(`${run.id} ${run.state} ${run.latest_step ?? ""} ${issue?.title ?? ""}`, query);
  });
}

function searchable(value: string, query: string) {
  return value.toLowerCase().includes(query.trim().toLowerCase());
}

function normalizedStatus(status: string) {
  const lowered = status.toLowerCase();
  if (lowered === "wait_for_approval" || lowered === "waiting_for_approval" || lowered === "awaiting_approval") return "wait_for_approval";
  if (lowered === "ready_for_review") return "ready_for_review";
  return lowered;
}

function issueColumn(issue: IssueResponse) {
  const status = normalizedStatus(issue.status);
  if (isPlanAwaitingApproval(issue.plan?.approval_status)) return "wait_for_approval";
  if (status.includes("blocked") || status.includes("rejected")) return "blocked";
  if (status.includes("planning") || issue.run?.state === "GENERATE_PLAN") return "planning";
  if (status.includes("progress") || issue.run?.state === "IMPLEMENT_PATCH") return "in_progress";
  if (status.includes("pr")) return "pr_opened";
  if (status === "agent_ready") return "agent_ready";
  if (status === "wait_for_approval") return "wait_for_approval";
  return "needs_info";
}

export function riskCounts(issues: IssueResponse[]) {
  return {
    low: issues.filter((issue) => issue.risk_score < 35).length,
    medium: issues.filter((issue) => issue.risk_score >= 35 && issue.risk_score < 70).length,
    high: issues.filter((issue) => issue.risk_score >= 70).length,
    blocked: issues.filter((issue) => issueColumn(issue) === "blocked").length
  };
}

function riskLabel(score: number) {
  if (score >= 85) return "Critical";
  if (score >= 70) return "High";
  if (score >= 35) return "Medium";
  return "Low";
}

function riskTone(score: number) {
  if (score >= 70) return "danger";
  if (score >= 35) return "warning";
  return "success";
}

function severityScore(severity: string) {
  const normalized = severity.toLowerCase();
  if (normalized === "critical") return 90;
  if (normalized === "high") return 75;
  if (normalized === "medium") return 50;
  if (normalized === "low") return 20;
  return 0;
}

function complexityTone(value: string | null) {
  if (!value) return "neutral";
  if (value.toLowerCase() === "high") return "danger";
  if (value.toLowerCase() === "medium") return "warning";
  return "success";
}

function statusTone(status: string) {
  const lowered = status.toLowerCase();
  if (lowered === "open") return "warning";
  if (["passed", "success", "succeeded", "ready_for_review", "opened", "approved", "agent_ready", "fixed", "configured", "verified"].some((item) => lowered.includes(item)) && !lowered.includes("unverified")) return "success";
  if (["waiting", "pending", "draft", "progress", "review", "approval", "queued", "unverified", "placeholder", "disabled"].some((item) => lowered.includes(item))) return "warning";
  if (["failed", "failure", "blocked", "rejected", "error", "critical", "missing"].some((item) => lowered.includes(item))) return "danger";
  if (["running", "ci", "plan"].some((item) => lowered.includes(item))) return "info";
  return "neutral";
}

function labelize(value: string) {
  return value.replace(/[._-]+/g, " ").replace(/\s+/g, " ").trim().replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function shortId(value: string) {
  return value.slice(0, 8);
}

function formatClock(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime()) || date.getFullYear() < 2000) {
    return "--:--";
  }
  const hh = String(date.getUTCHours()).padStart(2, "0");
  const mm = String(date.getUTCMinutes()).padStart(2, "0");
  return `${hh}:${mm}`;
}

function formatDateTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "at an unavailable time";
  return date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function relativeTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unavailable";
  const minutes = Math.max(0, Math.round((Date.now() - date.getTime()) / 60000));
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

function refreshStateLabel(lastRefreshedAt: string | null, isRefreshing: boolean) {
  if (isRefreshing) return "Refreshing current snapshot.";
  if (!lastRefreshedAt) return "Snapshot has not been refreshed in this session.";
  return `Last refreshed ${relativeTime(lastRefreshedAt)}. Auto-refresh checks relevant data every 30 seconds.`;
}

function elapsed(start: string, end: string | null) {
  const startTime = new Date(start).getTime();
  const endTime = end ? new Date(end).getTime() : Date.now();
  if (Number.isNaN(startTime) || Number.isNaN(endTime)) return "Unavailable";
  const seconds = Math.max(0, Math.round((endTime - startTime) / 1000));
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ${seconds % 60}s`;
}

function initials(value: string) {
  const parts = value.split(/[\s._-]+/).filter(Boolean);
  return (parts[0]?.[0] ?? "P").toUpperCase() + (parts[1]?.[0] ?? parts[0]?.[1] ?? "A").toUpperCase();
}

function workspaceLabel(installations: InstallationResponse[]) {
  return installations[0]?.account_name ?? "Platform Admin";
}

function lastIndexedLabel(repos: RepositoryResponse[]) {
  const indexedAt = latestRepositoryIndexTimestamp(repos);
  return indexedAt ? formatDateTime(indexedAt) : "Never";
}

function repositoryIndexLabel(repo: RepositoryResponse) {
  if (!repo.last_indexed_sha) return "Needs index";
  if (repo.index_stale) return "Stale";
  return labelize(repo.index_status ?? "indexed");
}

function repositoryIndexTone(repo: RepositoryResponse) {
  if (!repo.last_indexed_sha) return "warning";
  if (repo.index_stale) return "danger";
  return "success";
}

function ciPassRateLabel(prs: PullRequestSummary[]) {
  if (prs.length === 0) return "N/A";
  const withCi = prs.filter((pr) => pr.ci_status);
  if (withCi.length === 0) return "N/A";
  const passed = withCi.filter((pr) => passedCi(pr.ci_status)).length;
  return `${Math.round((passed / withCi.length) * 100)}%`;
}

function passedCi(status: string | null) {
  return ["passed", "success", "succeeded"].includes((status ?? "").toLowerCase());
}

function failedCi(status: string | null) {
  return ["failed", "failure", "error"].includes((status ?? "").toLowerCase());
}

function riskBucket(score: number): IssueRiskFilter {
  if (score >= 70) return "high";
  if (score >= 35) return "medium";
  return "low";
}

function statusBucket(status: string): AuditStatusFilter {
  const tone = statusTone(status);
  if (tone === "success") return "success";
  if (tone === "danger") return "failed";
  if (tone === "warning" || tone === "info") return "warning";
  return "recorded";
}

function latestValidation(pr: PullRequestSummary) {
  return pr.validation_results[0] ?? null;
}

function isPlanAwaitingApproval(status?: string | null) {
  const normalized = normalizedStatus(status ?? "");
  return ["draft", "waiting", "wait_for_approval", "pending"].includes(normalized);
}

function nextIssueAction(issue: IssueResponse) {
  if (!issue.plan) return "Generate plan";
  if (isPlanAwaitingApproval(issue.plan.approval_status)) return "Approve plan";
  if (issue.run) return nextRunAction(issue.run.state);
  return "Review issue";
}

type RunPrimaryAction = {
  key: string;
  label: string;
  detail: string;
  path: string;
  successMessage: string;
  body?: Record<string, unknown>;
};

function primaryRunAction(run: RunSummary): RunPrimaryAction | null {
  if (
    run.latest_step === "ORCHESTRATE_RUN"
    && ["blocked", "failed"].includes((run.latest_step_status ?? "").toLowerCase())
    && ["CREATE_BRANCH", "IMPLEMENT_PATCH", "GENERATE_TESTS", "RUN_LOCAL_VALIDATION", "RUN_SECURITY_CHECKS", "OPEN_DRAFT_PR", "FAILED"].includes(run.state.toUpperCase())
  ) {
    return {
      key: "retry",
      label: "Retry failed run",
      detail: "Creates a fresh run with the same approved plan, preserving the failed attempt and its evidence.",
      path: "/retry",
      successMessage: "A fresh retry run was queued."
    };
  }
  switch (run.state.toUpperCase()) {
    case "WAIT_FOR_APPROVAL":
      return {
        key: "execute",
        label: "Run to draft PR",
        detail: "Queues implementation, isolated validation, security gating, and draft-PR creation, then waits for trusted CI.",
        path: "/execute",
        successMessage: "Approved run queued through the trusted CI boundary."
      };
    case "CREATE_BRANCH":
      return {
        key: "execute",
        label: "Continue to draft PR",
        detail: "Queues the bounded implementation agent, validation, security gates, and draft-PR creation.",
        path: "/execute",
        successMessage: "Run queued through the trusted CI boundary."
      };
    case "RUN_LOCAL_VALIDATION":
      return {
        key: "security-scan",
        label: "Run security scan",
        detail: "Scans the generated patch and workspace before a draft PR record can be created.",
        path: "/security-scan",
        successMessage: "Security scan completed.",
        body: {}
      };
    case "RUN_SECURITY_CHECKS":
      return {
        key: "open-draft-pr",
        label: "Create draft PR record",
        detail: "Creates a gated local record or real GitHub draft PR when write readiness is enabled.",
        path: "/open-draft-pr",
        successMessage: "Draft PR record created.",
        body: {}
      };
    default:
      return null;
  }
}

function isTerminalRunState(state: string) {
  return ["READY_FOR_REVIEW", "CANCELLED", "FAILED", "REJECTED"].includes(state.toUpperCase());
}

function runActionStatus(state: string) {
  switch (state.toUpperCase()) {
    case "WAIT_FOR_CI":
      return "Waiting for CI evidence";
    case "READY_FOR_REVIEW":
      return "Ready for review";
    case "CANCELLED":
      return "Run cancelled";
    case "FAILED":
      return "Run failed";
    case "REJECTED":
      return "Run rejected";
    default:
      return "Workflow action unavailable";
  }
}

function runStageLabel(state: string) {
  switch (state.toUpperCase()) {
    case "WAIT_FOR_APPROVAL":
      return "Waiting for approval";
    case "WAIT_FOR_CI":
      return "Waiting for CI";
    case "READY_FOR_REVIEW":
      return "Ready for review";
    default:
      return labelize(state);
  }
}

function recordedRunDuration(run: RunSummary, trace: TraceData | null) {
  const state = run.state.toUpperCase();
  const waitingOrTerminal = ["WAIT_FOR_APPROVAL", "WAIT_FOR_CI", "READY_FOR_REVIEW", "CANCELLED", "FAILED", "REJECTED"].includes(state);
  const steps = trace?.steps ?? [];
  const lastStepAt = steps.length ? steps[steps.length - 1]?.created_at ?? null : null;
  const evidenceEnd = run.completed_at ?? (waitingOrTerminal ? lastStepAt : null);
  if (waitingOrTerminal && !evidenceEnd) return "Awaiting trace";
  return elapsed(run.started_at, evidenceEnd);
}

function nextRunAction(state?: string) {
  if (!state) return "Unavailable";
  const index = stateOrder.indexOf(state);
  if (index < 0 || index === stateOrder.length - 1) return "Review evidence";
  return labelize(stateOrder[index + 1]);
}

function agentName(stepName: string) {
  const step = stepName.toLowerCase();
  if (step.includes("triage")) return "Triage step";
  if (step.includes("context") || step.includes("retrieve")) return "Context step";
  if (step.includes("plan")) return "Planning step";
  if (step.includes("security")) return "Security step";
  if (step.includes("test") || step.includes("validation")) return "Validation step";
  if (step.includes("pr")) return "PR step";
  if (step.includes("ci")) return "CI step";
  return "Execution step";
}

function summaryFromOutput(value: Record<string, unknown> | null) {
  if (!value) return "No output payload";
  if (typeof value.summary === "string") return value.summary;
  if (typeof value.recommended_action === "string") return `Recommended action: ${value.recommended_action}`;
  if (Array.isArray(value.files_to_modify)) return `${value.files_to_modify.length} files to modify`;
  return Object.keys(value).slice(0, 4).join(", ") || "Output recorded";
}

function activityIcon(source: string) {
  if (source.includes("security")) return <Shield size={18} />;
  if (source.includes("pull")) return <GitBranch size={18} />;
  if (source.includes("agent")) return <Bot size={18} />;
  if (source.includes("validation")) return <Terminal size={18} />;
  return <FileText size={18} />;
}

function maybeOpenActivity(
  item: ActivityItem,
  data: ConsoleState,
  onIssue: (issue: IssueResponse) => void,
  onRun: (run: RunSummary) => void,
  onPr: (pr: PullRequestSummary) => void
) {
  const target = activityNavigationTarget(item);
  if (!target) return;
  if (target.kind === "issue") {
    const issue = data.issues.find((candidate) => candidate.id === target.entityId);
    if (issue) onIssue(issue);
  } else if (target.kind === "run") {
    const run = data.runs.find((candidate) => candidate.id === target.entityId);
    if (run) onRun(run);
  } else {
    const pr = data.pullRequests.find((candidate) => candidate.pr_id === target.entityId);
    if (pr) onPr(pr);
  }
}

function stringList(value: unknown) {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function stringValue(value: unknown) {
  return typeof value === "string" ? value : "";
}

function recordValue(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function metricPercent(value: unknown) {
  const numeric = typeof value === "number" && Number.isFinite(value) ? value : 0;
  const percent = numeric <= 1 ? numeric * 100 : numeric;
  return { label: `${Math.round(percent)}%`, value: Math.max(0, Math.min(100, Math.round(percent))) };
}

function numberMetric(value: unknown) {
  const numeric = typeof value === "number" && Number.isFinite(value) ? value : 0;
  return { label: String(Math.round(numeric)), value: numeric };
}

function prModeLabel(pr: PullRequestSummary) {
  return pr.is_local_record ? "Local record" : "GitHub PR";
}

function prModeDetail(pr: PullRequestSummary) {
  return pr.is_local_record
    ? "Local RepoPilot record; no real GitHub PR has been opened."
    : "Real GitHub pull request opened by the configured GitHub App.";
}

function prGithubUrl(pr: PullRequestSummary) {
  return pr.is_local_record ? null : pr.github_url ?? (pr.url.startsWith("http://") || pr.url.startsWith("https://") ? pr.url : null);
}

function reviewChecklist(pr: PullRequestSummary) {
  const files = pr.changed_files;
  const checks = ["Confirm implementation matches linked issue"];
  if (pr.is_local_record) checks.push("Confirm this local record before creating a real GitHub PR");
  if (files.some((file) => file.includes("auth"))) checks.push("Confirm token expiry policy");
  if (files.some((file) => file.includes(".github/workflows"))) checks.push("Confirm workflow permission changes");
  if (pr.validation_results.length) checks.push("Confirm validation results");
  if (pr.security_findings.length) checks.push("Confirm security findings");
  checks.push("Confirm rollback notes are acceptable");
  return checks.slice(0, 5);
}
