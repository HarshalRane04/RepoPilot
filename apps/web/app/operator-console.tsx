"use client";

import {
  AlertCircle,
  AlertTriangle,
  BarChart3,
  Bell,
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
import { genericKeyboard, rowKeyboard } from "./lib/keyboard";
import type {
  ActivityItem,
  EvalReport,
  GitHubAppConfigStatus,
  GitHubAppVerificationResponse,
  GitHubOAuthConfigStatus,
  GitHubLoginResponse,
  InstallationResponse,
  IssueResponse,
  MetricsResponse,
  ModelCatalogModel,
  ModelCatalogResponse,
  ModelProviderConfigStatus,
  ModelProviderVerificationResponse,
  OperatorData,
  PolicyResponse,
  PullRequestSummary,
  ReadinessResponse,
  RepositoryResponse,
  RunSummary,
  SecurityFindingResponse,
  SessionResponse,
  WebhookEvent
} from "../lib/api";

type View =
  | "landing"
  | "connect"
  | "setup"
  | "dashboard"
  | "repositories"
  | "repository-detail"
  | "issues"
  | "issue-detail"
  | "agent-runs"
  | "run-trace"
  | "pull-requests"
  | "pull-request-detail"
  | "ci-debugger"
  | "security"
  | "security-detail"
  | "evaluations"
  | "audit-logs"
  | "settings"
  | "profile";

type TraceData = {
  run?: {
    id: string;
    state: string;
    model_used: string | null;
    total_tokens: number;
    total_cost: number;
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
  pull_requests?: Array<{
    id: string;
    number: number;
    url: string;
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

type GitHubOAuthConfigPayload = {
  github_client_id: string;
  github_client_secret: string;
  session_secret_key: string;
  github_oauth_callback_url: string;
  web_app_url: string;
  github_api_base_url: string;
  github_web_base_url: string;
};

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
type AuditStatusFilter = "all" | "success" | "warning" | "failed";
type AuditRiskFilter = "all" | "low" | "medium" | "high";

const navItems: Array<{ view: View; label: string; icon: LucideIcon }> = [
  { view: "dashboard", label: "Dashboard", icon: Home },
  { view: "repositories", label: "Repositories", icon: Database },
  { view: "issues", label: "Issues", icon: AlertCircle },
  { view: "agent-runs", label: "Agent Runs", icon: Bot },
  { view: "pull-requests", label: "Pull Requests", icon: GitBranch },
  { view: "security", label: "Security", icon: Shield },
  { view: "evaluations", label: "Evaluations", icon: BarChart3 },
  { view: "audit-logs", label: "Audit Logs", icon: FileText },
  { view: "settings", label: "Settings", icon: Settings }
];

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

const issueColumns = [
  "needs_info",
  "agent_ready",
  "planning",
  "wait_for_approval",
  "in_progress",
  "pr_opened",
  "blocked"
];

const settingsTabs = ["GitHub", "Models", "Policies", "Tool Permissions", "Cost Limits", "Notifications"] as const;
type SettingsTab = typeof settingsTabs[number];
const useBrowserLayoutEffect = typeof window === "undefined" ? useEffect : useLayoutEffect;

export function OperatorConsole({ initialData, apiBaseUrl }: { initialData: OperatorData; apiBaseUrl: string }) {
  const [data, setData] = useState<ConsoleState>(initialData);
  const [view, setView] = useState<View>("dashboard");
  const [query, setQuery] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [selectedRepoId, setSelectedRepoId] = useState(initialData.repositories[0]?.id ?? "");
  const [selectedIssueId, setSelectedIssueId] = useState(initialData.issues[0]?.id ?? "");
  const [selectedRunId, setSelectedRunId] = useState(initialData.runs[0]?.id ?? "");
  const [selectedPrId, setSelectedPrId] = useState(initialData.pullRequests[0]?.pr_id ?? "");
  const [selectedFindingId, setSelectedFindingId] = useState(initialData.securityFindings[0]?.id ?? "");
  const [trace, setTrace] = useState<TraceData | null>(null);
  const [traceTab, setTraceTab] = useState<"timeline" | "tools" | "prompts" | "artifacts" | "audit">("timeline");
  const [issuesMode, setIssuesMode] = useState<"board" | "queue">("board");
  const [settingsTab, setSettingsTab] = useState<SettingsTab>("GitHub");
  const [showGithubSecretForm, setShowGithubSecretForm] = useState(false);
  const [showGithubAppSecretForm, setShowGithubAppSecretForm] = useState(false);
  const [selectedAuditKey, setSelectedAuditKey] = useState("");
  const [modelVerification, setModelVerification] = useState<ModelProviderVerificationResponse | null>(null);
  const [githubAppVerification, setGithubAppVerification] = useState<GitHubAppVerificationResponse | null>(null);
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

  const selectedRepo = data.repositories.find((repo) => repo.id === selectedRepoId) ?? data.repositories[0] ?? null;
  const selectedIssue = data.issues.find((issue) => issue.id === selectedIssueId) ?? data.issues[0] ?? null;
  const selectedRun = data.runs.find((run) => run.id === selectedRunId) ?? data.runs[0] ?? null;
  const selectedPr = data.pullRequests.find((pr) => pr.pr_id === selectedPrId) ?? data.pullRequests[0] ?? null;
  const selectedFinding = data.securityFindings.find((finding) => finding.id === selectedFindingId) ?? data.securityFindings[0] ?? null;
  const setup = useMemo(() => setupState(data), [data]);

  useBrowserLayoutEffect(() => {
    const syncHash = () => {
      const nextView = parseHash(window.location.hash);
      setView(nextView);
      const nextSettingsTab = parseSettingsTab(window.location.hash);
      if (nextSettingsTab) {
        setSettingsTab(nextSettingsTab);
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

  useEffect(() => {
    const timer = window.setInterval(() => {
      void refresh({ quiet: true });
    }, 20000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if ((view === "agent-runs" || view === "run-trace") && selectedRun?.id) {
      void loadTrace(selectedRun.id);
    }
  }, [selectedRun?.id, view]);

  async function refresh(options?: { quiet?: boolean }) {
    if (!options?.quiet) {
      setIsRefreshing(true);
      setNotice(null);
    }
    try {
      const next = await Promise.all([
        fetchJson<SessionResponse>("/auth/session"),
        fetchJson<MetricsResponse>("/metrics/overview"),
        fetchJson<WebhookEvent[]>("/webhooks/events"),
        fetchJson<RepositoryResponse[]>("/repos"),
        fetchJson<InstallationResponse[]>("/installations"),
        fetchJson<IssueResponse[]>("/issues?limit=300"),
        fetchJson<PullRequestSummary[]>("/prs?limit=200"),
        fetchJson<SecurityFindingResponse[]>("/security/findings?limit=300"),
        fetchJson<ActivityItem[]>("/activity?limit=160"),
        fetchJson<RunSummary[]>("/runs?limit=80"),
        fetchJson<{ reports: EvalReport[] }>("/evals/reports"),
        fetchJson<ReadinessResponse>("/settings/readiness"),
        fetchJson<PolicyResponse>("/settings/policy"),
        fetchJson<GitHubOAuthConfigStatus>("/settings/github/oauth"),
        fetchJson<GitHubAppConfigStatus>("/settings/github/app"),
        fetchJson<ModelCatalogResponse>("/settings/models/catalog"),
        fetchJson<ModelProviderConfigStatus>("/settings/models/config")
      ]);
      setData((current) => ({
        ...current,
        session: next[0],
        metrics: next[1],
        events: next[2],
        repositories: next[3],
        installations: next[4],
        issues: next[5],
        pullRequests: next[6],
        securityFindings: next[7],
        activities: next[8],
        runs: next[9],
        evalReports: next[10].reports,
        readiness: next[11],
        policy: next[12],
        githubOAuthConfig: next[13],
        githubAppConfig: next[14],
        modelCatalog: next[15],
        modelConfig: next[16]
      }));
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

  async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(`${apiBaseUrl}${path}`, {
      ...init,
      credentials: "include"
    });
    if (!response.ok) {
      const body = await response.text();
      throw new Error(body || `${response.status} ${response.statusText}`);
    }
    return (await response.json()) as T;
  }

  function navigate(next: View) {
    setView(next);
    window.location.hash = next === "settings" ? settingsHash(settingsTab) : next;
  }

  function selectSettingsTab(next: SettingsTab) {
    setSettingsTab(next);
    window.location.hash = settingsHash(next);
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
        window.location.hash = settingsHash("GitHub");
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
    setNotice(status.api_key_configured ? "Model provider saved securely." : "Model provider saved. Add an API key to connect it.");
    await refresh({ quiet: true });
  }

  async function verifyModelProvider() {
    setNotice(null);
    try {
      const result = await fetchJson<ModelProviderVerificationResponse>("/settings/models/verify", { method: "POST" });
      setModelVerification(result);
      setNotice(result.ok ? "Model provider responded successfully." : result.detail);
    } catch (error) {
      setModelVerification(null);
      setNotice(error instanceof Error ? error.message : "Model provider verification failed");
    }
  }

  async function indexRepository(repo: RepositoryResponse) {
    const sourcePath = window.prompt("Local source path to index", "/Users/harshalrane/Documents/RepoPilot");
    if (!sourcePath) {
      return;
    }
    setNotice(null);
    try {
      await fetchJson(`/repos/${repo.id}/index`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source_path: sourcePath })
      });
      setNotice(`Indexing completed for ${repo.owner}/${repo.name}.`);
      await refresh();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Repository indexing failed");
    }
  }

  async function generatePlan(issue: IssueResponse) {
    setNotice(null);
    try {
      const response = await fetchJson<{ plan_id: string; run_id: string }>(`/issues/${issue.id}/plan`, { method: "POST" });
      setSelectedRunId(response.run_id);
      setNotice(`Plan generated for issue #${issue.number}.`);
      await refresh();
      navigate("issue-detail");
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
      await fetchJson(`/plans/${issue.plan.id}/approve`, { method: "POST" });
      setNotice(`Plan approved for issue #${issue.number}.`);
      await refresh();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Plan approval failed");
    }
  }

  async function rejectPlan(issue: IssueResponse) {
    if (!issue.plan) {
      setNotice("No plan is available for this issue yet.");
      return;
    }
    const reason = window.prompt("Reason for rejecting this plan", "Scope or risk needs human revision.");
    if (!reason) {
      return;
    }
    setNotice(null);
    try {
      await fetchJson(`/plans/${issue.plan.id}/reject`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason })
      });
      setNotice(`Plan rejected for issue #${issue.number}.`);
      await refresh();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Plan rejection failed");
    }
  }

  async function revisePlan(issue: IssueResponse) {
    if (!issue.plan) {
      setNotice("No plan is available for this issue yet.");
      return;
    }
    const instructions = window.prompt("Revision instructions", "Narrow the scope and add validation details.");
    if (!instructions) {
      return;
    }
    setNotice(null);
    try {
      const response = await fetchJson<{ new_plan_id: string; version: number }>(`/plans/${issue.plan.id}/revise`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ instructions })
      });
      setNotice(`Plan revision v${response.version} created for issue #${issue.number}.`);
      await refresh();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Plan revision failed");
    }
  }

  async function runAction(run: RunSummary, path: string, successMessage: string) {
    setNotice(null);
    try {
      await fetchJson(`/runs/${run.id}${path}`, { method: "POST" });
      setNotice(successMessage);
      await refresh();
      await loadTrace(run.id);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Run action failed");
    }
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
    const logText = window.prompt("Paste the GitHub Actions log text to analyze", latestValidation(pr)?.parsed_summary ?? "");
    if (logText === null) {
      return;
    }
    setNotice(null);
    try {
      await fetchJson(`/prs/${pr.pr_id}/ci`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          workflow_name: "github-actions",
          conclusion: pr.ci_status === "passed" ? "success" : "failure",
          log_text: logText
        })
      });
      setNotice(`CI analysis updated for PR #${pr.pr_number}.`);
      await refresh();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "CI analysis failed");
    }
  }

  async function createRevisionPlanFromCi(pr: PullRequestSummary) {
    const instructions = window.prompt("Revision instructions", "Use CI failure evidence, keep changes inside the approved plan, and rerun validation/security.");
    if (!instructions) {
      return;
    }
    setNotice(null);
    try {
      const response = await fetchJson<{ plan_id: string; version: number }>(`/prs/${pr.pr_id}/revision-plan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ instructions })
      });
      setNotice(`Revision plan v${response.version} created for PR #${pr.pr_number}.`);
      await refresh();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Revision plan creation failed");
    }
  }

  async function updateSecurityFindingStatus(finding: SecurityFindingResponse, status: string) {
    const needsReason = status === "acknowledged" || status === "false_positive";
    const reason = needsReason ? window.prompt("Security review reason", finding.status_reason ?? "Reviewed by operator.") : "";
    if (needsReason && !reason) {
      return;
    }
    setNotice(null);
    try {
      await fetchJson(`/security/findings/${finding.id}/status`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status, reason })
      });
      setNotice(`Security finding marked ${labelize(status)}.`);
      await refresh();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Security finding update failed");
    }
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

  async function triageIssue(issue: IssueResponse) {
    setNotice(null);
    try {
      await fetchJson(`/issues/${issue.id}/triage`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ body: issue.title })
      });
      setNotice(`Triage updated for issue #${issue.number}.`);
      await refresh();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Issue triage failed");
    }
  }

  function selectRepository(repo: RepositoryResponse) {
    setSelectedRepoId(repo.id);
    navigate("repository-detail");
  }

  function selectIssue(issue: IssueResponse) {
    setSelectedIssueId(issue.id);
    navigate("issue-detail");
  }

  function selectRun(run: RunSummary, target: View = "agent-runs") {
    setSelectedRunId(run.id);
    setTrace(null);
    navigate(target);
  }

  function selectPr(pr: PullRequestSummary, target: View = "pull-request-detail") {
    setSelectedPrId(pr.pr_id);
    navigate(target);
  }

  function selectFinding(finding: SecurityFindingResponse) {
    setSelectedFindingId(finding.id);
    navigate("security-detail");
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
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = isNavActive(view, item.view);
            return (
              <button className={active ? "navItem active" : "navItem"} key={item.view} onClick={() => navigate(item.view)} type="button" aria-current={active ? "page" : undefined}>
                <Icon size={20} aria-hidden="true" />
                <span>{item.label}</span>
              </button>
            );
          })}
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
          <label className="commandSearch">
            <Search size={20} aria-hidden="true" />
            <input
              aria-label="Search repos, issues, and pull requests"
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search repos, issues, PRs..."
              value={query}
            />
            <kbd aria-label="Keyboard shortcut Command K">⌘ K</kbd>
          </label>
          <button className="iconOnly" disabled={isRefreshing} onClick={() => void refresh()} aria-label="Refresh live data" type="button">
            <RefreshCcw size={19} aria-hidden="true" className={isRefreshing ? "refreshSpinner" : ""} />
          </button>
          <button
            className="iconOnly notify"
            onClick={() => {
              setSettingsTab("Notifications");
              setView("settings");
              window.location.hash = settingsHash("Notifications");
            }}
            aria-label="Notification settings"
            type="button"
          >
            <Bell size={21} aria-hidden="true" />
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
          {view === "dashboard" ? (
            <DashboardScreen data={data} query={query} onIssue={selectIssue} onRun={selectRun} onSecurity={() => navigate("security")} isRefreshing={isRefreshing} />
          ) : null}
          {view === "repositories" ? (
            <RepositoriesScreen
              data={data}
              query={query}
              onConnect={startGithubFlow}
              onRepo={selectRepository}
              statusFilter={repoStatusFilter}
              setStatusFilter={setRepoStatusFilter}
            />
          ) : null}
          {view === "repository-detail" ? (
            <RepositoryDetailScreen
              issues={data.issues}
              onIndex={indexRepository}
              onIssue={selectIssue}
              onIssues={() => navigate("issues")}
              repo={selectedRepo}
            />
          ) : null}
          {view === "issues" ? (
            <IssuesScreen
              issues={data.issues}
              repositoryFilter={issueRepositoryFilter}
              riskFilter={issueRiskFilter}
              typeFilter={issueTypeFilter}
              mode={issuesMode}
              onGeneratePlan={generatePlan}
              onIssue={selectIssue}
              onTriage={triageIssue}
              query={query}
              repositories={data.repositories}
              setRepositoryFilter={setIssueRepositoryFilter}
              setMode={setIssuesMode}
              setRiskFilter={setIssueRiskFilter}
              setTypeFilter={setIssueTypeFilter}
            />
          ) : null}
          {view === "issue-detail" ? (
            <IssueDetailScreen issue={selectedIssue} onApprove={approvePlan} onGeneratePlan={generatePlan} onReject={rejectPlan} onRevise={revisePlan} />
          ) : null}
          {view === "agent-runs" ? (
            <AgentRunsScreen
              issues={data.issues}
              onRun={selectRun}
              onStart={(run) => void runAction(run, "/start", "Run moved to CREATE_BRANCH.")}
              onStop={(run) => void runAction(run, "/stop", "Run cancelled.")}
              query={query}
              runs={data.runs}
              selectedRun={selectedRun}
              trace={trace}
            />
          ) : null}
          {view === "run-trace" ? (
            <RunTraceScreen selectedRun={selectedRun} setTab={setTraceTab} tab={traceTab} trace={trace} />
          ) : null}
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
          {view === "pull-request-detail" ? (
            <PullRequestDetailScreen
              onAnalyzeCi={analyzeCi}
              onOpenIssue={(issueId) => {
                setSelectedIssueId(issueId);
                navigate("issue-detail");
              }}
              onOpenRun={(runId) => {
                setSelectedRunId(runId);
                navigate("run-trace");
              }}
              onRevisionPlan={createRevisionPlanFromCi}
              onSecurityReview={runSecurityReview}
              pr={selectedPr}
            />
          ) : null}
          {view === "ci-debugger" ? <CiDebuggerScreen onAnalyzeCi={analyzeCi} pr={selectedPr} /> : null}
          {view === "security" ? (
            <SecurityScreen findings={data.securityFindings} onFinding={selectFinding} policy={data.policy} query={query} />
          ) : null}
          {view === "security-detail" ? <SecurityDetailScreen finding={selectedFinding} onUpdateStatus={updateSecurityFindingStatus} /> : null}
          {view === "evaluations" ? <EvaluationsScreen evalReports={data.evalReports} onRunEvaluation={runEvaluation} repositories={data.repositories} runs={data.runs} /> : null}
          {view === "audit-logs" ? (
            <AuditLogsScreen
              activities={data.activities}
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
            />
          ) : null}
          {view === "profile" ? <ProfileScreen data={data} onGithub={startGithubFlow} /> : null}
        </main>
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
    ["Draft PR Generation", "Generate production-ready code and open draft pull requests.", GitBranch],
    ["CI Debugging", "Detect failures, fix issues, and re-run CI automatically.", Terminal],
    ["Security Checks", "Run static analysis and dependency scans on every change.", Shield]
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
          <button disabled type="button">Docs unavailable</button>
          <button onClick={onSignIn} type="button">
            Sign in
          </button>
        </nav>
      </header>
      <section className="heroGrid">
        <div className="heroCopy">
          <h1>
            Agentic GitHub Development, with <span>Human Control</span>
          </h1>
          <p>RepoPilot AI turns GitHub issues into planned, tested, security-scanned draft pull requests while keeping humans in control.</p>
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
            ["Draft PR Opened", "draft"],
            ["CI Passed", "all checks passed"]
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
      <ScreenHeader title="Set up RepoPilot AI" subtitle="Complete these steps to start turning GitHub issues into safe draft pull requests." />
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

