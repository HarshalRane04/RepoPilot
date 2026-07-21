export type SessionResponse = {
  username: string;
  role: string;
  mode: string;
  github_user_id?: string | null;
  email?: string | null;
};

export type RepositoryResponse = {
  id: string;
  canonical_id?: string;
  alias_ids?: string[];
  installation_id?: string;
  installation_ids?: string[];
  source_mode?: "github_app" | "oauth_discovery";
  source_modes?: Array<"github_app" | "oauth_discovery">;
  acquirable?: boolean;
  owner: string;
  name: string;
  default_branch: string;
  last_indexed_sha: string | null;
  issue_count: number;
  index_id?: string | null;
  index_status?: string | null;
  indexed_at?: string | null;
  content_fingerprint?: string | null;
  chunker_version?: string | null;
  indexed_file_count?: number;
  code_chunk_count?: number;
  test_file_count?: number;
  language?: string | null;
  framework?: string | null;
  embedding_provider?: string | null;
  embedding_model?: string | null;
  embedding_dimensions?: number | null;
  index_stale?: boolean;
};

export type ActivityItem = {
  source: string;
  action: string;
  status: string;
  created_at: string;
  entity_type: string;
  entity_id: string | null;
  metadata: Record<string, unknown>;
};

export type AuditLogItem = {
  id: string;
  actor_type: "user" | "agent" | "system" | "github";
  actor_id: string | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  result: string;
  risk_score: number | null;
  created_at: string;
  metadata: Record<string, unknown>;
};

