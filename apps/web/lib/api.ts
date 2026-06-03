export type HealthResponse = {
  status: string;
  service: string;
  environment: string;
  timestamp: string;
};

export type SessionResponse = {
  username: string;
  role: string;
  mode: string;
  github_user_id?: string | null;
  email?: string | null;
};

export type MetricsResponse = {
  repositories: number;
  agent_runs: number;
  open_pull_requests: number;
  security_findings: number;
  blocking_security_findings: number;
  passed_validations: number;
  ready_for_review_prs: number;
  eval_runs: number;
};

export type RepositoryResponse = {
  id: string;
  installation_id?: string;
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

export type RunSummary = {
  id: string;
  issue_id: string | null;
  plan_id: string | null;
  state: string;
  model_used: string | null;
  total_tokens: number;
  total_cost: number;
  started_at: string;
  completed_at: string | null;
  latest_step: string | null;
  latest_step_status: string | null;
  validation_statuses: string[];
};

export type WebhookEvent = {
  id: string;
  event_type: string;
  status: string;
  received_at: string;
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
  github_installation_id: string;
  account_name: string;
  repository_count: number;
  created_at: string;
};

export type IssueResponse = {
  id: string;
  repository_id: string;
  number: number;
  title: string;
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
    plan: Record<string, unknown>;
  };
  run?: {
    id: string;
    state: string;
    total_tokens: number;
    total_cost: number;
    started_at: string;
    completed_at: string | null;
  };
};

export type PullRequestSummary = {
  pr_id: string;
  run_id: string;
  pr_number: number;
  url: string;
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
  changed_files: string[];
  validation_results: Array<{
    command: string;
    status: string;
    duration_ms: number | null;
    parsed_summary: string | null;
    log_uri?: string | null;
    evidence_hash?: string | null;
  }>;
  security_findings: Array<{
    tool: string;
    severity: string;
    file_path: string | null;
    description: string;
    status: string;
    status_reason?: string | null;
  }>;
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
  base_url: string | null;
  reasoning_level: string | null;
  reasoning_levels: string[];
  reasoning_supported: boolean;
  docs_url: string | null;
  verified: boolean;
  verified_at: string | null;
  status: "configured" | "missing";
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

export type HealthView = Partial<HealthResponse> & {
  ok: boolean;
};

export type OperatorData = {
  health: HealthView;
  session: SessionResponse | null;
  metrics: MetricsResponse | null;
  events: WebhookEvent[];
  repositories: RepositoryResponse[];
  installations: InstallationResponse[];
  issues: IssueResponse[];
  pullRequests: PullRequestSummary[];
  securityFindings: SecurityFindingResponse[];
  activities: ActivityItem[];
  runs: RunSummary[];
  evalReports: EvalReport[];
  readiness: ReadinessResponse | null;
  policy: PolicyResponse | null;
  githubOAuthConfig: GitHubOAuthConfigStatus | null;
  githubAppConfig: GitHubAppConfigStatus | null;
  modelCatalog: ModelCatalogResponse | null;
  modelConfig: ModelProviderConfigStatus | null;
};

export async function getDashboardData(): Promise<OperatorData> {
  const [
    health,
    session,
    metrics,
    events,
    repositories,
    installations,
    issues,
    pullRequests,
    securityFindings,
    activities,
    runs,
    evals,
    readiness,
    policy,
    githubOAuthConfig,
    githubAppConfig,
    modelCatalog,
    modelConfig
  ] = await Promise.all([
    getApiHealth(),
    safeFetch<SessionResponse>("/auth/session"),
    safeFetch<MetricsResponse>("/metrics/overview"),
    safeFetch<WebhookEvent[]>("/webhooks/events"),
    safeFetch<RepositoryResponse[]>("/repos"),
    safeFetch<InstallationResponse[]>("/installations"),
    safeFetch<IssueResponse[]>("/issues?limit=300"),
    safeFetch<PullRequestSummary[]>("/prs?limit=200"),
    safeFetch<SecurityFindingResponse[]>("/security/findings?limit=300"),
    safeFetch<ActivityItem[]>("/activity?limit=160"),
    safeFetch<RunSummary[]>("/runs?limit=80"),
    safeFetch<{ reports: EvalReport[] }>("/evals/reports"),
    safeFetch<ReadinessResponse>("/settings/readiness"),
    safeFetch<PolicyResponse>("/settings/policy"),
    safeFetch<GitHubOAuthConfigStatus>("/settings/github/oauth"),
    safeFetch<GitHubAppConfigStatus>("/settings/github/app"),
    safeFetch<ModelCatalogResponse>("/settings/models/catalog"),
    safeFetch<ModelProviderConfigStatus>("/settings/models/config")
  ]);

  return {
    health,
    session,
    metrics,
    events: events ?? [],
    repositories: repositories ?? [],
    installations: installations ?? [],
    issues: issues ?? [],
    pullRequests: pullRequests ?? [],
    securityFindings: securityFindings ?? [],
    activities: activities ?? [],
    runs: runs ?? [],
    evalReports: evals?.reports ?? [],
    readiness,
    policy,
    githubOAuthConfig,
    githubAppConfig,
    modelCatalog,
    modelConfig
  };
}

async function getApiHealth(): Promise<HealthView> {
  const data = await safeFetch<HealthResponse>("/health");
  if (!data) {
    return { ok: false };
  }
  return { ...data, ok: data.status === "ok" };
}

export function publicApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
}

async function safeFetch<T>(path: string): Promise<T | null> {
  for (const baseUrl of apiBaseUrls()) {
    try {
      const response = await fetch(`${baseUrl}${path}`, {
        cache: "no-store",
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