function DashboardScreen({
  data,
  query,
  onIssue,
  onRun,
  onSecurity,
  isRefreshing
}: {
  data: ConsoleState;
  query: string;
  onIssue: (issue: IssueResponse) => void;
  onRun: (run: RunSummary) => void;
  onSecurity: () => void;
  isRefreshing: boolean;
}) {
  const issues = filterIssues(data.issues, query);
  const runs = filterRuns(data.runs, data.issues, query).slice(0, 3);
  const activity = data.activities.slice(0, 5);
  const risk = riskCounts(data.issues);
  const avgCost = data.runs.length ? data.runs.reduce((sum, run) => sum + run.total_cost, 0) / data.runs.length : 0;
  const ciRate = data.metrics?.ci_total_prs ? metricPercent(data.metrics.ci_pass_rate).label : ciPassRateLabel(data.pullRequests);
  const firstRunCiRate = data.metrics?.ci_total_prs ? metricPercent(data.metrics.ci_first_run_ci_pass_rate).label : "N/A";
  const revisionCiRate = data.metrics?.ci_revised_pr_count ? metricPercent(data.metrics.ci_pass_after_revision_rate).label : "N/A";
  return (
    <div className="screen">
      <ScreenHeader title="Dashboard" subtitle="Your agentic GitHub development command center." />
      <section className={`statGrid ten${isRefreshing ? " is-loading" : ""}`}>
        <StatCard label="Connected repositories" value={data.metrics?.repositories ?? data.repositories.length} />
        <StatCard label="Agent-ready issues" value={data.issues.filter((issue) => normalizedStatus(issue.status) === "agent_ready").length} />
        <StatCard label="Plans awaiting approval" value={data.issues.filter((issue) => issue.plan?.approval_status === "draft").length} />
        <StatCard label="Draft PRs created" value={data.metrics?.open_pull_requests ?? data.pullRequests.length} />
        <StatCard label="CI pass rate" value={ciRate} />
        <StatCard label="First-run CI" value={firstRunCiRate} />
        <StatCard label="CI after revision" value={revisionCiRate} />
        <StatCard label="Security blocks" value={data.metrics?.blocking_security_findings ?? 0} />
        <StatCard label="Fixup attempts" value={data.metrics?.ci_revision_fixup_attempts ?? 0} />
        <StatCard label="Avg cost/task" value={formatMoney(avgCost)} />
      </section>
      <div className="dashboardGrid">
        <section className="panel">
          <PanelHeader icon={Bot} title="Active Agent Runs" />
          <div className="listRows" role="list" aria-label="Active agent runs list">
            {runs.map((run) => {
              const issue = data.issues.find((item) => item.id === run.issue_id);
              return (
                <button className="dataRow clickable" key={run.id} onClick={() => onRun(run)} type="button" aria-label={`Agent run ${issue ? `for issue #${issue.number} ${issue.title}` : shortId(run.id)}`}>
                  <span className="iconTile violet">
                    <GitBranch size={18} />
                  </span>
                  <strong>{issue ? `Issue #${issue.number} ${issue.title}` : shortId(run.id)}</strong>
                  <Badge tone={statusTone(run.state)}>{labelize(run.state)}</Badge>
                  <Badge tone={riskTone(issue?.risk_score ?? 0)}>{riskLabel(issue?.risk_score ?? 0)}</Badge>
                </button>
              );
            })}
            {runs.length === 0 ? <EmptyState text="No agent runs match the current data." /> : null}
          </div>
          <button className="panelLink" onClick={() => onRun(data.runs[0])} disabled={!data.runs[0]} type="button">
            View all agent runs <ChevronRight size={16} />
          </button>
        </section>
        <section className="panel">
          <PanelHeader icon={Shield} title="Risk Summary" />
          <RiskRows risk={risk} onSecurity={onSecurity} />
        </section>
      </div>
      <section className="panel">
        <PanelHeader icon={Clock3} title="Recent Activity" />
        <div className="activityTable" role="list" aria-label="Recent activity feed">
          {activity.map((item, index) => (
            <button className="activityLine" key={`${item.source}-${item.action}-${index}`} onClick={() => maybeOpenActivity(item, data, onIssue, onRun)} type="button" aria-label={`${labelize(item.source)} ${item.action} ${item.status} at ${formatClock(item.created_at)}`}>
              <time>{formatClock(item.created_at)}</time>
              <span className="iconTile blue">{activityIcon(item.source)}</span>
              <strong>{labelize(item.source)}</strong>
              <span>{item.action}</span>
              <Badge tone={statusTone(item.status)}>{labelize(item.status)}</Badge>
            </button>
          ))}
          {activity.length === 0 ? <EmptyState text="No activity has been recorded yet." /> : null}
        </div>
      </section>
      {issues.length === 0 && query ? <EmptyState text="No dashboard issues match the current search." /> : null}
    </div>
  );
}

function RepositoriesScreen({
  data,
  query,
  onConnect,
  onRepo,
  setStatusFilter,
  statusFilter
}: {
  data: ConsoleState;
  query: string;
  onConnect: () => void;
  onRepo: (repo: RepositoryResponse) => void;
  setStatusFilter: (filter: RepoStatusFilter) => void;
  statusFilter: RepoStatusFilter;
}) {
  const repos = data.repositories.filter((repo) => {
    const matchesQuery = searchable(`${repo.owner}/${repo.name} ${repo.language ?? ""} ${repo.framework ?? ""}`, query);
    if (!matchesQuery) return false;
    if (statusFilter === "indexed") return Boolean(repo.last_indexed_sha);
    if (statusFilter === "needs-indexing") return !repo.last_indexed_sha;
    if (statusFilter === "ci-failing") {
      return data.pullRequests.some((pr) => pr.repository?.id === repo.id && failedCi(pr.ci_status));
    }
    return true;
  });
  const indexed = data.repositories.filter((repo) => repo.last_indexed_sha).length;
  const needsIndex = data.repositories.filter((repo) => !repo.last_indexed_sha).length;
  const ciFailing = data.repositories.filter((repo) => data.pullRequests.some((pr) => pr.repository?.id === repo.id && failedCi(pr.ci_status))).length;
  return (
    <div className="screen">
      <ScreenHeader title="Repositories" subtitle="Connected GitHub repositories and indexing status." />
      <GitHubSyncPanel data={data} onConnect={onConnect} compact />
      <div className="toolbar">
        <label className="inlineSearch">
          <Search size={18} />
          <input readOnly value={query} placeholder="Search repositories..." />
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
                      {repo.name}
                    </span>
                  </td>
                  <td>{repo.language ?? "Unavailable"}</td>
                  <td>{repo.framework ?? "Unavailable"}</td>
                  <td><code>{repo.last_indexed_sha ? repo.last_indexed_sha.slice(0, 7) : "not indexed"}</code></td>
                  <td>{repo.issue_count}</td>
                  <td className="greenText">{data.issues.filter((issue) => issue.repository_id === repo.id && normalizedStatus(issue.status) === "agent_ready").length}</td>
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
          <SummaryItem icon={Database} label="Indexed repos" value={indexed} tone="success" />
          <SummaryItem icon={Clock3} label="Needs indexing" value={needsIndex} tone="warning" />
          <SummaryItem icon={X} label="CI failing repos" value={ciFailing} tone="danger" />
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
  const repoIssues = issues.filter((issue) => issue.repository_id === repo.id);
  const highRisk = repoIssues.filter((issue) => issue.risk_score >= 70);
  const agentReady = repoIssues.filter((issue) => normalizedStatus(issue.status) === "agent_ready");
  return (
    <div className="screen">
      <Breadcrumb trail={["Repositories", repo.name]} />
      <div className="titleRow">
        <ScreenHeader title={repo.name} subtitle={`${repo.framework ?? repo.language ?? "Repository"} monitored by RepoPilot AI.`} />
        <button className="primaryAction" onClick={() => onIndex(repo)} type="button">
          <RefreshCcw size={20} />
          Index repository
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
      <section className="panel">
        <PanelHeader title="Suggested Improvements" />
        <div className="suggestionList">
          {repoIssues.slice(0, 4).map((issue) => (
            <button key={issue.id} onClick={() => onIssue(issue)} type="button">
              <CheckCircle2 size={18} />
              <span>{issue.title}</span>
              <ChevronRight size={18} />
            </button>
          ))}
          {repoIssues.length === 0 ? <EmptyState text="Suggestions appear after issues are triaged." /> : null}
        </div>
      </section>
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
  onGeneratePlan,
  onTriage
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
  onGeneratePlan: (issue: IssueResponse) => void;
  onTriage: (issue: IssueResponse) => void;
}) {
  const issueTypes = Array.from(new Set(issues.map((issue) => issue.issue_type).filter((value): value is string => Boolean(value)))).sort();
  const filtered = filterIssues(issues, query).filter((issue) => {
    if (repositoryFilter !== "all" && issue.repository_id !== repositoryFilter) return false;
    if (riskFilter !== "all" && riskBucket(issue.risk_score) !== riskFilter) return false;
    if (typeFilter !== "all" && issue.issue_type !== typeFilter) return false;
    return true;
  });
  return (
    <div className="screen">
      <ScreenHeader title={mode === "board" ? "Issues Board" : "Issue Queue"} subtitle="Track issues from triage to draft pull request." />
      <div className="toolbar">
        <select onChange={(event) => setRepositoryFilter(event.target.value)} value={repositoryFilter}>
          <option value="all">All repositories</option>
          {repositories.map((repo) => (
            <option key={repo.id} value={repo.id}>{repo.owner}/{repo.name}</option>
          ))}
        </select>
        <select onChange={(event) => setRiskFilter(event.target.value as IssueRiskFilter)} value={riskFilter}>
          <option value="all">All risks</option>
          <option value="low">Low risk</option>
          <option value="medium">Medium risk</option>
          <option value="high">High risk</option>
        </select>
        <select onChange={(event) => setTypeFilter(event.target.value)} value={typeFilter}>
          <option value="all">All types</option>
          {issueTypes.map((type) => <option key={type} value={type}>{labelize(type)}</option>)}
        </select>
        <button className={mode === "board" ? "segment active" : "segment"} onClick={() => setMode("board")} type="button">
          <LayoutGrid size={16} /> Board
        </button>
        <button className={mode === "queue" ? "segment active" : "segment"} onClick={() => setMode("queue")} type="button">
          <ListChecks size={16} /> Queue
        </button>
        <button className="primaryAction pushRight" disabled={filtered.length === 0} onClick={() => filtered[0] && onGeneratePlan(filtered[0])} type="button">
          <Play size={18} />
          Generate plan
        </button>
        <button className="ghostAction" disabled={filtered.length === 0} onClick={() => filtered[0] && onTriage(filtered[0])} type="button">
          <RefreshCcw size={18} />
          Run triage
        </button>
      </div>
      {mode === "board" ? (
        <div className="kanban">
          {issueColumns.map((column) => {
            const columnIssues = filtered.filter((issue) => issueColumn(issue) === column);
            return (
              <section className="kanbanColumn" key={column}>
                <h2>{columnLabel(column)} <span>{columnIssues.length}</span></h2>
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
                    <td><button className="rowAction" onClick={(event) => { event.stopPropagation(); void onGeneratePlan(issue); }} type="button">{nextIssueAction(issue)} <ChevronRight size={16} /></button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
          <aside className="panel summaryPanel">
            <h2>Issue Summary</h2>
            <SummaryItem icon={Bot} label="Agent-ready" value={filtered.filter((issue) => normalizedStatus(issue.status) === "agent_ready").length} tone="success" />
            <SummaryItem icon={Clock3} label="Awaiting approval" value={filtered.filter((issue) => issue.plan?.approval_status === "draft").length} tone="warning" />
            <SummaryItem icon={X} label="Blocked" value={filtered.filter((issue) => issueColumn(issue) === "blocked").length} tone="danger" />
            <SummaryItem icon={ShieldAlert} label="High risk" value={filtered.filter((issue) => issue.risk_score >= 70).length} tone="danger" />
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
  const riskNotes = stringList(plan.risk_notes);
  return (
    <div className="screen">
      <Breadcrumb trail={["Issues", `#${issue.number}`]} />
      <div className="titleRow">
        <ScreenHeader title={`#${issue.number} ${issue.title}`} subtitle={issue.repository ? `${issue.repository.owner}/${issue.repository.name}` : "Tracked GitHub issue"} />
        <Badge tone={statusTone(issue.plan?.approval_status ?? issue.status)}>{labelize(issue.plan?.approval_status ?? issue.status)}</Badge>
      </div>
      <div className="detailGrid">
        <section className="detailStack">
          <InfoPanel number="1" title="Original GitHub Issue">
            <p>{issue.title}</p>
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
          <InfoPanel number="3" title="Acceptance Criteria">
            <CheckList items={stringList(plan.acceptance_criteria)} empty="No acceptance criteria were captured in the current plan data." />
          </InfoPanel>
          <InfoPanel number="4" title="Retrieved Code Context">
            <PillList items={filesToInspect} empty="No retrieved files are attached to this issue yet." />
          </InfoPanel>
          <div className="threePanels">
            <InfoPanel number="5" title="Implementation Plan">
              <NumberedList items={filesToModify.length ? filesToModify : stringList(plan.steps)} empty="Generate a plan to populate implementation steps." />
            </InfoPanel>
            <InfoPanel number="6" title="Test Plan">
              <Bullets items={testsToAdd} empty="No test plan is attached yet." />
            </InfoPanel>
            <InfoPanel number="7" title="Security Notes">
              <Bullets items={riskNotes} empty="No security notes are attached yet." />
            </InfoPanel>
          </div>
        </section>
        <aside className="panel contextPanel">
          <Field label="Status" value={labelize(issue.plan?.approval_status ?? issue.status)} tone={statusTone(issue.plan?.approval_status ?? issue.status)} />
          <Field label="Risk" value={riskLabel(issue.risk_score)} tone={riskTone(issue.risk_score)} />
          <Field label="Run" value={issue.run ? shortId(issue.run.id) : "Unavailable"} />
          <Field label="Cost estimate" value={issue.run ? formatMoney(issue.run.total_cost) : "Unavailable"} />
          <Field label="Confidence" value={issue.run ? "From trace data" : "Unavailable"} />
          <button className="primaryAction wide" onClick={() => onApprove(issue)} disabled={!issue.plan} type="button">
            <Check size={20} />
            Approve Plan
          </button>
          <button className="ghostAction wide" onClick={() => onRevise(issue)} disabled={!issue.plan} type="button">
            <RotateCcw size={18} />
            Request Revision
          </button>
          <button className="ghostAction wide" onClick={() => onGeneratePlan(issue)} type="button">
            <RotateCcw size={18} />
            Generate New Plan
          </button>
          <button className="dangerAction wide" onClick={() => onReject(issue)} disabled={!issue.plan} type="button">
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
  query,
  onRun,
  onStart,
  onStop
}: {
  runs: RunSummary[];
  selectedRun: RunSummary | null;
  trace: TraceData | null;
  issues: IssueResponse[];
  query: string;
  onRun: (run: RunSummary, target?: View) => void;
  onStart: (run: RunSummary) => void;
  onStop: (run: RunSummary) => void;
}) {
  const filtered = filterRuns(runs, issues, query);
  const run = selectedRun ?? filtered[0] ?? null;
  const issue = run ? issues.find((item) => item.id === run.issue_id) : null;
  return (
    <div className="screen">
      <Breadcrumb trail={["Agent Runs", run ? shortId(run.id) : "No run"]} />
      <ScreenHeader title={run ? `Agent Run #${shortId(run.id)}` : "Agent Runs"} subtitle={issue ? `Issue #${issue.number} - ${issue.title}` : "Workflow execution state and evidence."} />
      <section className="statGrid five">
        <StatCard label="Status" value={run ? labelize(run.state) : "Unavailable"} icon={Clock3} />
        <StatCard label="Risk" value={issue ? riskLabel(issue.risk_score) : "Unavailable"} icon={ShieldAlert} />
        <StatCard label="Agents used" value={trace?.steps?.length ?? 0} icon={Bot} />
        <StatCard label="Runtime" value={run ? elapsed(run.started_at, run.completed_at) : "Unavailable"} icon={Clock3} />
        <StatCard label="Cost" value={run ? formatMoney(run.total_cost) : "Unavailable"} icon={KeyRound} />
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
              <button className="ghostAction" onClick={() => onStart(run)} type="button">Start</button>
              <button className="dangerAction" onClick={() => onStop(run)} type="button">Stop</button>
              <button className="primaryAction" onClick={() => onRun(run, "run-trace")} type="button">Open trace</button>
            </div>
          ) : null}
        </section>
        <aside className="panel contextPanel">
          <h2>Run Context</h2>
          <Field label="Current state" value={run ? run.state : "Unavailable"} mono />
          <Field label="Plan" value={run?.plan_id ? shortId(run.plan_id) : "Unavailable"} mono />
          <Field label="Pull request" value={trace?.pull_requests?.[0] ? `#${trace.pull_requests[0].number}` : "Unavailable"} />
          <Field label="Next action" value={nextRunAction(run?.state)} />
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
  const errors = steps.filter((step) => step.status === "failed").length;
  return (
    <div className="screen">
      <Breadcrumb trail={["Agent Runs", selectedRun ? shortId(selectedRun.id) : "Run", "Trace"]} />
      <ScreenHeader title={`Trace: ${selectedRun ? shortId(selectedRun.id) : "Unavailable"}`} subtitle="Detailed agent decisions, tool calls, latency, and outputs." />
      <section className="statGrid five">
        <StatCard label="Total tool calls" value={steps.length} icon={Wrench} />
        <StatCard label="LLM calls" value={llm.length} icon={Sparkles} />
        <StatCard label="Tokens" value={trace?.run?.total_tokens ?? selectedRun?.total_tokens ?? 0} icon={Database} />
        <StatCard label="Cost" value={formatMoney(trace?.run?.total_cost ?? selectedRun?.total_cost ?? 0)} icon={KeyRound} />
        <StatCard label="Errors" value={errors} icon={AlertTriangle} />
      </section>
      <div className="tabs">
        {["timeline", "tools", "prompts", "artifacts", "audit"].map((item) => (
          <button className={tab === item ? "tab active" : "tab"} key={item} onClick={() => setTab(item as typeof tab)} type="button">
            {labelize(item)}
          </button>
        ))}
      </div>
      <div className="sideGrid">
        <section className="panel tablePanel">
          <PanelHeader title={tab === "tools" ? "Tool Call Trace" : `${labelize(tab)} Trace`} />
          {tab === "tools" || tab === "timeline" ? (
            <table className="traceTable">
              <thead>
                <tr>
                  <th scope="col">Time</th>
                  <th scope="col">Agent</th>
                  <th scope="col">Tool</th>
                  <th scope="col">Output summary</th>
                  <th scope="col">Latency</th>
                  <th scope="col">Status</th>
                </tr>
              </thead>
              <tbody>
                {steps.map((step, index) => (
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
          {tab === "artifacts" ? <TraceJson items={[...(trace?.validation_results ?? []), ...(trace?.security_findings ?? [])]} /> : null}
          {tab === "audit" ? <TraceJson items={trace?.audit_events ?? []} /> : null}
        </section>
        <aside className="panel contextPanel">
          <h2>Tool Call Details</h2>
          {steps[0] ? (
            <>
              <Field label="Agent" value={agentName(steps[0].step_name)} />
              <Field label="Tool" value={steps[0].step_name.toLowerCase()} mono />
              <Field label="Output" value={summaryFromOutput(steps[0].output_json)} />
              <Field label="Latency" value={steps[0].latency_ms ? `${(steps[0].latency_ms / 1000).toFixed(1)}s` : "Unavailable"} />
              <Field label="Status" value={labelize(steps[0].status)} tone={statusTone(steps[0].status)} />
            </>
          ) : (
            <EmptyState text="Select a trace row after tool calls are recorded." />
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
  const filtered = prs.filter((pr) => {
    if (!searchable(`${pr.pr_number} ${pr.issue?.title ?? ""} ${pr.repository?.name ?? ""} ${pr.status}`, query)) return false;
    if (repositoryFilter !== "all" && pr.repository?.id !== repositoryFilter) return false;
    if (statusFilter !== "all" && pr.status !== statusFilter) return false;
    if (riskFilter !== "all" && riskBucket(pr.risk_score) !== riskFilter) return false;
    if (ciFilter === "passed" && !passedCi(pr.ci_status)) return false;
    if (ciFilter === "failed" && !failedCi(pr.ci_status)) return false;
    if (ciFilter === "unknown" && pr.ci_status) return false;
    if (securityFilter === "passed" && pr.security_findings.some((finding) => finding.status === "open")) return false;
    if (securityFilter === "open" && !pr.security_findings.some((finding) => finding.status === "open")) return false;
    return true;
  });
  return (
    <div className="screen">
      <ScreenHeader title="Pull Requests" subtitle="Draft PRs generated, monitored, or reviewed by RepoPilot AI." />
      <div className="toolbar fiveFilters">
        <select onChange={(event) => setRepositoryFilter(event.target.value)} value={repositoryFilter}>
          <option value="all">All repositories</option>
          {repositories.map((repo) => <option key={repo.id} value={repo.id}>{repo.owner}/{repo.name}</option>)}
        </select>
        <select onChange={(event) => setStatusFilter(event.target.value as PrStatusFilter)} value={statusFilter}>
          <option value="all">All statuses</option>
          <option value="draft">Draft</option>
          <option value="ready_for_review">Ready for review</option>
          <option value="blocked">Blocked</option>
        </select>
        <select onChange={(event) => setRiskFilter(event.target.value as IssueRiskFilter)} value={riskFilter}>
          <option value="all">All risks</option>
          <option value="low">Low risk</option>
          <option value="medium">Medium risk</option>
          <option value="high">High risk</option>
        </select>
        <select onChange={(event) => setCiFilter(event.target.value as PrCiFilter)} value={ciFilter}>
          <option value="all">All CI states</option>
          <option value="passed">CI passed</option>
          <option value="failed">CI failed</option>
          <option value="unknown">CI N/A</option>
        </select>
        <select onChange={(event) => setSecurityFilter(event.target.value as PrSecurityFilter)} value={securityFilter}>
          <option value="all">All security states</option>
          <option value="passed">No open findings</option>
          <option value="open">Open findings</option>
        </select>
      </div>
      <div className="sideGrid">
        <section className="panel tablePanel">
          <table className="prsTable">
            <thead>
              <tr>
                <th scope="col">PR</th>
                <th scope="col">Title</th>
                <th scope="col">Linked issue</th>
                <th scope="col">Status</th>
                <th scope="col">Risk</th>
                <th scope="col">CI</th>
                <th scope="col">Security</th>
                <th scope="col">Last updated</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((pr) => (
                <tr key={pr.pr_id} onClick={() => onPr(pr)} tabIndex={0} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onPr(pr); } }} role="row">
                  <td><span className="prNumberBadge mono">#{pr.pr_number}</span></td>
                  <td>{pr.issue?.title ?? `PR #${pr.pr_number}`}</td>
                  <td>{pr.issue ? `#${pr.issue.number}` : "Unavailable"}</td>
                  <td><Badge tone={statusTone(pr.status)}>{labelize(pr.status)}</Badge></td>
                  <td><Badge tone={riskTone(pr.risk_score)}>{riskLabel(pr.risk_score)}</Badge></td>
                  <td><Badge tone={statusTone(pr.ci_status ?? "unknown")}>{labelize(pr.ci_status ?? "unknown")}</Badge></td>
                  <td><Badge tone={securityTone(pr.security_findings)}>{securityLabel(pr.security_findings)}</Badge></td>
                  <td>{relativeTime(pr.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {filtered.length === 0 ? <EmptyState text="No pull requests are available yet." /> : null}
        </section>
        <aside className="panel summaryPanel">
          <h2>PR Summary</h2>
          <SummaryItem icon={FileText} label="Draft PRs" value={filtered.filter((pr) => pr.status === "draft").length} tone="violet" />
          <SummaryItem icon={Eye} label="Ready for review" value={filtered.filter((pr) => pr.status === "ready_for_review").length} tone="info" />
          <SummaryItem icon={X} label="Blocked" value={filtered.filter((pr) => pr.status === "blocked").length} tone="danger" />
          <SummaryItem icon={AlertCircle} label="CI failing" value={filtered.filter((pr) => pr.ci_status === "failed").length} tone="danger" />
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
  return (
    <div className="screen">
      <Breadcrumb trail={["Pull Requests", `#${pr.pr_number}`]} />
      <div className="titleRow">
        <ScreenHeader title={`PR #${pr.pr_number} ${pr.issue?.title ?? ""}`} subtitle="This pull request was generated by RepoPilot AI and is ready for human review." />
        <Badge tone={statusTone(pr.status)}>{labelize(pr.status)}</Badge>
        <Badge tone={riskTone(pr.risk_score)}>{riskLabel(pr.risk_score)}</Badge>
        <Badge tone={statusTone(pr.ci_status ?? "unknown")}>CI {labelize(pr.ci_status ?? "unknown")}</Badge>
        <Badge tone={securityTone(pr.security_findings)}>Security {securityLabel(pr.security_findings)}</Badge>
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
            <PillList items={pr.changed_files} empty="No changed files are attached to this PR record." />
          </InfoPanel>
          <InfoPanel number="4" title="Test Results">
            <div className="resultStrip">
              {pr.validation_results.map((result) => (
                <Field key={result.command} label={result.command} value={labelize(result.status)} tone={statusTone(result.status)} />
              ))}
              {pr.validation_results.length === 0 ? <EmptyState text="No validation results are recorded for this PR." /> : null}
            </div>
          </InfoPanel>
          <InfoPanel number="5" title="Security Results">
            <div className="resultStrip">
              {pr.security_findings.map((finding) => (
                <Field key={`${finding.tool}-${finding.description}`} label={finding.tool} value={labelize(finding.status)} tone={riskTone(severityScore(finding.severity))} />
              ))}
              {pr.security_findings.length === 0 ? <Field label="Security findings" value="None recorded" tone="success" /> : null}
            </div>
          </InfoPanel>
          <InfoPanel number="6" title="Rollback Notes">
            <p>{stringValue(pr.plan?.rollback_plan) || "No rollback plan is attached to this PR record."}</p>
          </InfoPanel>
          <button className="traceLink" onClick={() => onOpenRun(pr.run_id)} type="button">
            7. Agent Trace <span>View {shortId(pr.run_id)} <ExternalLink size={16} /></span>
          </button>
        </section>
        <aside className="panel contextPanel">
          <h2>Reviewer Checklist</h2>
          {reviewChecklist(pr).map((item) => (
            <label className="checkRow" key={item}>
              <input type="checkbox" />
              <span>{item}</span>
            </label>
          ))}
          <button className="dangerAction wide" onClick={() => onAnalyzeCi(pr)} type="button">
            <FileCode2 size={18} />
            Analyze CI logs
          </button>
          <button className="cyanAction wide" onClick={() => onRevisionPlan(pr)} type="button">
            <RotateCcw size={18} />
            Create CI revision plan
          </button>
          <button className="ghostAction wide" disabled title="No explanation endpoint is configured. Open the agent trace instead." type="button">
            <Sparkles size={18} />
            Explanation N/A
          </button>
          <button className="cyanAction wide" onClick={() => onSecurityReview(pr)} type="button">
            <Shield size={18} />
            Run security review
          </button>
          <button className="ghostAction wide" onClick={() => window.open(pr.url, "_blank", "noopener,noreferrer")} type="button">
            <Github size={18} />
            Open in GitHub
          </button>
        </aside>
      </div>
    </div>
  );
}

function CiDebuggerScreen({ pr, onAnalyzeCi }: { pr: PullRequestSummary | null; onAnalyzeCi: (pr: PullRequestSummary) => void }) {
  if (!pr) {
    return <EmptyState text="Select a pull request to debug CI." />;
  }
  const failed = pr.validation_results.find((result) => result.status !== "passed") ?? pr.validation_results[0] ?? null;
  return (
    <div className="screen">
      <Breadcrumb trail={["Pull Requests", `#${pr.pr_number}`, "CI Failure"]} />
      <ScreenHeader title="CI Failure Debugger" />
      <div className="failureBanner">
        <AlertTriangle size={26} />
        {failed ? `${failed.command} reported ${failed.status} on PR #${pr.pr_number}` : `No failing validation is recorded for PR #${pr.pr_number}`}
      </div>
      <section className="statGrid four">
        <StatCard label="Workflow" value="GitHub Actions" icon={GitBranch} />
        <StatCard label="Failed job" value={failed?.command ?? "Unavailable"} icon={ShieldAlert} />
        <StatCard label="Failed command" value={failed?.command ?? "Unavailable"} icon={Terminal} />
        <StatCard label="Status" value={failed ? labelize(failed.status) : "Unavailable"} icon={X} />
      </section>
      <div className="dashboardGrid">
        <section className="panel">
          <PanelHeader title="Failure Summary" />
          <InfoLine icon={AlertCircle} label="Root cause" value={failed?.parsed_summary ?? "No parsed failure summary is available."} />
          <InfoLine icon={AlertTriangle} label="Likely reason" value={failed?.command ?? "Unavailable"} />
          <InfoLine icon={Wrench} label="Suggested fix" value="Analyze the latest CI logs to produce a real suggested fix." />
        </section>
        <section className="panel">
          <PanelHeader title="Affected files" />
          <PillList items={pr.changed_files} empty="No affected files are attached to this PR record." />
        </section>
      </div>
      <section className="panel logPanel">
        <PanelHeader title="Log Preview" />
        <pre>{failed?.parsed_summary ?? "No CI log preview is available. Use Ask Agent to Propose Fix with pasted GitHub Actions logs."}</pre>
      </section>
      <div className="bottomActions">
        <button className="primaryAction" onClick={() => onAnalyzeCi(pr)} type="button"><Sparkles size={18} /> Ask Agent to Propose Fix</button>
        <span className="mutedText"><CheckCircle2 size={18} style={{ marginRight: 8 }} />Approve fix not available</span>
        <span className="mutedText"><X size={18} style={{ marginRight: 8 }} />Dismiss not available</span>
        <button className="ghostAction" onClick={() => window.open(pr.url, "_blank", "noopener,noreferrer")} type="button"><Github size={18} /> Open PR in GitHub</button>
      </div>
    </div>
  );
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
      <ScreenHeader title="Security" subtitle="Risk controls, blocked actions, and security findings from agent workflows." />
      <section className="statGrid six">
        <StatCard label="High-risk changes blocked" value={filtered.filter((finding) => severityScore(finding.severity) >= 70 && finding.status === "open").length} icon={ShieldAlert} />
        <StatCard label="Secrets detected" value={filtered.filter((finding) => finding.tool.toLowerCase().includes("secret")).length} icon={KeyRound} />
        <StatCard label="Dependency warnings" value={filtered.filter((finding) => finding.tool.toLowerCase().includes("dependency")).length} icon={AlertTriangle} />
        <StatCard label="CodeQL alerts" value={filtered.filter((finding) => finding.tool.toLowerCase().includes("codeql")).length} icon={Code2} />
        <StatCard label="Prompt injection attempts" value={filtered.filter((finding) => finding.tool.toLowerCase().includes("prompt")).length} icon={Shield} />
        <StatCard label="Workflow modifications blocked" value={filtered.filter((finding) => finding.file_path?.includes(".github/workflows")).length} icon={GitBranch} />
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
      <Breadcrumb trail={["Security", `Finding ${shortId(finding.id)}`]} />
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
            <button className="ghostAction wide" onClick={() => window.open(finding.pull_request?.url, "_blank", "noopener,noreferrer")} type="button">
              <Github size={18} /> Open in GitHub
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
  const bars = [
    ["Task pass rate", metricPercent(metrics.task_pass_rate)],
    ["PR creation success", metricPercent(metrics.patch_success_rate)],
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
        <ReadOnlyMeta label="Benchmark version" value={latest?.benchmark_version ?? "N/A"} />
        <ReadOnlyMeta label="Repository scope" value={repositories.length ? `${repositories.length} connected repos` : "N/A"} />
        <ReadOnlyMeta label="Agent version" value={latest ? "Current data snapshot" : "N/A"} />
      </div>
      <section className="statGrid seven">
        {bars.map(([label, value]) => <StatCard key={label} label={label} value={value.label} />)}
        <StatCard label="Avg runtime" value={averageRuntime(runs)} />
        <StatCard label="Avg cost/task" value={formatMoney(runs.length ? runs.reduce((sum, run) => sum + run.total_cost, 0) / runs.length : 0)} />
      </section>
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
  activities,
  riskFilter,
  selectedKey,
  setRiskFilter,
  setSelectedKey,
  setSourceFilter,
  setStatusFilter,
  sourceFilter,
  statusFilter
}: {
  activities: ActivityItem[];
  riskFilter: AuditRiskFilter;
  selectedKey: string;
  setRiskFilter: (filter: AuditRiskFilter) => void;
  setSelectedKey: (key: string) => void;
  setSourceFilter: (filter: string) => void;
  setStatusFilter: (filter: AuditStatusFilter) => void;
  sourceFilter: string;
  statusFilter: AuditStatusFilter;
}) {
  const sources = Array.from(new Set(activities.map((item) => item.source))).sort();
  const filtered = activities.filter((item) => {
    if (sourceFilter !== "all" && item.source !== sourceFilter) return false;
    if (statusFilter !== "all" && statusBucket(item.status) !== statusFilter) return false;
    if (riskFilter !== "all" && riskBucket(metadataRisk(item.metadata)) !== riskFilter) return false;
    return true;
  });
  const selected = filtered.find((item, index) => `${item.source}-${item.action}-${index}` === selectedKey) ?? filtered[0] ?? null;
  return (
    <div className="screen">
      <ScreenHeader title="Audit Logs" subtitle="Every human and agent action recorded for review." />
      <div className="toolbar fiveFilters">
        <select onChange={(event) => setSourceFilter(event.target.value)} value={sourceFilter}>
          <option value="all">All actors/sources</option>
          {sources.map((source) => <option key={source} value={source}>{labelize(source)}</option>)}
        </select>
        <select onChange={(event) => setStatusFilter(event.target.value as AuditStatusFilter)} value={statusFilter}>
          <option value="all">All results</option>
          <option value="success">Successful</option>
          <option value="warning">Pending/review</option>
          <option value="failed">Failed/blocked</option>
        </select>
        <select onChange={(event) => setRiskFilter(event.target.value as AuditRiskFilter)} value={riskFilter}>
          <option value="all">All risk levels</option>
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
              {filtered.map((item, index) => {
                const key = `${item.source}-${item.action}-${index}`;
                return (
                  <tr className={key === selectedKey ? "selected" : ""} key={key} onClick={() => setSelectedKey(key)} tabIndex={0} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setSelectedKey(key); } }} role="row">
                    <td>{formatClock(item.created_at)}</td>
                    <td>{labelize(item.source)}</td>
                    <td>{item.action}</td>
                    <td>{item.entity_id ? shortId(item.entity_id) : item.entity_type}</td>
                    <td><Badge tone={statusTone(item.status)}>{labelize(item.status)}</Badge></td>
                    <td><Badge tone={riskTone(metadataRisk(item.metadata))}>{riskLabel(metadataRisk(item.metadata))}</Badge></td>
                    <td><code>{item.entity_type === "agent_run" && item.entity_id ? shortId(item.entity_id) : "none"}</code></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {filtered.length === 0 ? <EmptyState text="No audit activity matches the current filters." /> : null}
        </section>
        <aside className="panel contextPanel">
          <h2>Selected log detail</h2>
          {selected ? (
            <>
              <Field label="Actor" value={labelize(selected.source)} />
              <Field label="Input" value={selected.entity_type} mono />
              <Field label="Output" value={selected.action} />
              <Field label="Policy" value={stringValue(selected.metadata.policy) || "Unavailable"} />
              <Field label="Status" value={labelize(selected.status)} tone={statusTone(selected.status)} />
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
  onGithub,
  onSaveGithubApp,
  onSaveGithubOAuth,
  onVerifyGithubApp,
  onSaveModelProvider,
  onVerifyModelProvider,
  policy,
  readiness,
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
  return (
    <div className="screen">
      <ScreenHeader title="Settings" subtitle="Configure GitHub access, models, approval policies, tools, and cost limits." />
      <div className="tabs">
        {settingsTabs.map((item) => (
          <button className={tab === item ? "tab active" : "tab"} key={item} onClick={() => setTab(item)} type="button">
            {item}
          </button>
        ))}
      </div>
      <div className="settingsGrid">
        {tab === "GitHub" && (
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

        {tab === "Policies" && (
          <>
            <section className="detailStack">
              <section className="panel settingsPanel">
                <h2>Human Approval Policies</h2>
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
                <strong>{readiness?.production_ready ? "Production ready" : "Local policy active"}</strong>
              </div>
              <p className="mutedText">Environment: {readiness?.environment ?? "Unavailable"}</p>
              <button className="primaryAction wide" onClick={onReset} type="button">
                <RefreshCcw size={18} />
                Refresh config
              </button>
            </aside>
          </>
        )}

        {tab === "Tool Permissions" && (
          <>
            <section className="detailStack">
              <section className="panel settingsPanel">
                <h2>Tool Permissions</h2>
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
                Refresh config
              </button>
            </aside>
          </>
        )}

        {tab === "Cost Limits" && (
          <>
            <section className="detailStack">
              <section className="panel settingsPanel">
                <h2>Cost Limits</h2>
                <KeyValue label="Max cost per issue" value="N/A" />
                <KeyValue label="Max commands without approval" value={String(policy?.max_commands_without_approval ?? "Unavailable")} />
                <KeyValue label="Max files changed without approval" value={String(policy?.max_files_changed_without_approval ?? "Unavailable")} />
              </section>
            </section>
            <aside className="panel contextPanel">
              <h2>Budget status</h2>
              <div className={policy ? "statusHero" : "statusHero warning"}>
                {policy ? <CheckCircle2 size={32} /> : <AlertTriangle size={32} />}
                <strong>{policy ? "Policy loaded" : "Policy N/A"}</strong>
              </div>
              <p className="mutedText">Environment: {readiness?.environment ?? "Unavailable"}</p>
              <button className="primaryAction wide" onClick={onReset} type="button">
                <RefreshCcw size={18} />
                Refresh config
              </button>
            </aside>
          </>
        )}

        {tab === "Models" && (
          <>
            <section className="detailStack">
              <ModelProviderForm
                catalog={data.modelCatalog}
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
              <Field label="Live verification" value={verification ? (verification.ok ? "Passed" : "Failed") : "Not run"} tone={verification?.ok ? "success" : verification ? "danger" : "warning"} />
              {verification ? <p className="mutedText">{verification.detail}</p> : null}
              <p className="mutedText">Environment: {readiness?.environment ?? "Unavailable"}</p>
              <button className="cyanAction wide" disabled={!data.modelConfig?.api_key_configured} onClick={() => void onVerifyModelProvider()} title={data.modelConfig?.api_key_configured ? "Calls the provider models endpoint with the saved key." : "Save a provider API key before verification."} type="button">
                <Sparkles size={18} />
                Verify provider
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

        {tab === "Notifications" && (
          <>
            <section className="detailStack">
              <section className="panel settingsPanel">
                <h2>Alert Channels</h2>
                <p className="mutedText" style={{ marginBottom: "16px" }}>No notification delivery endpoint or saved notification settings are present in this backend.</p>
                <KeyValue label="Slack" value="N/A" />
                <KeyValue label="Discord" value="N/A" />
                <KeyValue label="Email alerts" value="N/A" />
              </section>
              <section className="panel settingsPanel">
                <h2>Webhook Delivery</h2>
                <KeyValue label="Target URL" value="N/A" />
                <KeyValue label="Secret token" value="N/A" />
              </section>
            </section>
            <aside className="panel contextPanel">
              <h2>Alerts status</h2>
              <div className="statusHero warning">
                <AlertTriangle size={32} />
                <strong>Notifications N/A</strong>
              </div>
              <p className="mutedText">No notification configuration endpoint is available.</p>
              <button className="primaryAction wide" onClick={onReset} type="button">
                <RefreshCcw size={18} />
                Refresh status
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
  config,
  draft,
  onSave,
  setDraft
}: {
  catalog: ModelCatalogResponse | null;
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
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pricingLabel = (model: ModelCatalogModel): string | null => {
    if (!model.pricing) {
      return null;
    }
    const prompt = model.pricing.prompt;
    const completion = model.pricing.completion;
    if (!prompt && !completion) {
      return null;
    }
    return `Prompt ${prompt ?? "?"} | Completion ${completion ?? "?"}`;
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
    return (
      <section className="panel settingsPanel">
        <h2>Inference providers</h2>
        <EmptyState text="The model provider catalog is unavailable." />
      </section>
    );
  }

  return (
    <form className="panel modelProviderPanel" onSubmit={(event) => void submit(event)}>
      <div className="secretFormHeader">
        <span className="githubSyncIcon"><Sparkles size={24} /></span>
        <span>
          <h2>Inference provider</h2>
          <p>Select a real provider model from the verified catalog. API keys are write-only and saved in encrypted local storage.</p>
        </span>
        <Badge tone={config?.status === "configured" ? "success" : "warning"}>{config?.status === "configured" ? "Configured" : "API key required"}</Badge>
      </div>

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
          placeholder={config?.api_key_configured ? "Already configured; enter a new key to rotate" : "Paste provider API key"}
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

      <div className="modelOptionsTable">
        {(provider?.models ?? []).map((model) => (
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
      </div>

      <div className="securityNotes">
        <InfoLine icon={Database} label="Verified catalog" value="Provider and model IDs are served by the backend catalog instead of display-only UI state." />
        <InfoLine icon={KeyRound} label="Write-only key" value="API keys are never returned to the browser after saving." />
        <InfoLine icon={Shield} label="Encrypted storage" value="Provider settings and keys are saved through the runtime secret store." />
      </div>

      {error ? <div className="connectNotice">{error}</div> : null}
      <div className="panelActions">
        <button className="primaryAction" disabled={isSaving} type="submit">
          <Save size={18} />
          {isSaving ? "Saving..." : "Save model provider"}
        </button>
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
  const [form, setForm] = useState<GitHubOAuthConfigPayload>({
    github_client_id: "",
    github_client_secret: "",
    session_secret_key: "",
    github_oauth_callback_url: "http://localhost:8000/auth/github/callback",
    web_app_url: "http://127.0.0.1:3001",
    github_api_base_url: "https://api.github.com",
    github_web_base_url: "https://github.com"
  });
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function updateField(field: keyof GitHubOAuthConfigPayload, value: string) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsSaving(true);
    try {
      await onSave(form);
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

function SecretInput({
  action,
  label,
  name,
  onChange,
  placeholder,
  secret,
  value
}: {
  action?: React.ReactNode;
  label: string;
  name: string;
  onChange: (value: string) => void;
  placeholder: string;
  secret?: boolean;
  value: string;
}) {
  return (
    <label className="secretInput">
      <span>{label}</span>
      <div>
        <input
          autoCapitalize="none"
          autoComplete="off"
          autoCorrect="off"
          name={name}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          spellCheck={false}
          type={secret ? "password" : "text"}
          value={value}
        />
        {action}
      </div>
    </label>
  );
}

function ProfileScreen({ data, onGithub }: { data: ConsoleState; onGithub: () => void }) {
  const username = data.session?.username ?? "Platform Admin";
  const githubConnected = isGithubAccountConnected(data);
  return (
    <div className="screen">
      <ScreenHeader title="Profile" subtitle="Manage your RepoPilot workspace preferences." />
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
            <SummaryItem icon={FileText} label="Plans approved" value={data.activities.filter((item) => item.action.includes("plan.approved")).length} tone="info" />
            <SummaryItem icon={GitBranch} label="PRs reviewed" value={data.pullRequests.length} tone="violet" />
            <SummaryItem icon={Play} label="Agent runs started" value={data.runs.length} tone="info" />
            <SummaryItem icon={Shield} label="Security overrides" value={data.securityFindings.filter((item) => item.status !== "open").length} tone="warning" />
          </div>
        </section>
        <section className="panel profilePanel">
          <h2>Preferences</h2>
          <KeyValue label="Compact mode" value="N/A" />
          <KeyValue label="Email notifications" value="N/A" />
          <KeyValue label="GitHub comment notifications" value="N/A" />
          <KeyValue label="Weekly evaluation report" value="N/A" />
        </section>
        <section className="panel profilePanel">
          <h2>API and access</h2>
          <KeyValue icon={KeyRound} label="Personal API tokens" value="None created" />
          <KeyValue icon={Github} label="GitHub OAuth session" value={githubConnected ? "Active" : "Not connected"} />
          <KeyValue icon={Database} label="Imported GitHub accounts" value={String(data.installations.length)} />
          <button className="ghostAction wide" onClick={onGithub} type="button"><Github size={18} /> Manage GitHub access</button>
        </section>
        <section className="panel profilePanel dangerZone">
          <h2>Danger zone</h2>
          <button className="dangerAction" disabled type="button">Revoke access unavailable</button>
          <button className="dangerAction" disabled type="button">Delete data unavailable</button>
        </section>
      </div>
    </div>
  );
}

function LogoMark() {
  return (
    <span className="logoMark" aria-hidden="true">
      <Shield size={25} />
    </span>
  );
}

function ScreenHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="screenHeader">
      <h1>{title}</h1>
      {subtitle ? <p>{subtitle}</p> : null}
    </div>
  );
}

function PanelHeader({ title, icon: Icon }: { title: string; icon?: LucideIcon }) {
  return (
    <header className="panelHeader">
      <h2>{Icon ? <Icon size={22} /> : null}{title}</h2>
    </header>
  );
}

function StatCard({ label, value, icon: Icon }: { label: string; value: string | number; icon?: LucideIcon }) {
  return (
    <article className="statCard">
      {Icon ? <Icon size={28} /> : null}
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function MetaCard({ icon: Icon, label, value, mono, tone }: { icon: LucideIcon; label: string; value: string; mono?: boolean; tone?: string }) {
  return (
    <article className="metaCard">
      <Icon size={22} />
      <span>{label}</span>
      {tone ? <Badge tone={tone}>{value}</Badge> : <strong className={mono ? "mono" : ""}>{value}</strong>}
    </article>
  );
}

function Badge({ children, tone = "neutral" }: { children: React.ReactNode; tone?: string }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}

function Segment({
  active,
  disabled,
  label,
  onClick
}: {
  active?: boolean;
  disabled?: boolean;
  label: string;
  onClick?: () => void;
}) {
  return <button className={active ? "segment active" : "segment"} disabled={disabled} onClick={onClick} type="button">{label}</button>;
}

function SummaryItem({ icon: Icon, label, value, tone }: { icon: LucideIcon; label: string; value: string | number; tone: string }) {
  return (
    <div className="summaryItem">
      <span className={`summaryIcon ${tone}`}><Icon size={24} /></span>
      <span><small>{label}</small><strong>{value}</strong></span>
      <ChevronRight size={18} />
    </div>
  );
}

function Field({ label, value, tone, mono }: { label: string; value: string; tone?: string; mono?: boolean }) {
  return (
    <div className="field">
      <small>{label}</small>
      {tone ? <Badge tone={tone}>{value}</Badge> : <strong className={mono ? "mono" : ""}>{value}</strong>}
    </div>
  );
}

function InfoPanel({ number, title, children }: { number: string; title: string; children: React.ReactNode }) {
  return (
    <section className="panel infoPanel">
      <h2><span>{number}.</span> {title}</h2>
      {children}
    </section>
  );
}

function Breadcrumb({ trail }: { trail: string[] }) {
  return <div className="breadcrumb">{trail.map((item, index) => <span key={`${item}-${index}`}>{item}</span>)}</div>;
}

function CheckList({ items, empty }: { items: string[]; empty: string }) {
  if (items.length === 0) {
    return <EmptyState text={empty} />;
  }
  return <div className="checkList">{items.map((item) => <span key={item}><CheckCircle2 size={19} /> {item}</span>)}</div>;
}

function PillList({ items, empty }: { items: string[]; empty: string }) {
  if (items.length === 0) {
    return <EmptyState text={empty} />;
  }
  return <div className="pillList">{items.map((item) => <code key={item}>{item}</code>)}</div>;
}

function NumberedList({ items, empty }: { items: string[]; empty: string }) {
  if (items.length === 0) {
    return <EmptyState text={empty} />;
  }
  return <ol className="numberedList">{items.map((item) => <li key={item}>{item}</li>)}</ol>;
}

function Bullets({ items, empty = "No entries recorded." }: { items: string[]; empty?: string }) {
  if (items.length === 0) {
    return <EmptyState text={empty} />;
  }
  return <ul className="bullets">{items.map((item) => <li key={item}>{item}</li>)}</ul>;
}

function EmptyState({ text }: { text: string }) {
  return <p className="emptyState">{text}</p>;
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

function RiskRows({ risk, onSecurity }: { risk: ReturnType<typeof riskCounts>; onSecurity: () => void }) {
  const total = Math.max(1, risk.low + risk.medium + risk.high + risk.blocked);
  const rows = [
    ["Low risk", risk.low, "success"],
    ["Medium risk", risk.medium, "warning"],
    ["High risk", risk.high, "danger"],
    ["Blocked", risk.blocked, "danger"]
  ] as const;
  return (
    <div className="riskRows">
      {rows.map(([label, value, tone]) => (
        <div className="riskRow" key={label}>
          <span><i className={tone} /> {label}</span>
          <div className="miniBar"><span className={tone} style={{ width: `${(value / total) * 100}%` }} /></div>
          <strong>{value}</strong>
        </div>
      ))}
      <button className="panelLink" onClick={onSecurity} type="button">View full risk report <ChevronRight size={16} /></button>
    </div>
  );
}

function PolicyToggle({ label, enabled }: { label: string; enabled: boolean }) {
  return (
    <div className="policyToggle">
      <span>{label}</span>
      <Badge tone={enabled ? "success" : "neutral"}>{enabled ? "Enabled" : "Disabled"}</Badge>
    </div>
  );
}

function Threshold({ label, value, tone }: { label: string; value: string; tone: string }) {
  return <div className="threshold"><span>{label}</span><Badge tone={tone}>{value}</Badge></div>;
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

function KeyValue({ label, value, icon: Icon }: { label: string; value: string; icon?: LucideIcon }) {
  return <div className="keyValue">{Icon ? <Icon size={20} /> : null}<span>{label}</span><strong>{value}</strong></div>;
}

function ReadOnlyMeta({ label, value }: { label: string; value: string }) {
  return <div className="reportMetaItem"><span>{label}</span><strong>{value}</strong></div>;
}

function InfoLine({ icon: Icon, label, value }: { icon: LucideIcon; label: string; value: string }) {
  return (
    <div className="infoLine">
      <Icon size={24} />
      <span><strong>{label}</strong><small>{value}</small></span>
    </div>
  );
}

function TraceJson({ items }: { items: Array<Record<string, unknown>> }) {
  if (items.length === 0) {
    return <EmptyState text="No records are available for this tab." />;
  }
  return <pre className="jsonBlock">{JSON.stringify(items, null, 2)}</pre>;
}

function BarChart({ metrics }: { metrics: Record<string, unknown> }) {
  const data = [
    ["Docs", metricPercent(metrics.docs_success_rate).value],
    ["Tests", metricPercent(metrics.tests_success_rate).value],
    ["Bug", metricPercent(metrics.bug_success_rate).value],
    ["Refactor", metricPercent(metrics.refactor_success_rate).value],
    ["API", metricPercent(metrics.api_success_rate).value],
    ["Security", metricPercent(metrics.security_success_rate).value]
  ];
  if (data.every(([, value]) => value === 0)) {
    return <EmptyState text="No issue-type success metrics are present in the latest eval report." />;
  }
  return (
    <div className="barChart">
      {data.map(([label, value]) => (
        <div className="barColumn" key={label as string}>
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

function parseHash(hash: string): View {
  const value = hash.replace("#", "").split("?")[0].split("/")[0] as View;
  const views: View[] = ["landing", "connect", "setup", "dashboard", "repositories", "repository-detail", "issues", "issue-detail", "agent-runs", "run-trace", "pull-requests", "pull-request-detail", "ci-debugger", "security", "security-detail", "evaluations", "audit-logs", "settings", "profile"];
  return views.includes(value) ? value : "dashboard";
}

function parseSettingsTab(hash: string): SettingsTab | null {
  const cleanHash = hash.replace("#", "").split("?")[0];
  const [, rawTab] = cleanHash.split("/");
  if (!rawTab) {
    return cleanHash === "settings" ? "GitHub" : null;
  }
  const normalized = rawTab.replace(/-/g, " ").toLowerCase();
  if (normalized === "policy") {
    return "Policies";
  }
  return settingsTabs.find((tab) => tab.toLowerCase() === normalized) ?? null;
}

function settingsHash(tab: SettingsTab) {
  return `settings/${tab.toLowerCase().replace(/\s+/g, "-")}`;
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
    config?.api_key_configured ? "api-key" : "no-api-key"
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
  const required = ["GITHUB_CLIENT_ID", "GITHUB_CLIENT_SECRET", "GITHUB_OAUTH_CALLBACK_URL", "WEB_APP_URL", "SESSION_SECRET_KEY"];
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
  if (item === "pull-requests") return view === item || view === "pull-request-detail" || view === "ci-debugger";
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
  if (issue.plan?.approval_status === "draft") return "wait_for_approval";
  if (status.includes("blocked") || status.includes("rejected")) return "blocked";
  if (status.includes("planning") || issue.run?.state === "GENERATE_PLAN") return "planning";
  if (status.includes("progress") || issue.run?.state === "IMPLEMENT_PATCH") return "in_progress";
  if (status.includes("pr")) return "pr_opened";
  if (status === "agent_ready") return "agent_ready";
  if (status === "wait_for_approval") return "wait_for_approval";
  return "needs_info";
}

function columnLabel(column: string) {
  const labels: Record<string, string> = {
    needs_info: "Needs Info",
    agent_ready: "Agent Ready",
    planning: "Planning",
    wait_for_approval: "Awaiting Approval",
    in_progress: "In Progress",
    pr_opened: "PR Opened",
    blocked: "Blocked"
  };
  return labels[column] ?? labelize(column);
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
  if (["passed", "success", "succeeded", "ready_for_review", "open", "approved", "agent_ready", "fixed", "configured", "verified"].some((item) => lowered.includes(item)) && !lowered.includes("unverified")) return "success";
  if (["waiting", "pending", "draft", "progress", "review", "approval", "queued", "unverified", "placeholder", "disabled"].some((item) => lowered.includes(item))) return "warning";
  if (["failed", "blocked", "rejected", "error", "critical", "missing"].some((item) => lowered.includes(item))) return "danger";
  if (["running", "ci", "plan"].some((item) => lowered.includes(item))) return "info";
  return "neutral";
}

function securityTone(findings: PullRequestSummary["security_findings"]) {
  if (findings.some((finding) => finding.status === "open" && severityScore(finding.severity) >= 70)) return "danger";
  if (findings.some((finding) => finding.status === "open")) return "warning";
  return "success";
}

function securityLabel(findings: PullRequestSummary["security_findings"]) {
  if (findings.length === 0) return "Passed";
  const open = findings.filter((finding) => finding.status === "open");
  if (open.length === 0) return "Passed";
  return `${open.length} open`;
}

function labelize(value: string) {
  return value.replace(/[_-]/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function shortId(value: string) {
  return value.slice(0, 8);
}

function formatMoney(value: number) {
  return `₹${Math.round(value * 100) / 100}`;
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

function relativeTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unavailable";
  const minutes = Math.max(0, Math.round((Date.now() - date.getTime()) / 60000));
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

function elapsed(start: string, end: string | null) {
  const startTime = new Date(start).getTime();
  const endTime = end ? new Date(end).getTime() : Date.now();
  if (Number.isNaN(startTime) || Number.isNaN(endTime)) return "Unavailable";
  const seconds = Math.max(0, Math.round((endTime - startTime) / 1000));
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ${seconds % 60}s`;
}

function averageRuntime(runs: RunSummary[]) {
  if (runs.length === 0) return "Unavailable";
  const completed = runs.map((run) => {
    const start = new Date(run.started_at).getTime();
    const end = run.completed_at ? new Date(run.completed_at).getTime() : Date.now();
    return Number.isNaN(start) || Number.isNaN(end) ? 0 : end - start;
  });
  const seconds = Math.round(completed.reduce((sum, value) => sum + value, 0) / Math.max(1, completed.length) / 1000);
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

function initials(value: string) {
  const parts = value.split(/[\s._-]+/).filter(Boolean);
  return (parts[0]?.[0] ?? "P").toUpperCase() + (parts[1]?.[0] ?? parts[0]?.[1] ?? "A").toUpperCase();
}

function workspaceLabel(installations: InstallationResponse[]) {
  return installations[0]?.account_name ?? "Platform Admin";
}

function lastIndexedLabel(repos: RepositoryResponse[]) {
  const indexed = repos.find((repo) => repo.last_indexed_sha);
  return indexed ? indexed.last_indexed_sha?.slice(0, 7) ?? "Indexed" : "Never";
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
  return status === "passed" || status === "success" || status === "succeeded";
}

function failedCi(status: string | null) {
  return status === "failed" || status === "failure" || status === "error";
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
  return "warning";
}

function latestValidation(pr: PullRequestSummary) {
  return pr.validation_results[0] ?? null;
}

function nextIssueAction(issue: IssueResponse) {
  if (!issue.plan) return "Generate plan";
  if (issue.plan.approval_status === "draft") return "Approve plan";
  if (issue.run) return nextRunAction(issue.run.state);
  return "Review issue";
}

function nextRunAction(state?: string) {
  if (!state) return "Unavailable";
  const index = stateOrder.indexOf(state);
  if (index < 0 || index === stateOrder.length - 1) return "Review evidence";
  return labelize(stateOrder[index + 1]);
}

function agentName(stepName: string) {
  const step = stepName.toLowerCase();
  if (step.includes("triage")) return "Triage Agent";
  if (step.includes("context") || step.includes("retrieve")) return "Context Agent";
  if (step.includes("plan")) return "Planning Agent";
  if (step.includes("security")) return "Security Agent";
  if (step.includes("test") || step.includes("validation")) return "Test Agent";
  if (step.includes("pr")) return "PR Agent";
  if (step.includes("ci")) return "CI Agent";
  return "Execution Agent";
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

function maybeOpenActivity(item: ActivityItem, data: ConsoleState, onIssue: (issue: IssueResponse) => void, onRun: (run: RunSummary) => void) {
  if (item.entity_type === "issue" && item.entity_id) {
    const issue = data.issues.find((candidate) => candidate.id === item.entity_id);
    if (issue) onIssue(issue);
  }
  if (item.entity_type === "agent_run" && item.entity_id) {
    const run = data.runs.find((candidate) => candidate.id === item.entity_id);
    if (run) onRun(run);
  }
}

function metadataRisk(metadata: Record<string, unknown>) {
  const risk = metadata.risk_score;
  return typeof risk === "number" ? risk : 0;
}

function stringList(value: unknown) {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function stringValue(value: unknown) {
  return typeof value === "string" ? value : "";
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

function reviewChecklist(pr: PullRequestSummary) {
  const files = pr.changed_files;
  const checks = ["Confirm implementation matches linked issue"];
  if (files.some((file) => file.includes("auth"))) checks.push("Confirm token expiry policy");
  if (files.some((file) => file.includes(".github/workflows"))) checks.push("Confirm workflow permission changes");
  if (pr.validation_results.length) checks.push("Confirm validation results");
  if (pr.security_findings.length) checks.push("Confirm security findings");
  checks.push("Confirm rollback notes are acceptable");
  return checks.slice(0, 5);
}