export type AuditLogPage = {
  items: AuditLogItem[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
  is_complete: boolean;
};

export type ActivitySummaryResponse = {
  plans_approved: number;
  pull_request_records: number;
  agent_runs: number;
  reviewed_security_findings: number;
};

export type RunSummary = {
  id: string;
  issue_id: string | null;
  plan_id: string | null;
  state: string;
  model_used: string | null;
  total_tokens: number;
  total_cost: number;
  cost_currency?: "USD";
  started_at: string;
  completed_at: string | null;
  latest_step: string | null;
  latest_step_status: string | null;
  validation_statuses: string[];
};

export type AgentRunDetailResponse = {
  id: string;
  issue_id: string | null;
  plan_id: string | null;
  state: string;
  model_used: string | null;
  total_tokens: number;
  total_cost: number;
  cost_currency?: "USD";
  started_at: string;
  completed_at: string | null;
  steps: Array<{
    id: string;
    step_name: string;
    status: string;
    output_json: Record<string, unknown> | null;
    error: string | null;
    created_at: string;
  }>;
  validation_results: Array<{
    id: string;
    command: string;
    status: string;
    duration_ms: number | null;
    parsed_summary: string | null;
    log_uri?: string | null;
    evidence_hash?: string | null;
    patch_hash?: string | null;
    sandbox_backend?: string | null;
  }>;
};

export type EvalReport = {
  id: string;
  benchmark_version: string;
  metrics: Record<string, unknown>;
  report_uri: string | null;
  created_at: string;
};

export type IntegrationStatus = {
  name: string;
  state: "configured" | "verified" | "unverified" | "placeholder" | "missing" | "disabled";
  mode?: string | null;
  required_for_production: boolean;
  detail: string;
  next_step: string;
};

export type ReadinessResponse = {
  environment: string;
  release_profile: string;
  production_ready: boolean;
  github_writes_enabled: boolean;
  local_record_mode: boolean;
  github_mode: string;
  model_mode: string;
  integrations: IntegrationStatus[];
  blockers: string[];
  warnings: string[];
};

export type InstallationResponse = {
  id: string;
  canonical_id?: string;
  alias_ids?: string[];
  github_installation_id: string;
  github_installation_ids?: string[];
  account_name: string;
  repository_count: number;
  created_at: string;
  source_mode?: "github_app" | "oauth_discovery";
  source_modes?: Array<"github_app" | "oauth_discovery">;
};

export type IssueResponse = {
  id: string;
  repository_id: string;
  number: number;
  title: string;
  body_text?: string | null;
  issue_type: string | null;
  complexity: string | null;
  risk_score: number;
  status: string;
  created_at: string;
  repository?: Pick<RepositoryResponse, "id" | "owner" | "name" | "default_branch" | "last_indexed_sha">;
  plan?: {
    id: string;
    approval_status: string;
    version: number;
    approved_at: string | null;
    plan: ImplementationPlanPayload;
  };
  run?: {
    id: string;
    state: string;
    total_tokens: number;
    total_cost: number;
    cost_currency?: "USD";
    started_at: string;
    completed_at: string | null;
  };
};

export type ImplementationPlanPayload = {
  summary?: string | null;
  files_to_inspect?: string[];
  files_to_modify?: string[];
  tests_to_add?: string[];
  commands_to_run?: string[];
  intended_changes?: string[];
  validation_strategy?: string[];
  assumptions?: string[];
  context_citations?: string[];
  risk_notes?: string[];
  rollback_plan?: string | null;
  policy_decision?: unknown;
  approval_policy_decision?: unknown;
  requires_human_approval?: boolean;
  plan_hash?: string | null;
  approved_plan_hash?: string | null;
  [key: string]: unknown;
};

export type PromptSubmitPayload = {
  repository_id?: string;
  title: string;
  prompt: string;
  auto_plan: boolean;
};

export type PromptSubmitResponse = {
  status: string;
  issue: {
    id: string;
    number: number;
    title: string;
    status: string;
    risk_score: number;
    issue_type: string | null;
  };
  run: {
    id: string;
    state: string;
  };
  plan: {
    plan_id: string;
    run_id: string;
    plan: ImplementationPlanPayload;
  } | null;
};

export type PullRequestSummary = {
  pr_id: string;
  run_id: string;
  pr_number: number;
  url: string;
  pr_mode: "local_record" | "real_github";
  is_local_record: boolean;
  github_url: string | null;
  status: string;
  ci_status: string | null;
  risk_score: number;
  created_at: string;
  issue: {
    id: string;
    number: number;
    title: string;
    status: string;
  } | null;
  repository: {
    id: string;
    owner: string;
    name: string;
    default_branch: string;
  } | null;
  plan: {
    id: string;
    approval_status: string;
    summary?: unknown;
    rollback_plan?: unknown;
    files_to_modify: string[];
    tests_to_add: string[];
    risk_notes: string[];
  } | null;
  current_patch_hash: string | null;
  changed_files: string[];
  planned_files: string[];
  validation_results: Array<{
    command: string;
    status: string;
    duration_ms: number | null;
    parsed_summary: string | null;
    log_uri?: string | null;
    evidence_hash?: string | null;
    patch_hash?: string | null;
    sandbox_backend?: string | null;
  }>;
  validation_evidence?: {
    status: "not_run" | "pending" | "passed" | "failed" | "incomplete" | "unknown";
    patch_hash: string | null;
    total: number;
    passed: number;
    failed: number;
    pending: number;
    incomplete: number;
  };
  security_findings: Array<{
    tool: string;
    severity: string;
    file_path: string | null;
    description: string;
    status: string;
    status_reason?: string | null;
    patch_hash?: string | null;
  }>;
  security_scan?: {
    status: "not_run" | "pending" | "passed" | "failed" | "incomplete" | "unknown";
    completed: boolean;
    patch_hash: string | null;
    finding_count: number;
    scanned_files: number | null;
    completed_at: string | null;
    sources: string[];
  };
};

export type SecurityFindingResponse = {
  id: string;
  run_id: string;
  tool: string;
  severity: string;
  file_path: string | null;
  description: string;
  status: string;
  status_reason?: string | null;
  status_actor?: string | null;
  status_changed_at?: string | null;
  run: {
    id: string;
    state: string;
    started_at: string;
    completed_at: string | null;
  } | null;
  issue: {
    id: string;
    number: number;
    title: string;
    status: string;
  } | null;
  repository: {
    id: string;
    owner: string;
    name: string;
  } | null;
  pull_request: {
    id: string;
    number: number;
    url: string;
    pr_mode: "local_record" | "real_github";
    is_local_record: boolean;
    github_url: string | null;
    status: string;
    ci_status: string | null;
  } | null;
};

export type PolicyResponse = {
  max_files_changed_without_approval: number;
  max_commands_without_approval: number;
  high_risk_patterns: string[];
  allowed_commands: string[];
  blocked_command_fragments: string[];
  max_cost_per_run: number;
  cost_currency: "USD";
};

export type GitHubLoginResponse = {
  status: string;
  authorize_url: string | null;
  next_step: string;
};

export type GitHubOAuthConfigField = {
  name: string;
  configured: boolean;
  secret: boolean;
  source: "environment" | "encrypted_store";
};

export type GitHubOAuthConfigStatus = {
  fields: GitHubOAuthConfigField[];
  encrypted: boolean;
  store_exists: boolean;
  key_source: string;
  store_permissions_ok: boolean;
  key_permissions_ok: boolean;
  updated_at: string | null;
};

export type GitHubAppConfigStatus = GitHubOAuthConfigStatus;

export type GitHubAppVerificationResponse = {
  ok: boolean;
  status: string;
  checked_at: string;
  installation_id: string;
  token_received: boolean;
  detail: string;
};

export type ModelCatalogModel = {
  id: string;
  name: string;
  context_window: string;
  capabilities: string[];
  reasoning_levels: string[];
  is_free?: boolean;
  pricing?: Partial<Record<"prompt" | "completion" | "request" | "image" | "web_search", string>>;
  pricing_currency?: "USD";
  pricing_unit?: "token";
};

export type ModelCatalogProvider = {
  id: string;
  name: string;
  description: string;
  api_key_env: string;
  default_base_url: string;
  docs_url: string;
  models: ModelCatalogModel[];
};

export type ModelCatalogResponse = {
  providers: ModelCatalogProvider[];
};

export type ModelProviderConfigStatus = {
  provider: string;
  provider_name: string;
  model: string;
  model_configured: boolean;
  api_key_configured: boolean;
  configured_api_key_providers: string[];
  base_url: string | null;
  reasoning_level: string | null;
  reasoning_levels: string[];
  reasoning_supported: boolean;
  docs_url: string | null;
  verified: boolean;
  verified_at: string | null;
  status: "configured" | "missing" | "unavailable";
  catalog_available: boolean;
  summary: GitHubOAuthConfigStatus;
};

export type ModelProviderVerificationResponse = {
  ok: boolean;
  provider: string;
  model: string;
  detail: string;
  checked_at: string;
  latency_ms: number;
};

export type OperatorData = {
  session: SessionResponse | null;
  repositories: RepositoryResponse[];
  installations: InstallationResponse[];
  issues: IssueResponse[];
  pullRequests: PullRequestSummary[];
  securityFindings: SecurityFindingResponse[];
  activities: ActivityItem[];
  auditLogPage: AuditLogPage | null;
  activitySummary: ActivitySummaryResponse | null;
  runs: RunSummary[];
  evalReports: EvalReport[];
  readiness: ReadinessResponse | null;
  policy: PolicyResponse | null;
  githubOAuthConfig: GitHubOAuthConfigStatus | null;
  githubAppConfig: GitHubAppConfigStatus | null;
  modelCatalog: ModelCatalogResponse | null;
  modelConfig: ModelProviderConfigStatus | null;
};

export const INITIAL_DASHBOARD_REQUEST_PATHS = {
  session: "/auth/session",
  repositories: "/repos",
  installations: "/installations",
  issues: "/issues?limit=300",
  pullRequests: "/prs?limit=200",
  securityFindings: "/security/findings?limit=300",
  activities: "/activity?limit=20",
  activitySummary: "/activity/summary",
  runs: "/runs?limit=80",
  evalReports: "/evals/reports",
  readiness: "/settings/readiness",
  policy: "/settings/policy",
  githubOAuthConfig: "/settings/github/oauth",
  githubAppConfig: "/settings/github/app",
  modelConfig: "/settings/models/config"
} as const;

export async function getDashboardData(cookieHeader?: string): Promise<OperatorData> {
  const [
    session,
    repositories,
    installations,
    issues,
    pullRequests,
    securityFindings,
    activities,
    activitySummary,
    runs,
    evals,
    readiness,
    policy,
    githubOAuthConfig,
    githubAppConfig,
    modelConfig
  ] = await Promise.all([
    safeFetch<SessionResponse>(INITIAL_DASHBOARD_REQUEST_PATHS.session, cookieHeader),
    safeFetch<RepositoryResponse[]>(INITIAL_DASHBOARD_REQUEST_PATHS.repositories, cookieHeader),
    safeFetch<InstallationResponse[]>(INITIAL_DASHBOARD_REQUEST_PATHS.installations, cookieHeader),
    safeFetch<IssueResponse[]>(INITIAL_DASHBOARD_REQUEST_PATHS.issues, cookieHeader),
    safeFetch<PullRequestSummary[]>(INITIAL_DASHBOARD_REQUEST_PATHS.pullRequests, cookieHeader),
    safeFetch<SecurityFindingResponse[]>(INITIAL_DASHBOARD_REQUEST_PATHS.securityFindings, cookieHeader),
    safeFetch<ActivityItem[]>(INITIAL_DASHBOARD_REQUEST_PATHS.activities, cookieHeader),
    safeFetch<ActivitySummaryResponse>(INITIAL_DASHBOARD_REQUEST_PATHS.activitySummary, cookieHeader),
    safeFetch<RunSummary[]>(INITIAL_DASHBOARD_REQUEST_PATHS.runs, cookieHeader),
    safeFetch<{ reports: EvalReport[] }>(INITIAL_DASHBOARD_REQUEST_PATHS.evalReports, cookieHeader),
    safeFetch<ReadinessResponse>(INITIAL_DASHBOARD_REQUEST_PATHS.readiness, cookieHeader),
    safeFetch<PolicyResponse>(INITIAL_DASHBOARD_REQUEST_PATHS.policy, cookieHeader),
    safeFetch<GitHubOAuthConfigStatus>(INITIAL_DASHBOARD_REQUEST_PATHS.githubOAuthConfig, cookieHeader),
    safeFetch<GitHubAppConfigStatus>(INITIAL_DASHBOARD_REQUEST_PATHS.githubAppConfig, cookieHeader),
    safeFetch<ModelProviderConfigStatus>(INITIAL_DASHBOARD_REQUEST_PATHS.modelConfig, cookieHeader)
  ]);

  return {
    session,
    repositories: repositories ?? [],
    installations: installations ?? [],
    issues: issues ?? [],
    pullRequests: pullRequests ?? [],
    securityFindings: securityFindings ?? [],
    activities: activities ?? [],
    auditLogPage: null,
    activitySummary,
    runs: runs ?? [],
    evalReports: evals?.reports ?? [],
    readiness,
    policy,
    githubOAuthConfig,
    githubAppConfig,
    modelCatalog: null,
    modelConfig
  };
}

export function publicApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
}

async function safeFetch<T>(path: string, cookieHeader?: string): Promise<T | null> {
  for (const baseUrl of apiBaseUrls()) {
    try {
      const response = await fetch(`${baseUrl}${path}`, {
        cache: "no-store",
        headers: cookieHeader ? { cookie: cookieHeader } : undefined,
        next: { revalidate: 0 }
      });

      if (!response.ok) {
        continue;
      }

      return (await response.json()) as T;
    } catch {
      continue;
    }
  }

  return null;
}

function apiBaseUrls(): string[] {
  return Array.from(
    new Set(
      [
        process.env.INTERNAL_API_URL,
        process.env.NEXT_PUBLIC_API_URL,
        "http://api:8000",
        "http://repopilot-api-local:8000",
        "http://localhost:8000"
      ].filter((value): value is string => Boolean(value))
    )
  );
}
