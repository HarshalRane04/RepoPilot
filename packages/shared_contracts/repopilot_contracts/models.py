from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class IssueType(StrEnum):
    BUG = "bug"
    FEATURE = "feature"
    DOCS = "docs"
    TEST = "test"
    REFACTOR = "refactor"
    SECURITY = "security"
    QUESTION = "question"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AgentRunState(StrEnum):
    NEW_EVENT = "NEW_EVENT"
    VALIDATE_WEBHOOK = "VALIDATE_WEBHOOK"
    NORMALIZE_EVENT = "NORMALIZE_EVENT"
    TRIAGE_ISSUE = "TRIAGE_ISSUE"
    RETRIEVE_CONTEXT = "RETRIEVE_CONTEXT"
    GENERATE_PLAN = "GENERATE_PLAN"
    POLICY_REVIEW_PLAN = "POLICY_REVIEW_PLAN"
    WAIT_FOR_APPROVAL = "WAIT_FOR_APPROVAL"
    CREATE_BRANCH = "CREATE_BRANCH"
    IMPLEMENT_PATCH = "IMPLEMENT_PATCH"
    GENERATE_TESTS = "GENERATE_TESTS"
    RUN_LOCAL_VALIDATION = "RUN_LOCAL_VALIDATION"
    RUN_SECURITY_CHECKS = "RUN_SECURITY_CHECKS"
    OPEN_DRAFT_PR = "OPEN_DRAFT_PR"
    WAIT_FOR_CI = "WAIT_FOR_CI"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    NEEDS_INFO = "NEEDS_INFO"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    MERGED_OR_CLOSED = "MERGED_OR_CLOSED"


class PlanApprovalStatus(StrEnum):
    DRAFT = "draft"
    WAITING = "waiting"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVISED = "revised"


class PolicyDecisionType(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    ESCALATE = "escalate"


class ValidationStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


class SecuritySeverity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ArtifactReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    uri: str
    artifact_type: str
    storage_backend: str = "local"
    storage_key: str | None = None
    sha256: str
    byte_size: int = Field(ge=0)
    content_type: str = "application/octet-stream"
    metadata: dict[str, Any] = Field(default_factory=dict)


class IntegrationState(StrEnum):
    CONFIGURED = "configured"
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    PLACEHOLDER = "placeholder"
    MISSING = "missing"
    DISABLED = "disabled"


class AgentStepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"


class AuditActorType(StrEnum):
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"
    GITHUB = "github"


class ToolPermissionTier(StrEnum):
    READ = "read"
    WORKSPACE_WRITE = "workspace_write"
    SANDBOX_EXEC = "sandbox_exec"
    SECURITY_GATE = "security_gate"
    GITHUB_WRITE = "github_write"
    HUMAN_GATE = "human_gate"


class ToolCallStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"


class ToolBlockType(StrEnum):
    NOT_IMPLEMENTED = "not_implemented"
    POLICY_DENIED = "policy_denied"
    AUTH_REQUIRED = "auth_required"
    STATE_MISMATCH = "state_mismatch"
    APPROVAL_REQUIRED = "approval_required"
    GITHUB_WRITES_DISABLED = "github_writes_disabled"
    BUDGET_EXCEEDED = "budget_exceeded"
    UNKNOWN_TOOL = "unknown_tool"


class LLMCallMode(StrEnum):
    MOCK = "mock"
    LIVE = "live"
    FALLBACK = "fallback"


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    referenced_files: list[str] = Field(default_factory=list)
    reasoning_summary: str = ""


class CodeContextChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_path: str
    symbol_name: str | None = None
    chunk_type: str = "code"
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    score: float = Field(ge=0.0)
    semantic_score: float = Field(default=0.0, ge=0.0)
    lexical_score: float = Field(default=0.0, ge=0.0)
    path_score: float = Field(default=0.0, ge=0.0)
    selection_reason: str = ""
    freshness: dict[str, Any] = Field(default_factory=dict)
    text: str


class CodeContextPack(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repository_id: str
    query: str
    chunks: list[CodeContextChunk] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)


class IssueTriageResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issue_id: str
    issue_type: IssueType
    complexity: RiskLevel = RiskLevel.LOW
    risk_score: int = Field(ge=0, le=100)
    missing_information: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    suggested_labels: list[str] = Field(default_factory=list)
    suggested_comment: str | None = None
    recommended_action: str = Field(pattern="^(ask_info|plan|reject|human_review)$")
    evidence: Evidence = Field(default_factory=Evidence)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class ImplementationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str
    issue_id: str
    summary: str | None = None
    files_to_inspect: list[str] = Field(default_factory=list)
    files_to_modify: list[str] = Field(default_factory=list)
    tests_to_add: list[str] = Field(default_factory=list)
    commands_to_run: list[str] = Field(default_factory=list)
    intended_changes: list[str] = Field(default_factory=list)
    validation_strategy: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    context_citations: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)
    rollback_plan: str
    requires_human_approval: bool = True
    plan_hash: str | None = None


class RepositoryIndexRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_path: str
    commit_sha: str | None = None
    max_files: int = Field(default=500, ge=1, le=5000)
    max_file_bytes: int = Field(default=120_000, ge=1_000, le=2_000_000)


class RepositoryIndexResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index_id: str | None = None
    repository_id: str
    source_path: str
    commit_sha: str
    content_fingerprint: str | None = None
    files_indexed: int = Field(ge=0)
    chunks_indexed: int = Field(ge=0)
    skipped_files: int = Field(ge=0)
    embedding_provider: str = "mock"
    embedding_model: str = "mock-embedding"
    embedding_dimensions: int = Field(default=1536, ge=1)
    chunker_version: str | None = None


class ToolCallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    state: AgentRunState
    tool_name: str
    actor: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    requested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ToolCallBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_calls: list[ToolCallRequest] = Field(min_length=1, max_length=20)


class ToolDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    permission: ToolPermissionTier
    required_states: list[AgentRunState] = Field(default_factory=list)
    requires_approved_plan: bool = False
    requires_github_write_mode: bool = False
    enabled: bool = True
    disabled_reason: str | None = None


class ToolCallResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_call_id: str = Field(default_factory=lambda: str(uuid4()))
    tool_name: str
    status: ToolCallStatus
    output: dict[str, Any] = Field(default_factory=dict)
    blocked_reason: str | None = None
    block_type: ToolBlockType | None = None
    duration_ms: int = Field(default=0, ge=0)


class TokenUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: int = Field(default=0, ge=0)
    completion: int = Field(default=0, ge=0)
    total: int = Field(default=0, ge=0)


class LLMRequestMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: UUID | None = None
    agent_name: str = "model_gateway"
    provider: str = "mock"
    model: str = "mock-planner"
    mode: LLMCallMode = LLMCallMode.MOCK
    prompt_hash: str | None = None
    context_citations: list[str] = Field(default_factory=list)


class LLMResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str
    model: str
    tokens: TokenUsage = Field(default_factory=TokenUsage)
    cost: float = Field(default=0.0, ge=0.0)
    latency_ms: int = Field(default=0, ge=0)
    mode: LLMCallMode = LLMCallMode.MOCK
    prompt_hash: str | None = None
    response_hash: str | None = None


class EmbeddingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    embeddings: list[list[float]]
    provider: str = "mock"
    model: str
    dimensions: int = Field(ge=1)
    tokens: TokenUsage = Field(default_factory=TokenUsage)
    cost: float = Field(default=0.0, ge=0.0)
    latency_ms: int = Field(default=0, ge=0)
    mode: LLMCallMode = LLMCallMode.MOCK


class PolicyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: PolicyDecisionType
    reason: str
    required_approvals: list[str] = Field(default_factory=list)
    blocked_patterns: list[str] = Field(default_factory=list)
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SandboxCommandRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_path: str
    command: str
    timeout_seconds: int = Field(default=60, ge=1, le=600)


class SandboxCommandResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: str
    status: ValidationStatus
    exit_code: int | None = None
    duration_ms: int = Field(ge=0)
    stdout: str = ""
    stderr: str = ""
    blocked_reason: str | None = None


class ImplementationRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_path: str
    validation_command: str | None = None
    timeout_seconds: int = Field(default=120, ge=1, le=900)
    max_changed_files: int = Field(default=5, ge=1, le=20)


class PatchFileChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    change_type: str = Field(pattern="^(create|modify|delete)$")
    additions: int = Field(ge=0)
    deletions: int = Field(ge=0)


class GeneratedPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    source_workspace_path: str
    working_workspace_path: str
    patch_hash: str
    diff: str
    diff_uri: str | None = None
    diff_artifact: ArtifactReference | None = None
    changed_files: list[PatchFileChange] = Field(default_factory=list)
    summary: str


class ImplementationRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: ValidationStatus
    patch: GeneratedPatch | None = None
    validation: SandboxCommandResult | None = None
    blocked_reason: str | None = None


class SecurityScanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_path: str | None = None
    fail_on_findings: bool = True


class CodeQLSarifIngestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sarif: dict[str, Any]
    source: str = Field(default="codeql-sarif", min_length=1, max_length=255)
    fail_on_findings: bool = True


class CodeQLAlertFetchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: str = Field(default="open", pattern="^(open|fixed|dismissed)$")
    ref: str | None = Field(default=None, max_length=255)
    tool_name: str = Field(default="CodeQL", min_length=1, max_length=255)
    per_page: int = Field(default=100, ge=1, le=100)
    fail_on_findings: bool = True


class CodeQLRecommendationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    tool: str = "codeql"
    workflow_path: str = ".github/workflows/codeql.yml"
    summary: str
    workflow_yaml: str


class DraftPullRequestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    body: str | None = None
    base_branch: str | None = None
    branch_prefix: str = Field(default="repopilot", min_length=1, max_length=64)


class DraftPullRequestResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pr_id: str
    run_id: str
    pr_number: int = Field(ge=1)
    url: str
    status: str
    branch_name: str
    ci_status: str | None = None
    summary: str


class CIAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_name: str = "local-ci"
    conclusion: str = Field(default="success", pattern="^(success|failure|cancelled|skipped)$")
    log_text: str = ""


class CIAnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pr_id: str
    run_id: str
    ci_status: str
    summary: str
    failure_reasons: list[str] = Field(default_factory=list)
    ready_for_review: bool = False
    failed_job: str | None = None
    failing_command: str | None = None
    root_cause: str | None = None
    proposed_fix_path: str | None = None


class EvalRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    benchmark_version: str = Field(default="v1-local", min_length=1, max_length=64)
    task_count: int = Field(default=30, ge=1, le=500)
    model_settings: dict[str, Any] = Field(default_factory=dict, alias="model_config")


class EvalTaskFixture(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    category: str
    fixture_repository: str
    issue_title: str
    issue_body: str
    expected_changed_files: list[str] = Field(default_factory=list)
    expected_diff_summary: str
    expected_tests: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    disallowed_changes: list[str] = Field(default_factory=list)
    expected_security_result: str = Field(pattern="^(pass|block|escalate)$")


class EvalTaskOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    category: str
    status: str = Field(pattern="^(passed|failed)$")
    score: float = Field(ge=0.0, le=1.0)
    failure_reasons: list[str] = Field(default_factory=list)


class EvalRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    eval_run_id: str
    benchmark_version: str
    metrics: dict[str, Any]
    report_uri: str
    task_outcomes: list[EvalTaskOutcome] = Field(default_factory=list)


class ValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    command: str
    status: ValidationStatus
    duration_ms: int = Field(ge=0)
    parsed_summary: str = ""
    log_uri: str | None = None
    evidence_hash: str | None = None
    log_artifact: ArtifactReference | None = None


class SecurityFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    tool: str
    severity: SecuritySeverity
    description: str
    file_path: str | None = None
    status: str = "open"
    status_reason: str | None = None
    status_actor: str | None = None
    status_changed_at: datetime | None = None


class SecurityScanResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: ValidationStatus
    scanned_files: int = Field(ge=0)
    findings: list[SecurityFinding] = Field(default_factory=list)
    summary: str


class RunTraceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    state: AgentRunState
    event_name: str
    actor_type: AuditActorType
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class LLMTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    agent_name: str
    prompt_hash: str
    response_hash: str | None = None
    provider: str = "unknown"
    model: str
    mode: str = "unknown"
    tokens: int = Field(ge=0)
    cost: float = Field(ge=0.0)
    latency_ms: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PullRequestSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pr_number: int
    url: str
    status: str
    risk_score: int = Field(ge=0, le=100)
    validation_results: list[ValidationResult] = Field(default_factory=list)
    security_findings: list[SecurityFinding] = Field(default_factory=list)


class IntegrationStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    state: IntegrationState
    mode: str | None = None
    required_for_production: bool = True
    detail: str
    next_step: str


class RuntimeReadiness(BaseModel):
    model_config = ConfigDict(extra="forbid")

    environment: str
    production_ready: bool
    github_writes_enabled: bool
    local_record_mode: bool
    github_mode: str
    model_mode: str
    integrations: list[IntegrationStatus] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ActivityEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    action: str
    status: str
    created_at: datetime
    entity_type: str
    entity_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentRunListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    issue_id: str | None = None
    plan_id: str | None = None
    state: str
    model_used: str | None = None
    total_tokens: int = Field(ge=0)
    total_cost: float = Field(ge=0.0)
    started_at: datetime
    completed_at: datetime | None = None
    latest_step: str | None = None
    latest_step_status: str | None = None
    validation_statuses: list[str] = Field(default_factory=list)


class AgentRunStepDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    step_name: str
    status: str
    output_json: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    created_at: datetime


class AgentRunValidationDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    command: str
    status: str
    duration_ms: int = Field(ge=0)
    parsed_summary: str = ""
    log_uri: str | None = None
    evidence_hash: str | None = None
    log_artifact: ArtifactReference | None = None


class AgentRunDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    issue_id: str | None = None
    plan_id: str | None = None
    state: str
    model_used: str | None = None
    total_tokens: int = Field(ge=0)
    total_cost: float = Field(ge=0.0)
    started_at: datetime
    completed_at: datetime | None = None
    steps: list[AgentRunStepDetail] = Field(default_factory=list)
    validation_results: list[AgentRunValidationDetail] = Field(default_factory=list)


class RunTraceRunSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    state: str
    model_used: str | None = None
    total_tokens: int = Field(ge=0)
    total_cost: float = Field(ge=0.0)
    started_at: datetime
    completed_at: datetime | None = None


class RunTraceStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_name: str
    status: str
    latency_ms: int | None = Field(default=None, ge=0)
    created_at: datetime
    output_json: dict[str, Any] = Field(default_factory=dict)


class RunTraceValidation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: str
    status: str
    duration_ms: int = Field(ge=0)
    parsed_summary: str = ""


class RunTraceSecurityFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str
    severity: str
    file_path: str | None = None
    description: str
    status: str


class RunTracePullRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    number: int = Field(ge=1)
    url: str
    status: str
    ci_status: str | None = None


class RunTraceAuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str
    actor_type: str
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunTraceLLMTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_name: str
    prompt_hash: str
    response_hash: str | None = None
    provider: str = "unknown"
    model: str
    mode: str = "unknown"
    tokens: int = Field(ge=0)
    cost: float = Field(ge=0.0)
    latency_ms: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunTraceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run: RunTraceRunSummary
    steps: list[RunTraceStep] = Field(default_factory=list)
    validation_results: list[RunTraceValidation] = Field(default_factory=list)
    security_findings: list[RunTraceSecurityFinding] = Field(default_factory=list)
    pull_requests: list[RunTracePullRequest] = Field(default_factory=list)
    audit_events: list[RunTraceAuditEvent] = Field(default_factory=list)
    llm_traces: list[RunTraceLLMTrace] = Field(default_factory=list)


class PlanDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    issue_id: str
    active_run_ids: list[str] = Field(default_factory=list)
    approval_status: str
    approved_by: str | None = None
    approved_at: datetime | None = None
    version: int = Field(ge=1)
    plan: dict[str, Any] = Field(default_factory=dict)


class IssueSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    number: int = Field(ge=0)
    title: str
    status: str


class RepositorySummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    owner: str
    name: str
    default_branch: str | None = None


class PlanSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    approval_status: str
    summary: str | None = None
    rollback_plan: str | None = None
    files_to_modify: list[str] = Field(default_factory=list)
    tests_to_add: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)


class PullRequestValidationEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: str
    status: str
    duration_ms: int = Field(ge=0)
    parsed_summary: str = ""
    log_uri: str | None = None
    evidence_hash: str | None = None
    log_artifact: ArtifactReference | None = None


class PullRequestSecurityFindingEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str
    severity: str
    file_path: str | None = None
    description: str
    status: str
    status_reason: str | None = None


class PullRequestSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pr_id: str
    run_id: str
    pr_number: int = Field(ge=1)
    url: str
    status: str
    ci_status: str | None = None
    risk_score: int = Field(ge=0, le=100)
    created_at: datetime
    issue: IssueSummaryResponse | None = None
    repository: RepositorySummaryResponse | None = None
    plan: PlanSummaryResponse | None = None
    changed_files: list[str] = Field(default_factory=list)
    validation_results: list[PullRequestValidationEvidence] = Field(default_factory=list)
    security_findings: list[PullRequestSecurityFindingEvidence] = Field(default_factory=list)


class SecurityFindingRunSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    state: str
    started_at: datetime
    completed_at: datetime | None = None


class SecurityFindingPullRequestSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    number: int = Field(ge=1)
    url: str
    status: str
    ci_status: str | None = None


class SecurityFindingDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    run_id: str
    tool: str
    severity: str
    file_path: str | None = None
    description: str
    status: str
    status_reason: str | None = None
    status_actor: str | None = None
    status_changed_at: datetime | None = None
    run: SecurityFindingRunSummary | None = None
    issue: IssueSummaryResponse | None = None
    repository: RepositorySummaryResponse | None = None
    pull_request: SecurityFindingPullRequestSummary | None = None


class EvalReportItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    benchmark_version: str
    metrics: dict[str, Any] = Field(default_factory=dict)
    report_uri: str | None = None
    created_at: datetime


class EvalReportsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reports: list[EvalReportItem] = Field(default_factory=list)
