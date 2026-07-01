from __future__ import annotations

import difflib
import fnmatch
import hashlib
import json
import re
import shutil
import subprocess
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from repopilot_contracts import (
    AgentRunState,
    CIAnalysisRequest,
    DraftPullRequestRequest,
    EvalRunRequest,
    PlanApprovalStatus,
    RepositoryIndexRequest,
    SandboxCommandRequest,
    SecurityScanRequest,
    SecuritySeverity,
    ToolBlockType,
    ToolCallRequest,
    ToolCallResult,
    ToolCallStatus,
    ToolDefinition,
    ToolPermissionTier,
    ValidationStatus,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import AgentRun, AgentStep, Installation, Issue, Plan, Repository, SecurityFinding, ValidationResult as DbValidationResult
from app.services.artifacts import ArtifactStore, maybe_externalize_json
from app.services.audit import record_audit
from app.services.ci_analyzer import CIAnalyzer
from app.services.draft_pr import DraftPullRequestService
from app.services.eval_runner import EvalRunner
from app.services.github_app import GitHubApiClient, GitHubIntegrationError
from app.services.implementation_agent import IGNORED_WORKSPACE_DIRS
from app.services.observability import ObservabilityService
from app.services.planning import PlanningService, approved_plan_hash_matches, implementation_plan_from_db
from app.services.policy import PolicyEngine
from app.services.repo_indexer import IGNORED_DIRS, SENSITIVE_FILE_NAMES, SENSITIVE_SUFFIXES, TEXT_EXTENSIONS, RepositoryIndexer
from app.services.runtime_secrets import effective_settings
from app.services.sandbox import SandboxRunner
from app.services.security_envelope import redact_data, redact_text, stable_json_hash
from app.services.security_scanner import SecurityScanner
from app.services.state_machine import next_states, transition_run
from app.services.triage import TriageService


WORKSPACE_ROOT = Path("/tmp/repopilot-agent-workspaces")
INTERNAL_DIR = ".repopilot"
MAX_READ_BYTES = 200_000
MAX_DIFF_BYTES = 40_000
IGNORED_TOOL_DIRS = set(IGNORED_DIRS) | set(IGNORED_WORKSPACE_DIRS) | {INTERNAL_DIR}
SENSITIVE_TOOL_DIR_NAMES = {"secrets", ".secrets"}


class ToolBlocked(ValueError):
    def __init__(self, message: str, *, block_type: ToolBlockType = ToolBlockType.POLICY_DENIED) -> None:
        super().__init__(message)
        self.block_type = block_type


class ToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RepoIndexInput(ToolInput):
    repository_id: UUID
    source_path: str
    commit_sha: str | None = None
    max_files: int = Field(default=500, ge=1, le=5000)
    max_file_bytes: int = Field(default=120_000, ge=1_000, le=2_000_000)


class RepoSearchContextInput(ToolInput):
    repository_id: UUID
    query: str = Field(min_length=1)
    limit: int = Field(default=6, ge=1, le=20)


class RepoListFilesInput(ToolInput):
    workspace_path: str
    glob: str | None = None
    max_files: int = Field(default=200, ge=1, le=1000)


class RepoReadFileInput(ToolInput):
    workspace_path: str
    path: str
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)


class RepoReadFileSpec(ToolInput):
    path: str
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)


class RepoReadFilesInput(ToolInput):
    workspace_path: str
    files: list[RepoReadFileSpec] = Field(min_length=1, max_length=12)


class RepoGrepInput(ToolInput):
    workspace_path: str
    query: str = Field(min_length=1)
    glob: str | None = None
    max_results: int = Field(default=50, ge=1, le=200)


class RepoSummarizeTreeInput(ToolInput):
    workspace_path: str
    max_depth: int = Field(default=3, ge=1, le=8)


class IssueTriageInput(ToolInput):
    issue_id: UUID
    body: str = ""


class PlanGenerateInput(ToolInput):
    issue_id: UUID
    context_limit: int = Field(default=6, ge=1, le=20)


class PlanIdInput(ToolInput):
    plan_id: UUID


class PlanRequestApprovalInput(PlanIdInput):
    summary: str | None = Field(default=None, max_length=4000)


class CreateRunCopyInput(ToolInput):
    run_id: UUID
    source_workspace: str


class WorkspacePathInput(ToolInput):
    workspace_path: str


class ApplyPatchInput(WorkspacePathInput):
    diff: str = Field(min_length=1, max_length=1_000_000)
    max_changed_files: int = Field(default=5, ge=1, le=20)
    return_diff: bool = True


class WriteFileInput(WorkspacePathInput):
    path: str
    content: str = Field(max_length=1_000_000)


class ReplaceTextInput(WorkspacePathInput):
    path: str
    old_text: str = Field(min_length=1, max_length=500_000)
    new_text: str = Field(max_length=500_000)


class DiscardWorkspaceInput(ToolInput):
    run_id: UUID


class SandboxCommandInput(WorkspacePathInput):
    command: str = Field(min_length=1, max_length=500)
    timeout_seconds: int = Field(default=60, ge=1, le=600)


class ValidationRunInput(WorkspacePathInput):
    run_id: UUID
    command: str | None = Field(default=None, max_length=500)
    timeout_seconds: int = Field(default=120, ge=1, le=900)


class ValidationRecordInput(ToolInput):
    run_id: UUID
    command: str = Field(min_length=1, max_length=500)
    status: ValidationStatus
    summary: str = Field(default="", max_length=4000)
    stdout: str = Field(default="", max_length=8000)
    stderr: str = Field(default="", max_length=8000)
    duration_ms: int = Field(default=0, ge=0)


class SecurityScanPatchInput(ToolInput):
    run_id: UUID
    workspace_path: str | None = None
    fail_on_findings: bool = True


class SecurityScanWorkspaceInput(ToolInput):
    run_id: UUID
    workspace_path: str
    fail_on_findings: bool = True


class RunIdInput(ToolInput):
    run_id: UUID


class DraftPrInput(ToolInput):
    run_id: UUID
    title: str | None = Field(default=None, max_length=300)
    body: str | None = Field(default=None, max_length=20_000)
    base_branch: str | None = Field(default=None, max_length=255)
    branch_prefix: str = Field(default="repopilot", min_length=1, max_length=64)


class CiAnalyzeInput(ToolInput):
    pr_id: UUID
    workflow_name: str = "local-ci"
    conclusion: str = Field(default="success", pattern="^(success|failure|cancelled|skipped)$")
    log_text: str = ""


class GithubCreateBranchInput(ToolInput):
    repository_id: UUID
    branch_name: str
    base_sha: str


class GithubCommitPatchInput(ToolInput):
    repository_id: UUID
    branch_name: str
    message: str
    diff_hash: str


class GithubOpenPullRequestInput(ToolInput):
    repository_id: UUID
    branch_name: str
    title: str
    body: str
    base_branch: str


class GithubCommentIssueInput(ToolInput):
    repository_id: UUID
    issue_number: int = Field(ge=1)
    body: str


class GithubFetchCiLogsInput(ToolInput):
    repository_id: UUID
    pr_number: int = Field(ge=1)


class RunTransitionInput(ToolInput):
    run_id: UUID
    next_state: AgentRunState
    reason: str = Field(min_length=1, max_length=1000)


class RunStopInput(ToolInput):
    run_id: UUID
    reason: str = Field(default="Tool call requested run stop.", max_length=1000)


class AskUserInput(ToolInput):
    run_id: UUID
    question: str = Field(min_length=1, max_length=2000)
    choices: list[str] = Field(default_factory=list, max_length=5)


class EvalRecordInput(ToolInput):
    benchmark_version: str = Field(default="v1-local", min_length=1, max_length=64)
    task_count: int = Field(default=30, ge=1, le=500)
    model_settings: dict[str, Any] = Field(default_factory=dict, alias="model_config")


ToolHandler = Callable[[AsyncSession, ToolCallRequest, BaseModel], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class ToolSpec:
    definition: ToolDefinition
    input_model: type[BaseModel]
    handler: ToolHandler | None


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self._register_defaults()

    def definitions(self) -> list[ToolDefinition]:
        return [spec.definition for spec in self._tools.values()]

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def _register(
        self,
        *,
        name: str,
        description: str,
        input_model: type[BaseModel],
        permission: ToolPermissionTier,
        handler: ToolHandler | None,
        required_states: list[AgentRunState] | None = None,
        requires_approved_plan: bool = False,
        requires_github_write_mode: bool = False,
        enabled: bool = True,
        disabled_reason: str | None = None,
    ) -> None:
        output_schema = {"type": "object", "additionalProperties": True}
        self._tools[name] = ToolSpec(
            definition=ToolDefinition(
                name=name,
                description=description,
                input_schema=input_model.model_json_schema(),
                output_schema=output_schema,
                permission=permission,
                required_states=required_states or [],
                requires_approved_plan=requires_approved_plan,
                requires_github_write_mode=requires_github_write_mode,
                enabled=enabled,
                disabled_reason=disabled_reason,
            ),
            input_model=input_model,
            handler=handler,
        )

    def _register_defaults(self) -> None:
        self._register(name="repo.index", description="Index a local repository path into code context chunks.", input_model=RepoIndexInput, permission=ToolPermissionTier.READ, handler=_repo_index)
        self._register(name="repo.search_context", description="Retrieve ranked repository context with file and line citations.", input_model=RepoSearchContextInput, permission=ToolPermissionTier.READ, handler=_repo_search_context)
        self._register(name="repo.list_files", description="List text/code files from a workspace using RepoPilot ignore rules.", input_model=RepoListFilesInput, permission=ToolPermissionTier.READ, handler=_repo_list_files)
        self._register(name="repo.read_file", description="Read bounded file content with optional line ranges.", input_model=RepoReadFileInput, permission=ToolPermissionTier.READ, handler=_repo_read_file)
        self._register(name="repo.read_files", description="Read multiple bounded file snippets from a workspace with per-file errors.", input_model=RepoReadFilesInput, permission=ToolPermissionTier.READ, handler=_repo_read_files)
        self._register(name="repo.grep", description="Search workspace text files for a literal query.", input_model=RepoGrepInput, permission=ToolPermissionTier.READ, handler=_repo_grep)
        self._register(name="repo.summarize_tree", description="Return a compact workspace tree and stack hints.", input_model=RepoSummarizeTreeInput, permission=ToolPermissionTier.READ, handler=_repo_summarize_tree)
        self._register(name="issue.triage", description="Run deterministic issue triage without mutating the issue.", input_model=IssueTriageInput, permission=ToolPermissionTier.READ, handler=_issue_triage)
        self._register(name="plan.generate", description="Generate an implementation plan from issue and indexed context.", input_model=PlanGenerateInput, permission=ToolPermissionTier.READ, handler=_plan_generate)
        self._register(name="plan.evaluate_policy", description="Evaluate policy for an existing implementation plan.", input_model=PlanIdInput, permission=ToolPermissionTier.READ, handler=_plan_evaluate_policy)
        self._register(name="plan.request_approval", description="Keep or move a plan into waiting-for-approval state and report its policy decision.", input_model=PlanRequestApprovalInput, permission=ToolPermissionTier.HUMAN_GATE, handler=_plan_request_approval)
        self._register(name="workspace.create_run_copy", description="Create an isolated run workspace copy and baseline manifest.", input_model=CreateRunCopyInput, permission=ToolPermissionTier.WORKSPACE_WRITE, handler=_workspace_create_run_copy, requires_approved_plan=True)
        self._register(name="workspace.diff", description="Return current workspace changes against the RepoPilot baseline when available.", input_model=WorkspacePathInput, permission=ToolPermissionTier.READ, handler=_workspace_diff)
        self._register(name="workspace.apply_patch", description="Apply a unified diff to an approved isolated run workspace.", input_model=ApplyPatchInput, permission=ToolPermissionTier.WORKSPACE_WRITE, handler=_workspace_apply_patch, requires_approved_plan=True)
        self._register(name="workspace.write_file", description="Create or replace a file inside an approved isolated run workspace.", input_model=WriteFileInput, permission=ToolPermissionTier.WORKSPACE_WRITE, handler=_workspace_write_file, requires_approved_plan=True)
        self._register(name="workspace.replace_text", description="Replace exact text inside one approved isolated workspace file.", input_model=ReplaceTextInput, permission=ToolPermissionTier.WORKSPACE_WRITE, handler=_workspace_replace_text, requires_approved_plan=True)
        self._register(name="workspace.discard", description="Delete an isolated run workspace.", input_model=DiscardWorkspaceInput, permission=ToolPermissionTier.WORKSPACE_WRITE, handler=_workspace_discard, requires_approved_plan=True)
        self._register(name="sandbox.run_command", description="Run an allowlisted command through the configured sandbox backend.", input_model=SandboxCommandInput, permission=ToolPermissionTier.SANDBOX_EXEC, handler=_sandbox_run_command, requires_approved_plan=True)
        self._register(name="validation.run_tests", description="Run the plan-specified or detected test command through the sandbox.", input_model=ValidationRunInput, permission=ToolPermissionTier.SANDBOX_EXEC, handler=_validation_run_tests, requires_approved_plan=True)
        self._register(name="validation.run_lint", description="Run an allowlisted lint command through the sandbox.", input_model=ValidationRunInput, permission=ToolPermissionTier.SANDBOX_EXEC, handler=_validation_run_lint, requires_approved_plan=True)
        self._register(name="validation.run_typecheck", description="Run an allowlisted typecheck command through the sandbox.", input_model=ValidationRunInput, permission=ToolPermissionTier.SANDBOX_EXEC, handler=_validation_run_typecheck, requires_approved_plan=True)
        self._register(name="validation.record_result", description="Persist external validation evidence for a run.", input_model=ValidationRecordInput, permission=ToolPermissionTier.SANDBOX_EXEC, handler=_validation_record_result, requires_approved_plan=True)
        self._register(name="security.scan_patch", description="Scan the latest generated patch and changed files for security findings.", input_model=SecurityScanPatchInput, permission=ToolPermissionTier.SECURITY_GATE, handler=_security_scan_patch, requires_approved_plan=True, required_states=[AgentRunState.RUN_LOCAL_VALIDATION, AgentRunState.RUN_SECURITY_CHECKS, AgentRunState.WAIT_FOR_CI, AgentRunState.READY_FOR_REVIEW])
        self._register(name="security.scan_workspace", description="Scan bounded workspace files for security findings.", input_model=SecurityScanWorkspaceInput, permission=ToolPermissionTier.SECURITY_GATE, handler=_security_scan_workspace, requires_approved_plan=True, required_states=[AgentRunState.RUN_LOCAL_VALIDATION, AgentRunState.RUN_SECURITY_CHECKS, AgentRunState.WAIT_FOR_CI, AgentRunState.READY_FOR_REVIEW])
        self._register(name="security.explain_findings", description="Summarize stored security findings for a run.", input_model=RunIdInput, permission=ToolPermissionTier.READ, handler=_security_explain_findings)
        self._register(name="security.semgrep", description="Semgrep-style adapter for generated workspaces, guarded by SEMGREP_ENABLED.", input_model=SecurityScanWorkspaceInput, permission=ToolPermissionTier.SECURITY_GATE, handler=_security_semgrep, requires_approved_plan=True)
        self._register(name="security.dependency_audit", description="Dependency-audit adapter for generated workspaces, guarded by DEPENDENCY_AUDIT_ENABLED.", input_model=SecurityScanWorkspaceInput, permission=ToolPermissionTier.SECURITY_GATE, handler=_security_dependency_audit, requires_approved_plan=True)
        self._register(name="pr.open_draft_record", description="Create the current local draft PR record after validation and security gates.", input_model=DraftPrInput, permission=ToolPermissionTier.GITHUB_WRITE, handler=_pr_open_draft_record, requires_approved_plan=True, required_states=[AgentRunState.RUN_LOCAL_VALIDATION, AgentRunState.RUN_SECURITY_CHECKS])
        self._register(name="ci.analyze", description="Analyze CI conclusion and failure-log text for a PR.", input_model=CiAnalyzeInput, permission=ToolPermissionTier.READ, handler=_ci_analyze)
        self._register(name="github.create_branch", description="Create a real GitHub branch through installation credentials.", input_model=GithubCreateBranchInput, permission=ToolPermissionTier.GITHUB_WRITE, handler=_github_create_branch, requires_github_write_mode=True)
        self._register(name="github.commit_patch", description="Commit the latest validated patch to a real GitHub branch.", input_model=GithubCommitPatchInput, permission=ToolPermissionTier.GITHUB_WRITE, handler=_github_commit_patch, requires_github_write_mode=True)
        self._register(name="github.open_pull_request", description="Open a real GitHub draft pull request.", input_model=GithubOpenPullRequestInput, permission=ToolPermissionTier.GITHUB_WRITE, handler=_github_open_pull_request, requires_github_write_mode=True)
        self._register(name="github.comment_issue", description="Create a real GitHub issue or PR comment.", input_model=GithubCommentIssueInput, permission=ToolPermissionTier.GITHUB_WRITE, handler=_github_comment_issue, requires_github_write_mode=True)
        self._register(name="github.fetch_ci_logs", description="Fetch bounded, redacted GitHub check-run and annotation summaries for a pull request head.", input_model=GithubFetchCiLogsInput, permission=ToolPermissionTier.READ, handler=_github_fetch_ci_logs)
        self._register(name="run.get_trace", description="Return the full auditable trace for a run.", input_model=RunIdInput, permission=ToolPermissionTier.READ, handler=_run_get_trace)
        self._register(name="run.next_states", description="Return allowed next states for the run.", input_model=RunIdInput, permission=ToolPermissionTier.READ, handler=_run_next_states)
        self._register(name="run.transition", description="Transition a run through the guarded state machine for human/system actors.", input_model=RunTransitionInput, permission=ToolPermissionTier.HUMAN_GATE, handler=_run_transition)
        self._register(name="run.stop", description="Cancel a run through the guarded state machine.", input_model=RunStopInput, permission=ToolPermissionTier.HUMAN_GATE, handler=_run_stop)
        self._register(name="agent.ask_user", description="Record a human-information request in the run trace.", input_model=AskUserInput, permission=ToolPermissionTier.HUMAN_GATE, handler=_agent_ask_user)
        self._register(name="eval.record_run", description="Record an evaluation report from current platform evidence.", input_model=EvalRecordInput, permission=ToolPermissionTier.READ, handler=_eval_record_run)


class ToolExecutor:
    def __init__(self, registry: ToolRegistry | None = None) -> None:
        self.registry = registry or get_tool_registry()

    async def available_tools(self, db: AsyncSession, *, run_id: UUID | None = None) -> list[ToolDefinition]:
        if run_id is None:
            return self.registry.definitions()
        run = await db.get(AgentRun, run_id)
        if run is None:
            return self.registry.definitions()

        definitions: list[ToolDefinition] = []
        for definition in self.registry.definitions():
            blocked_reason = await self._blocked_reason(db, definition=definition, run=run)
            if blocked_reason:
                definitions.append(definition.model_copy(update={"enabled": False, "disabled_reason": blocked_reason}))
            else:
                definitions.append(definition)
        return definitions

    async def execute(self, db: AsyncSession, *, request: ToolCallRequest) -> ToolCallResult:
        started = time.monotonic()
        spec = self.registry.get(request.tool_name)
        run = await db.get(AgentRun, request.run_id)
        if run is None:
            return ToolCallResult(
                tool_name=request.tool_name,
                status=ToolCallStatus.BLOCKED,
                blocked_reason=f"Agent run not found: {request.run_id}",
                block_type=ToolBlockType.AUTH_REQUIRED,
                duration_ms=self._duration_ms(started),
            )

        if spec is None:
            result = ToolCallResult(
                tool_name=request.tool_name,
                status=ToolCallStatus.BLOCKED,
                blocked_reason="Unknown tool.",
                block_type=ToolBlockType.UNKNOWN_TOOL,
                duration_ms=self._duration_ms(started),
            )
            await self._record_result(db, run=run, request=request, result=result)
            return result

        blocked_reason = await self._blocked_reason(db, definition=spec.definition, run=run, request=request)
        if blocked_reason:
            result = ToolCallResult(
                tool_name=request.tool_name,
                status=ToolCallStatus.BLOCKED,
                blocked_reason=blocked_reason,
                block_type=self._block_type_for(blocked_reason),
                duration_ms=self._duration_ms(started),
            )
            await self._record_result(db, run=run, request=request, result=result)
            return result

        try:
            payload = spec.input_model.model_validate(request.arguments)
        except ValidationError as exc:
            result = ToolCallResult(
                tool_name=request.tool_name,
                status=ToolCallStatus.BLOCKED,
                blocked_reason=f"Invalid tool arguments: {exc.errors()}",
                block_type=ToolBlockType.POLICY_DENIED,
                duration_ms=self._duration_ms(started),
            )
            await self._record_result(db, run=run, request=request, result=result)
            return result
        payload_run_id = getattr(payload, "run_id", None)
        if payload_run_id is not None and payload_run_id != request.run_id:
            result = ToolCallResult(
                tool_name=request.tool_name,
                status=ToolCallStatus.BLOCKED,
                blocked_reason="Tool payload run_id must match the tool-call run_id.",
                block_type=ToolBlockType.POLICY_DENIED,
                duration_ms=self._duration_ms(started),
            )
            await self._record_result(db, run=run, request=request, result=result)
            return result

        try:
            if spec.handler is None:
                raise ToolBlocked(spec.definition.disabled_reason or "Tool is not implemented.", block_type=ToolBlockType.NOT_IMPLEMENTED)
            output = await spec.handler(db, request, payload)
            result = ToolCallResult(
                tool_name=request.tool_name,
                status=ToolCallStatus.SUCCEEDED,
                output=output,
                duration_ms=self._duration_ms(started),
            )
        except ToolBlocked as exc:
            result = ToolCallResult(
                tool_name=request.tool_name,
                status=ToolCallStatus.BLOCKED,
                blocked_reason=str(exc),
                block_type=exc.block_type,
                duration_ms=self._duration_ms(started),
            )
        except Exception as exc:  # Keep model-facing failures structured and auditable.
            result = ToolCallResult(
                tool_name=request.tool_name,
                status=ToolCallStatus.FAILED,
                blocked_reason=f"{exc.__class__.__name__}: {exc}",
                duration_ms=self._duration_ms(started),
            )

        await self._record_result(db, run=run, request=request, result=result)
        return result

    async def execute_batch(self, db: AsyncSession, *, requests: list[ToolCallRequest]) -> list[ToolCallResult]:
        results: list[ToolCallResult] = []
        for request in requests:
            spec = self.registry.get(request.tool_name)
            if spec is not None and spec.definition.permission != ToolPermissionTier.READ:
                run = await db.get(AgentRun, request.run_id)
                result = ToolCallResult(
                    tool_name=request.tool_name,
                    status=ToolCallStatus.BLOCKED,
                    blocked_reason="Batch execution only supports read tools.",
                    block_type=ToolBlockType.POLICY_DENIED,
                )
                if run is not None:
                    await self._record_result(db, run=run, request=request, result=result)
                results.append(result)
                continue
            results.append(await self.execute(db, request=request))
        return results

    async def _blocked_reason(
        self,
        db: AsyncSession,
        *,
        definition: ToolDefinition,
        run: AgentRun,
        request: ToolCallRequest | None = None,
    ) -> str | None:
        if not definition.enabled:
            return definition.disabled_reason or "Tool is disabled."
        if definition.requires_github_write_mode and not effective_settings(settings).github_writes_enabled:
            return "Real GitHub writes are disabled."
        if request is not None and request.state.value != run.state:
            return f"Tool call state {request.state.value} does not match current run state {run.state}."
        if definition.required_states and run.state not in {state.value for state in definition.required_states}:
            return f"Tool {definition.name} is not available while run is in state {run.state}."
        if definition.requires_approved_plan and not await self._has_approved_plan(db, run):
            return "Tool requires an approved plan."
        return None

    def _block_type_for(self, blocked_reason: str) -> ToolBlockType:
        lowered = blocked_reason.lower()
        if "approved plan" in lowered:
            return ToolBlockType.APPROVAL_REQUIRED
        if "github writes" in lowered:
            return ToolBlockType.GITHUB_WRITES_DISABLED
        if "state" in lowered or "not available while run" in lowered:
            return ToolBlockType.STATE_MISMATCH
        if "not implemented" in lowered or "disabled" in lowered:
            return ToolBlockType.NOT_IMPLEMENTED
        return ToolBlockType.POLICY_DENIED

    async def _has_approved_plan(self, db: AsyncSession, run: AgentRun) -> bool:
        if run.plan_id is None:
            return False
        plan = await db.get(Plan, run.plan_id)
        return bool(plan and plan.approval_status == PlanApprovalStatus.APPROVED.value and approved_plan_hash_matches(plan))

    async def _record_result(
        self,
        db: AsyncSession,
        *,
        run: AgentRun,
        request: ToolCallRequest,
        result: ToolCallResult,
    ) -> None:
        spec = self.registry.get(request.tool_name)
        step_output = redact_data({
            **result.model_dump(mode="json"),
            "arguments": request.arguments,
            "permission": spec.definition.permission.value if spec else None,
        })
        step_output = maybe_externalize_json(
            db,
            run_id=run.id,
            artifact_type="tool.output",
            payload=step_output,
            metadata={"tool_name": request.tool_name, "status": result.status.value},
        )
        db.add(
            AgentStep(
                run_id=run.id,
                step_name=f"TOOL_CALL:{request.tool_name}",
                output_json=step_output,
                status=result.status.value,
            )
        )
        await record_audit(
            db,
            actor_type=request.actor,
            action="tool.call",
            entity_type="agent_run",
            entity_id=str(run.id),
            metadata={
                "tool_name": request.tool_name,
                "status": result.status.value,
                "blocked_reason": result.blocked_reason,
                "block_type": result.block_type.value if result.block_type else None,
            },
        )
        await db.commit()

    def _duration_ms(self, started: float) -> int:
        return max(0, int((time.monotonic() - started) * 1000))


async def _repo_index(db: AsyncSession, _request: ToolCallRequest, payload: BaseModel) -> dict[str, Any]:
    args = _cast(payload, RepoIndexInput)
    result = await RepositoryIndexer().index_repository(
        db,
        repository_id=args.repository_id,
        request=RepositoryIndexRequest(
            source_path=args.source_path,
            commit_sha=args.commit_sha,
            max_files=args.max_files,
            max_file_bytes=args.max_file_bytes,
        ),
    )
    return result.model_dump(mode="json")


async def _repo_search_context(db: AsyncSession, _request: ToolCallRequest, payload: BaseModel) -> dict[str, Any]:
    args = _cast(payload, RepoSearchContextInput)
    context = await RepositoryIndexer().retrieve_context(db, repository_id=args.repository_id, query=args.query, limit=args.limit)
    return context.model_dump(mode="json")


async def _repo_list_files(_db: AsyncSession, request: ToolCallRequest, payload: BaseModel) -> dict[str, Any]:
    args = _cast(payload, RepoListFilesInput)
    workspace = _isolated_workspace(request.run_id, args.workspace_path)
    files: list[dict[str, Any]] = []
    for path in _iter_workspace_files(workspace):
        relative = path.relative_to(workspace).as_posix()
        if args.glob and not fnmatch.fnmatch(relative, args.glob):
            continue
        files.append({"path": relative, "size_bytes": path.stat().st_size, "is_test": _is_test_file(relative)})
        if len(files) >= args.max_files:
            break
    return {"workspace_path": str(workspace), "files": files, "truncated": len(files) >= args.max_files}


async def _repo_read_file(_db: AsyncSession, request: ToolCallRequest, payload: BaseModel) -> dict[str, Any]:
    args = _cast(payload, RepoReadFileInput)
    workspace = _isolated_workspace(request.run_id, args.workspace_path)
    return _read_workspace_file(workspace, path=args.path, start_line=args.start_line, end_line=args.end_line)


async def _repo_read_files(_db: AsyncSession, request: ToolCallRequest, payload: BaseModel) -> dict[str, Any]:
    args = _cast(payload, RepoReadFilesInput)
    workspace = _isolated_workspace(request.run_id, args.workspace_path)
    files: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for spec in args.files:
        try:
            files.append(
                _read_workspace_file(
                    workspace,
                    path=spec.path,
                    start_line=spec.start_line,
                    end_line=spec.end_line,
                )
            )
        except ToolBlocked as exc:
            errors.append({"path": spec.path, "blocked_reason": str(exc), "block_type": exc.block_type.value})
    return {
        "workspace_path": str(workspace),
        "files": files,
        "errors": errors,
        "succeeded_count": len(files),
        "blocked_count": len(errors),
    }


def _read_workspace_file(
    workspace: Path,
    *,
    path: str,
    start_line: int | None,
    end_line: int | None,
) -> dict[str, Any]:
    resolved = _child_path(workspace, path)
    relative = resolved.relative_to(workspace).as_posix()
    if _is_sensitive_workspace_path(relative):
        raise ToolBlocked(f"Refusing to read sensitive file: {relative}")
    if not resolved.is_file():
        raise ToolBlocked(f"File not found: {path}")
    if resolved.stat().st_size > MAX_READ_BYTES:
        raise ToolBlocked(f"File exceeds read limit of {MAX_READ_BYTES} bytes: {path}")
    lines = resolved.read_text(encoding="utf-8", errors="ignore").splitlines()
    start = start_line or 1
    end = end_line or len(lines)
    if end < start:
        raise ToolBlocked("end_line must be greater than or equal to start_line.")
    selected = lines[start - 1 : end]
    return {
        "path": relative,
        "start_line": start,
        "end_line": min(end, len(lines)),
        "line_count": len(lines),
        "content": "\n".join(selected),
    }


async def _repo_grep(_db: AsyncSession, request: ToolCallRequest, payload: BaseModel) -> dict[str, Any]:
    args = _cast(payload, RepoGrepInput)
    workspace = _isolated_workspace(request.run_id, args.workspace_path)
    query = args.query.lower()
    matches: list[dict[str, Any]] = []
    for path in _iter_workspace_files(workspace):
        relative = path.relative_to(workspace).as_posix()
        if args.glob and not fnmatch.fnmatch(relative, args.glob):
            continue
        if path.stat().st_size > MAX_READ_BYTES:
            continue
        for line_number, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
            if query in line.lower():
                matches.append({"path": relative, "line": line_number, "text": line[:500]})
                if len(matches) >= args.max_results:
                    return {"query": args.query, "matches": matches, "truncated": True}
    return {"query": args.query, "matches": matches, "truncated": False}


async def _repo_summarize_tree(_db: AsyncSession, request: ToolCallRequest, payload: BaseModel) -> dict[str, Any]:
    args = _cast(payload, RepoSummarizeTreeInput)
    workspace = _isolated_workspace(request.run_id, args.workspace_path)
    entries: list[str] = []
    suffix_counts: dict[str, int] = {}
    corpus_signals: list[str] = []
    for path in _iter_workspace_files(workspace):
        relative = path.relative_to(workspace)
        if len(relative.parts) > args.max_depth:
            continue
        rel = relative.as_posix()
        entries.append(rel)
        suffix = path.suffix.lower() or "no_extension"
        suffix_counts[suffix] = suffix_counts.get(suffix, 0) + 1
        if path.stat().st_size <= 20_000 and len(corpus_signals) < 50:
            corpus_signals.append(path.read_text(encoding="utf-8", errors="ignore")[:1200].lower())
        if len(entries) >= 300:
            break
    corpus = "\n".join(corpus_signals)
    return {
        "workspace_path": str(workspace),
        "entries": sorted(entries),
        "language_counts": suffix_counts,
        "frameworks": _framework_hints(corpus),
        "truncated": len(entries) >= 300,
    }


async def _issue_triage(db: AsyncSession, _request: ToolCallRequest, payload: BaseModel) -> dict[str, Any]:
    args = _cast(payload, IssueTriageInput)
    issue = await db.get(Issue, args.issue_id)
    if issue is None:
        raise ToolBlocked(f"Issue not found: {args.issue_id}")
    result = TriageService().triage(issue_id=str(issue.id), title=issue.title, body=args.body)
    return result.model_dump(mode="json")


async def _plan_generate(db: AsyncSession, _request: ToolCallRequest, payload: BaseModel) -> dict[str, Any]:
    args = _cast(payload, PlanGenerateInput)
    plan, run = await PlanningService().generate_plan(db, issue_id=args.issue_id, context_limit=args.context_limit)
    return {"plan_id": str(plan.id), "run_id": str(run.id), "plan": plan.plan_json}


async def _plan_evaluate_policy(db: AsyncSession, _request: ToolCallRequest, payload: BaseModel) -> dict[str, Any]:
    args = _cast(payload, PlanIdInput)
    plan = await db.get(Plan, args.plan_id)
    if plan is None:
        raise ToolBlocked(f"Plan not found: {args.plan_id}")
    decision = PolicyEngine().evaluate_plan(implementation_plan_from_db(plan))
    return decision.model_dump(mode="json")


async def _plan_request_approval(db: AsyncSession, request: ToolCallRequest, payload: BaseModel) -> dict[str, Any]:
    args = _cast(payload, PlanRequestApprovalInput)
    plan = await db.get(Plan, args.plan_id)
    if plan is None:
        raise ToolBlocked(f"Plan not found: {args.plan_id}")
    if plan.approval_status == PlanApprovalStatus.DRAFT.value:
        plan.approval_status = PlanApprovalStatus.WAITING.value
    decision = PolicyEngine().evaluate_plan(implementation_plan_from_db(plan))
    await record_audit(
        db,
        actor_type=request.actor,
        action="plan.approval_requested",
        entity_type="plan",
        entity_id=str(plan.id),
        metadata={"summary": args.summary, "policy": decision.decision.value},
    )
    return {"plan_id": str(plan.id), "approval_status": plan.approval_status, "policy_decision": decision.model_dump(mode="json")}


async def _workspace_create_run_copy(_db: AsyncSession, request: ToolCallRequest, payload: BaseModel) -> dict[str, Any]:
    args = _cast(payload, CreateRunCopyInput)
    if args.run_id != request.run_id:
        raise ToolBlocked("Payload run_id must match the tool-call run_id.")
    source = _repository_workspace(args.source_workspace)
    target = WORKSPACE_ROOT / str(request.run_id)
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target, ignore=_copy_ignore)
    _write_baseline(target)
    return {"source_workspace": str(source), "working_workspace_path": str(target)}


async def _workspace_diff(_db: AsyncSession, request: ToolCallRequest, payload: BaseModel) -> dict[str, Any]:
    args = _cast(payload, WorkspacePathInput)
    workspace = _isolated_workspace(request.run_id, args.workspace_path)
    return _workspace_diff_payload(workspace)


async def _workspace_apply_patch(db: AsyncSession, request: ToolCallRequest, payload: BaseModel) -> dict[str, Any]:
    args = _cast(payload, ApplyPatchInput)
    workspace = _isolated_workspace(request.run_id, args.workspace_path)
    changed_paths = _diff_paths(args.diff)
    if not changed_paths:
        raise ToolBlocked("Patch does not include file paths.")
    if len(changed_paths) > args.max_changed_files:
        raise ToolBlocked("Patch changes more files than max_changed_files.")
    for rel in changed_paths:
        _assert_safe_write_path(workspace, rel)
        await _assert_plan_allows_write_path(db, run_id=request.run_id, relative_path=rel)

    completed = subprocess.run(
        ["git", "apply", "--whitespace=nowarn", "-"],
        cwd=workspace,
        input=args.diff,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if completed.returncode != 0:
        raise ToolBlocked(f"git apply failed: {completed.stderr[-1000:]}")
    if not args.return_diff:
        return {"changed_paths": sorted(changed_paths)}
    diff_payload = _workspace_diff_payload(workspace)
    return {"changed_paths": sorted(changed_paths), **diff_payload}


async def _workspace_write_file(db: AsyncSession, request: ToolCallRequest, payload: BaseModel) -> dict[str, Any]:
    args = _cast(payload, WriteFileInput)
    workspace = _isolated_workspace(request.run_id, args.workspace_path)
    path = _assert_safe_write_path(workspace, args.path)
    await _assert_plan_allows_write_path(db, run_id=request.run_id, relative_path=path.relative_to(workspace).as_posix())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(args.content, encoding="utf-8")
    return {"path": path.relative_to(workspace).as_posix(), "bytes_written": len(args.content.encode("utf-8"))}


async def _workspace_replace_text(db: AsyncSession, request: ToolCallRequest, payload: BaseModel) -> dict[str, Any]:
    args = _cast(payload, ReplaceTextInput)
    workspace = _isolated_workspace(request.run_id, args.workspace_path)
    path = _assert_safe_write_path(workspace, args.path)
    await _assert_plan_allows_write_path(db, run_id=request.run_id, relative_path=path.relative_to(workspace).as_posix())
    if not path.is_file():
        raise ToolBlocked(f"File not found: {args.path}")
    text = path.read_text(encoding="utf-8")
    count = text.count(args.old_text)
    if count != 1:
        raise ToolBlocked(f"Expected exactly one match for old_text, found {count}.")
    path.write_text(text.replace(args.old_text, args.new_text, 1), encoding="utf-8")
    return {"path": path.relative_to(workspace).as_posix(), "replacements": 1}


async def _workspace_discard(_db: AsyncSession, request: ToolCallRequest, payload: BaseModel) -> dict[str, Any]:
    args = _cast(payload, DiscardWorkspaceInput)
    if args.run_id != request.run_id:
        raise ToolBlocked("Payload run_id must match the tool-call run_id.")
    target = WORKSPACE_ROOT / str(request.run_id)
    if not target.exists():
        return {"discarded": False, "workspace_path": str(target)}
    shutil.rmtree(target)
    return {"discarded": True, "workspace_path": str(target)}


async def _sandbox_run_command(db: AsyncSession, request: ToolCallRequest, payload: BaseModel) -> dict[str, Any]:
    args = _cast(payload, SandboxCommandInput)
    result = SandboxRunner().run_command(
        SandboxCommandRequest(workspace_path=args.workspace_path, command=args.command, timeout_seconds=args.timeout_seconds),
        run_id=request.run_id,
    )
    _persist_validation_result(
        db,
        run_id=request.run_id,
        command=result.command,
        status=result.status,
        duration_ms=result.duration_ms,
        summary=result.blocked_reason or f"exit_code={result.exit_code}",
        stdout=result.stdout,
        stderr=result.stderr,
    )
    return result.model_dump(mode="json")


async def _validation_run_tests(db: AsyncSession, request: ToolCallRequest, payload: BaseModel) -> dict[str, Any]:
    args = _cast(payload, ValidationRunInput)
    command = args.command or await _plan_command(db, run_id=request.run_id, fallback="pytest")
    return await _run_validation_command(db, request=request, workspace_path=args.workspace_path, command=command, timeout_seconds=args.timeout_seconds)


async def _validation_run_lint(db: AsyncSession, request: ToolCallRequest, payload: BaseModel) -> dict[str, Any]:
    args = _cast(payload, ValidationRunInput)
    command = args.command or _default_lint_command(args.workspace_path)
    return await _run_validation_command(db, request=request, workspace_path=args.workspace_path, command=command, timeout_seconds=args.timeout_seconds)


async def _validation_run_typecheck(db: AsyncSession, request: ToolCallRequest, payload: BaseModel) -> dict[str, Any]:
    args = _cast(payload, ValidationRunInput)
    command = args.command or _default_typecheck_command(args.workspace_path)
    return await _run_validation_command(db, request=request, workspace_path=args.workspace_path, command=command, timeout_seconds=args.timeout_seconds)


async def _validation_record_result(db: AsyncSession, request: ToolCallRequest, payload: BaseModel) -> dict[str, Any]:
    args = _cast(payload, ValidationRecordInput)
    _persist_validation_result(
        db,
        run_id=request.run_id,
        command=args.command,
        status=args.status,
        duration_ms=args.duration_ms,
        summary=args.summary or f"status={args.status.value}",
        stdout=args.stdout,
        stderr=args.stderr,
    )
    return {"run_id": str(request.run_id), "command": args.command, "status": args.status.value, "summary": args.summary}


async def _security_scan_patch(db: AsyncSession, request: ToolCallRequest, payload: BaseModel) -> dict[str, Any]:
    args = _cast(payload, SecurityScanPatchInput)
    workspace_path = str(_isolated_workspace(request.run_id, args.workspace_path)) if args.workspace_path else None
    result = await SecurityScanner().scan_run(
        db,
        run_id=request.run_id,
        request=SecurityScanRequest(workspace_path=workspace_path, fail_on_findings=args.fail_on_findings),
    )
    return result.model_dump(mode="json")


async def _security_scan_workspace(db: AsyncSession, request: ToolCallRequest, payload: BaseModel) -> dict[str, Any]:
    args = _cast(payload, SecurityScanWorkspaceInput)
    workspace = _isolated_workspace(request.run_id, args.workspace_path)
    result = await SecurityScanner().scan_run(
        db,
        run_id=request.run_id,
        request=SecurityScanRequest(workspace_path=str(workspace), fail_on_findings=args.fail_on_findings),
    )
    return result.model_dump(mode="json")


async def _security_explain_findings(db: AsyncSession, request: ToolCallRequest, payload: BaseModel) -> dict[str, Any]:
    _cast(payload, RunIdInput)
    result = await db.execute(select(SecurityFinding).where(SecurityFinding.run_id == request.run_id))
    findings = result.scalars().all()
    by_severity: dict[str, int] = {}
    for finding in findings:
        by_severity[finding.severity] = by_severity.get(finding.severity, 0) + 1
    return {
        "run_id": str(request.run_id),
        "finding_count": len(findings),
        "by_severity": by_severity,
        "findings": [
            {
                "tool": finding.tool,
                "severity": finding.severity,
                "file_path": finding.file_path,
                "description": finding.description,
                "status": finding.status,
            }
            for finding in findings
        ],
    }


async def _security_semgrep(db: AsyncSession, request: ToolCallRequest, payload: BaseModel) -> dict[str, Any]:
    args = _cast(payload, SecurityScanWorkspaceInput)
    workspace = _isolated_workspace(request.run_id, args.workspace_path)
    if not settings.semgrep_enabled:
        return {
            "run_id": str(request.run_id),
            "adapter": "semgrep",
            "status": ValidationStatus.SKIPPED.value,
            "workspace_path": str(workspace),
            "summary": "SEMGREP_ENABLED is false; Semgrep adapter skipped.",
        }
    command_result = _run_security_command(["semgrep", "--config", "auto", "--json", "--quiet", "."], workspace=workspace, timeout_seconds=120)
    findings = _parse_semgrep_findings(run_id=request.run_id, output=command_result["stdout"])
    if command_result["status"] == "tool_unavailable":
        findings.append(
            _security_finding_payload(
                run_id=request.run_id,
                tool="semgrep",
                severity=SecuritySeverity.HIGH,
                file_path=None,
                description="SEMGREP_ENABLED is true, but the semgrep executable is unavailable in the runtime.",
            )
        )
    elif command_result["returncode"] not in {0, 1}:
        findings.append(
            _security_finding_payload(
                run_id=request.run_id,
                tool="semgrep",
                severity=SecuritySeverity.HIGH,
                file_path=None,
                description=f"Semgrep command failed: {redact_text(command_result['stderr'])[:300] or 'no stderr'}",
            )
        )
    await _persist_adapter_findings(db, run_id=request.run_id, findings=findings)
    blocked = args.fail_on_findings and any(_severity_score(str(finding["severity"])) >= _severity_score(SecuritySeverity.HIGH.value) for finding in findings)
    status = ValidationStatus.FAILED.value if blocked else ValidationStatus.PASSED.value
    return {
        "run_id": str(request.run_id),
        "adapter": "semgrep",
        "status": status,
        "workspace_path": str(workspace),
        "command": command_result["command"],
        "returncode": command_result["returncode"],
        "finding_count": len(findings),
        "findings": findings[:50],
        "summary": f"Semgrep adapter completed with {len(findings)} finding(s).",
    }


async def _security_dependency_audit(db: AsyncSession, request: ToolCallRequest, payload: BaseModel) -> dict[str, Any]:
    args = _cast(payload, SecurityScanWorkspaceInput)
    workspace = _isolated_workspace(request.run_id, args.workspace_path)
    manifests = [
        path.relative_to(workspace).as_posix()
        for path in workspace.rglob("*")
        if path.is_file() and path.name in {"package-lock.json", "pnpm-lock.yaml", "yarn.lock", "requirements.txt", "poetry.lock", "uv.lock", "go.sum"}
    ]
    if not settings.dependency_audit_enabled:
        return {
            "run_id": str(request.run_id),
            "adapter": "dependency_audit",
            "status": ValidationStatus.SKIPPED.value,
            "manifest_count": len(manifests),
            "manifests": manifests[:20],
            "summary": "DEPENDENCY_AUDIT_ENABLED is false; dependency audit skipped.",
        }
    audit_results = _run_dependency_audits(run_id=request.run_id, workspace=workspace, manifests=manifests)
    findings = [finding for result in audit_results for finding in result["findings"]]
    await _persist_adapter_findings(db, run_id=request.run_id, findings=findings)
    blocked = args.fail_on_findings and any(_severity_score(str(finding["severity"])) >= _severity_score(SecuritySeverity.HIGH.value) for finding in findings)
    status = ValidationStatus.FAILED.value if blocked else ValidationStatus.PASSED.value
    return {
        "run_id": str(request.run_id),
        "adapter": "dependency_audit",
        "status": status,
        "manifest_count": len(manifests),
        "manifests": manifests[:20],
        "results": audit_results,
        "finding_count": len(findings),
        "findings": findings[:50],
        "summary": f"Dependency audit adapter completed with {len(findings)} finding(s) across {len(manifests)} manifest(s).",
    }


def _run_security_command(command: list[str], *, workspace: Path, timeout_seconds: int) -> dict[str, Any]:
    executable = shutil.which(command[0])
    command_text = " ".join(command)
    if executable is None:
        return {
            "command": command_text,
            "status": "tool_unavailable",
            "returncode": 127,
            "stdout": "",
            "stderr": f"{command[0]} executable is not available.",
        }
    try:
        completed = subprocess.run(
            command,
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command_text,
            "status": "timeout",
            "returncode": 124,
            "stdout": redact_text(exc.stdout or ""),
            "stderr": redact_text(exc.stderr or "command timed out"),
        }
    return {
        "command": command_text,
        "status": "completed",
        "returncode": completed.returncode,
        "stdout": redact_text(completed.stdout or ""),
        "stderr": redact_text(completed.stderr or ""),
    }


def _parse_semgrep_findings(*, run_id: UUID, output: str) -> list[dict[str, Any]]:
    if not output.strip():
        return []
    try:
        payload = json.loads(output or "{}")
    except json.JSONDecodeError:
        return [
            _security_finding_payload(
                run_id=run_id,
                tool="semgrep",
                severity=SecuritySeverity.MEDIUM,
                file_path=None,
                description="Semgrep returned non-JSON output.",
            )
        ]
    results = payload.get("results") if isinstance(payload, dict) else []
    findings: list[dict[str, Any]] = []
    for item in results if isinstance(results, list) else []:
        if not isinstance(item, dict):
            continue
        extra = item.get("extra") if isinstance(item.get("extra"), dict) else {}
        findings.append(
            _security_finding_payload(
                run_id=run_id,
                tool="semgrep",
                severity=_semgrep_severity(str(extra.get("severity") or "")),
                file_path=str(item.get("path") or "") or None,
                description=str(extra.get("message") or item.get("check_id") or "Semgrep finding."),
            )
        )
    return findings


def _run_dependency_audits(*, run_id: UUID, workspace: Path, manifests: list[str]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    manifest_set = set(manifests)
    if "package-lock.json" in manifest_set:
        command_result = _run_security_command(["npm", "audit", "--audit-level=moderate", "--json"], workspace=workspace, timeout_seconds=120)
        findings = _parse_npm_audit_findings(run_id=run_id, output=command_result["stdout"])
        if command_result["status"] == "tool_unavailable":
            findings.append(_security_finding_payload(run_id=run_id, tool="dependency-audit", severity=SecuritySeverity.HIGH, file_path="package-lock.json", description="DEPENDENCY_AUDIT_ENABLED is true, but npm is unavailable."))
        elif command_result["returncode"] not in {0, 1} and not findings:
            findings.append(_security_finding_payload(run_id=run_id, tool="dependency-audit", severity=SecuritySeverity.HIGH, file_path="package-lock.json", description=f"npm audit failed: {redact_text(command_result['stderr'])[:300] or 'no stderr'}"))
        results.append({"manifest": "package-lock.json", **_command_public_result(command_result), "findings": findings[:50]})
    python_manifests = [manifest for manifest in manifests if manifest in {"requirements.txt", "poetry.lock", "uv.lock"}]
    if python_manifests:
        command_result = _run_security_command(["pip-audit", "--format", "json"], workspace=workspace, timeout_seconds=120)
        findings = _parse_pip_audit_findings(run_id=run_id, output=command_result["stdout"], manifests=python_manifests)
        if command_result["status"] == "tool_unavailable":
            findings.append(_security_finding_payload(run_id=run_id, tool="dependency-audit", severity=SecuritySeverity.HIGH, file_path=python_manifests[0], description="DEPENDENCY_AUDIT_ENABLED is true, but pip-audit is unavailable."))
        elif command_result["returncode"] not in {0, 1} and not findings:
            findings.append(_security_finding_payload(run_id=run_id, tool="dependency-audit", severity=SecuritySeverity.HIGH, file_path=python_manifests[0], description=f"pip-audit failed: {redact_text(command_result['stderr'])[:300] or 'no stderr'}"))
        results.append({"manifest": ",".join(python_manifests), **_command_public_result(command_result), "findings": findings[:50]})
    unsupported = sorted(manifest for manifest in manifest_set - {"package-lock.json", "requirements.txt", "poetry.lock", "uv.lock"})
    for manifest in unsupported:
        results.append(
            {
                "manifest": manifest,
                "command": None,
                "returncode": None,
                "status": "skipped",
                "findings": [],
                "summary": "No local dependency-audit adapter is configured for this manifest type.",
            }
        )
    if not results:
        results.append({"manifest": None, "command": None, "returncode": None, "status": "skipped", "findings": [], "summary": "No dependency manifests were found."})
    return results


def _parse_npm_audit_findings(*, run_id: UUID, output: str) -> list[dict[str, Any]]:
    try:
        payload = json.loads(output or "{}")
    except json.JSONDecodeError:
        return []
    vulnerabilities = payload.get("vulnerabilities") if isinstance(payload, dict) else {}
    findings: list[dict[str, Any]] = []
    if not isinstance(vulnerabilities, dict):
        return findings
    for package_name, info in vulnerabilities.items():
        if not isinstance(info, dict):
            continue
        severity = _npm_severity(str(info.get("severity") or "medium"))
        via = info.get("via")
        advisory = via[0] if isinstance(via, list) and via and isinstance(via[0], dict) else {}
        title = str(advisory.get("title") or f"Vulnerability reported for {package_name}.")
        findings.append(_security_finding_payload(run_id=run_id, tool="dependency-audit", severity=severity, file_path="package-lock.json", description=f"{package_name}: {title}"))
    return findings


def _parse_pip_audit_findings(*, run_id: UUID, output: str, manifests: list[str]) -> list[dict[str, Any]]:
    try:
        payload = json.loads(output or "{}")
    except json.JSONDecodeError:
        return []
    dependencies = payload.get("dependencies") if isinstance(payload, dict) else []
    findings: list[dict[str, Any]] = []
    for dependency in dependencies if isinstance(dependencies, list) else []:
        if not isinstance(dependency, dict):
            continue
        vulnerabilities = dependency.get("vulns") or dependency.get("vulnerabilities") or []
        for vuln in vulnerabilities if isinstance(vulnerabilities, list) else []:
            if not isinstance(vuln, dict):
                continue
            vuln_id = str(vuln.get("id") or vuln.get("aliases") or "vulnerability")
            description = str(vuln.get("description") or vuln.get("fix_versions") or "Python dependency vulnerability reported.")
            findings.append(_security_finding_payload(run_id=run_id, tool="dependency-audit", severity=SecuritySeverity.HIGH, file_path=manifests[0], description=f"{dependency.get('name')}: {vuln_id} - {description[:220]}"))
    return findings


async def _persist_adapter_findings(db: AsyncSession, *, run_id: UUID, findings: list[dict[str, Any]]) -> None:
    for finding in findings:
        db.add(
            SecurityFinding(
                run_id=run_id,
                tool=str(finding["tool"]),
                severity=str(finding["severity"]),
                file_path=finding.get("file_path"),
                description=str(finding["description"]),
                status="open",
            )
        )


def _security_finding_payload(*, run_id: UUID, tool: str, severity: SecuritySeverity, file_path: str | None, description: str) -> dict[str, Any]:
    return {
        "run_id": str(run_id),
        "tool": tool,
        "severity": severity.value,
        "file_path": file_path,
        "description": description,
        "status": "open",
    }


def _semgrep_severity(value: str) -> SecuritySeverity:
    normalized = value.lower()
    if normalized in {"error", "critical", "high"}:
        return SecuritySeverity.HIGH
    if normalized in {"warning", "medium"}:
        return SecuritySeverity.MEDIUM
    return SecuritySeverity.LOW


def _npm_severity(value: str) -> SecuritySeverity:
    normalized = value.lower()
    if normalized == "critical":
        return SecuritySeverity.CRITICAL
    if normalized == "high":
        return SecuritySeverity.HIGH
    if normalized == "moderate":
        return SecuritySeverity.MEDIUM
    return SecuritySeverity.LOW


def _severity_score(value: str) -> int:
    scores = {"info": 0, "low": 10, "medium": 40, "high": 70, "critical": 100}
    return scores.get(value.lower(), 0)


def _command_public_result(command_result: dict[str, Any]) -> dict[str, Any]:
    stderr = str(command_result.get("stderr") or "")
    return {
        "command": command_result.get("command"),
        "returncode": command_result.get("returncode"),
        "status": command_result.get("status"),
        "summary": stderr[:300] if stderr else "Command completed.",
    }


async def _pr_open_draft_record(db: AsyncSession, request: ToolCallRequest, payload: BaseModel) -> dict[str, Any]:
    args = _cast(payload, DraftPrInput)
    result = await DraftPullRequestService().open_draft_pr(
        db,
        run_id=request.run_id,
        request=DraftPullRequestRequest(
            title=args.title,
            body=args.body,
            base_branch=args.base_branch,
            branch_prefix=args.branch_prefix,
        ),
    )
    return result.model_dump(mode="json")


async def _ci_analyze(db: AsyncSession, _request: ToolCallRequest, payload: BaseModel) -> dict[str, Any]:
    args = _cast(payload, CiAnalyzeInput)
    result = await CIAnalyzer().analyze_pr(
        db,
        pr_id=args.pr_id,
        request=CIAnalysisRequest(workflow_name=args.workflow_name, conclusion=args.conclusion, log_text=args.log_text),
    )
    return result.model_dump(mode="json")


async def _github_create_branch(db: AsyncSession, _request: ToolCallRequest, payload: BaseModel) -> dict[str, Any]:
    args = _cast(payload, GithubCreateBranchInput)
    repository, installation = await _repository_and_installation(db, repository_id=args.repository_id)
    result = await _github_call(
        GitHubApiClient().create_branch(
            installation_id=installation.github_installation_id,
            owner=repository.owner,
            repo=repository.name,
            branch_name=args.branch_name,
            base_sha=args.base_sha,
        )
    )
    return {"repository_id": str(repository.id), "branch_name": args.branch_name, "base_sha": args.base_sha, "github_response": result}


async def _github_commit_patch(db: AsyncSession, request: ToolCallRequest, payload: BaseModel) -> dict[str, Any]:
    args = _cast(payload, GithubCommitPatchInput)
    repository, installation = await _repository_and_installation(db, repository_id=args.repository_id)
    patch_payload = await _latest_patch_payload(db, run_id=request.run_id)
    if not patch_payload:
        raise ToolBlocked("GitHub commit requires a captured patch payload.")
    if str(patch_payload.get("patch_hash") or "") != args.diff_hash:
        raise ToolBlocked("GitHub commit diff_hash does not match the latest captured patch.")
    head_sha = await _github_call(
        GitHubApiClient().commit_patch(
            installation_id=installation.github_installation_id,
            owner=repository.owner,
            repo=repository.name,
            branch_name=args.branch_name,
            message=args.message,
            changed_files=_changed_file_contents(patch_payload),
        )
    )
    return {"repository_id": str(repository.id), "branch_name": args.branch_name, "head_sha": head_sha, "diff_hash": args.diff_hash}


async def _github_open_pull_request(db: AsyncSession, _request: ToolCallRequest, payload: BaseModel) -> dict[str, Any]:
    args = _cast(payload, GithubOpenPullRequestInput)
    repository, installation = await _repository_and_installation(db, repository_id=args.repository_id)
    result = await _github_call(
        GitHubApiClient().open_pull_request(
            installation_id=installation.github_installation_id,
            owner=repository.owner,
            repo=repository.name,
            branch_name=args.branch_name,
            base_branch=args.base_branch,
            title=args.title,
            body=args.body,
            draft=True,
        )
    )
    return {
        "repository_id": str(repository.id),
        "pr_number": result.get("number"),
        "url": result.get("html_url") or result.get("url"),
        "branch_name": args.branch_name,
    }


async def _github_comment_issue(db: AsyncSession, _request: ToolCallRequest, payload: BaseModel) -> dict[str, Any]:
    args = _cast(payload, GithubCommentIssueInput)
    repository, installation = await _repository_and_installation(db, repository_id=args.repository_id)
    result = await _github_call(
        GitHubApiClient().comment_issue(
            installation_id=installation.github_installation_id,
            owner=repository.owner,
            repo=repository.name,
            issue_number=args.issue_number,
            body=args.body,
        )
    )
    return {"repository_id": str(repository.id), "issue_number": args.issue_number, "comment_url": result.get("html_url") or result.get("url")}


async def _github_fetch_ci_logs(db: AsyncSession, _request: ToolCallRequest, payload: BaseModel) -> dict[str, Any]:
    args = _cast(payload, GithubFetchCiLogsInput)
    repository, installation = await _repository_and_installation(db, repository_id=args.repository_id)
    client = GitHubApiClient()
    result = await _github_call(
        client.fetch_check_runs(
            installation_id=installation.github_installation_id,
            owner=repository.owner,
            repo=repository.name,
            ref=f"pull/{args.pr_number}/head",
        )
    )
    summary = client.summarize_check_runs(result)
    annotation_fetches = 0
    for check in summary["check_runs"]:
        check_run_id = check.get("id")
        if not check_run_id or int(check.get("annotations_count") or 0) <= 0 or annotation_fetches >= 5:
            continue
        annotations = await _github_call(
            client.fetch_check_run_annotations(
                installation_id=installation.github_installation_id,
                owner=repository.owner,
                repo=repository.name,
                check_run_id=int(check_run_id),
            )
        )
        check["annotations"] = client.summarize_check_annotations(annotations)
        annotation_fetches += 1
    return {
        "repository_id": str(repository.id),
        "pr_number": args.pr_number,
        "check_summary": summary,
        "annotation_fetches": annotation_fetches,
    }


async def _run_get_trace(db: AsyncSession, request: ToolCallRequest, payload: BaseModel) -> dict[str, Any]:
    _cast(payload, RunIdInput)
    return await ObservabilityService().run_trace(db, run_id=request.run_id)


async def _run_next_states(db: AsyncSession, request: ToolCallRequest, payload: BaseModel) -> dict[str, Any]:
    _cast(payload, RunIdInput)
    run = await db.get(AgentRun, request.run_id)
    if run is None:
        raise ToolBlocked(f"Agent run not found: {request.run_id}")
    return {"run_id": str(run.id), "state": run.state, "next_states": next_states(run.state)}


async def _run_transition(db: AsyncSession, request: ToolCallRequest, payload: BaseModel) -> dict[str, Any]:
    if request.actor not in {"user", "system"}:
        raise ToolBlocked("run.transition requires a user or system actor.")
    args = _cast(payload, RunTransitionInput)
    run = await db.get(AgentRun, request.run_id)
    if run is None:
        raise ToolBlocked(f"Agent run not found: {request.run_id}")
    await transition_run(db, run=run, next_state=args.next_state, actor_type=request.actor, reason=args.reason)
    return {"run_id": str(run.id), "state": run.state}


async def _run_stop(db: AsyncSession, request: ToolCallRequest, payload: BaseModel) -> dict[str, Any]:
    if request.actor not in {"user", "system"}:
        raise ToolBlocked("run.stop requires a user or system actor.")
    args = _cast(payload, RunStopInput)
    run = await db.get(AgentRun, request.run_id)
    if run is None:
        raise ToolBlocked(f"Agent run not found: {request.run_id}")
    await transition_run(db, run=run, next_state=AgentRunState.CANCELLED, actor_type=request.actor, reason=args.reason)
    return {"run_id": str(run.id), "state": run.state}


async def _agent_ask_user(_db: AsyncSession, request: ToolCallRequest, payload: BaseModel) -> dict[str, Any]:
    args = _cast(payload, AskUserInput)
    return {"run_id": str(request.run_id), "question": args.question, "choices": args.choices, "status": "recorded"}


async def _eval_record_run(db: AsyncSession, _request: ToolCallRequest, payload: BaseModel) -> dict[str, Any]:
    args = _cast(payload, EvalRecordInput)
    result = await EvalRunner().run(
        db,
        request=EvalRunRequest(benchmark_version=args.benchmark_version, task_count=args.task_count, model_config=args.model_settings),
    )
    return result.model_dump(mode="json")


async def _run_validation_command(
    db: AsyncSession,
    *,
    request: ToolCallRequest,
    workspace_path: str,
    command: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    command = _normalize_validation_command(command)
    result = SandboxRunner().run_command(
        SandboxCommandRequest(workspace_path=workspace_path, command=command, timeout_seconds=timeout_seconds),
        run_id=request.run_id,
    )
    _persist_validation_result(
        db,
        run_id=request.run_id,
        command=result.command,
        status=result.status,
        duration_ms=result.duration_ms,
        summary=result.blocked_reason or f"exit_code={result.exit_code}",
        stdout=result.stdout,
        stderr=result.stderr,
    )
    return result.model_dump(mode="json")


async def _plan_command(db: AsyncSession, *, run_id: UUID, fallback: str) -> str:
    run = await db.get(AgentRun, run_id)
    if run and run.plan_id:
        plan = await db.get(Plan, run.plan_id)
        if plan:
            implementation_plan = implementation_plan_from_db(plan)
            if implementation_plan.commands_to_run:
                return _normalize_validation_command(implementation_plan.commands_to_run[0])
    return fallback


def _normalize_validation_command(command: str) -> str:
    normalized = " ".join(command.split())
    if normalized == "pytest" or normalized.startswith("pytest "):
        return f"python -m {normalized}"
    if normalized == "python3 -m pytest" or normalized.startswith("python3 -m pytest "):
        return f"python{normalized.removeprefix('python3')}"
    return normalized


def _persist_validation_result(
    db: AsyncSession,
    *,
    run_id: UUID,
    command: str,
    status: ValidationStatus,
    duration_ms: int,
    summary: str,
    stdout: str = "",
    stderr: str = "",
) -> None:
    redacted_summary = redact_text(summary)
    redacted_stdout = redact_text(stdout)
    redacted_stderr = redact_text(stderr)
    evidence_hash = stable_json_hash(
        {
            "command": command,
            "status": status.value,
            "summary": redacted_summary,
            "stdout": redacted_stdout,
            "stderr": redacted_stderr,
        }
    )
    artifact = ArtifactStore().write_json(
        db,
        run_id=run_id,
        artifact_type="validation.log",
        payload={
            "command": command,
            "status": status.value,
            "summary": redacted_summary,
            "stdout": redacted_stdout,
            "stderr": redacted_stderr,
            "duration_ms": duration_ms,
            "evidence_hash": evidence_hash,
        },
        metadata={"source": "tool_registry"},
    )
    db.add(
        DbValidationResult(
            run_id=run_id,
            command=command,
            status=status.value,
            duration_ms=duration_ms,
            parsed_summary=redacted_summary,
            log_uri=artifact.uri,
            evidence_hash=evidence_hash,
        )
    )


async def _repository_and_installation(db: AsyncSession, *, repository_id: UUID) -> tuple[Repository, Installation]:
    repository = await db.get(Repository, repository_id)
    if repository is None:
        raise ToolBlocked(f"Repository not found: {repository_id}")
    installation = await db.get(Installation, repository.installation_id)
    if installation is None:
        raise ToolBlocked("Repository has no linked GitHub App installation.")
    return repository, installation


async def _latest_patch_payload(db: AsyncSession, *, run_id: UUID) -> dict[str, object] | None:
    result = await db.execute(
        select(AgentStep)
        .where(AgentStep.run_id == run_id, AgentStep.step_name == AgentRunState.IMPLEMENT_PATCH.value)
        .order_by(AgentStep.created_at.desc())
    )
    step = result.scalars().first()
    if not step or not isinstance(step.output_json, dict):
        return None
    return step.output_json


def _changed_file_contents(patch_payload: dict[str, object]) -> list[dict[str, str | None]]:
    workspace = Path(str(patch_payload.get("working_workspace_path") or "")).expanduser()
    changed_files: list[dict[str, str | None]] = []
    for change in patch_payload.get("changed_files", []):
        if not isinstance(change, dict):
            continue
        relative_path = str(change.get("path") or "")
        if not relative_path:
            continue
        candidate = workspace / relative_path
        content = candidate.read_text(encoding="utf-8", errors="ignore") if candidate.is_file() else None
        changed_files.append({"path": relative_path, "content": content})
    if not changed_files:
        raise ToolBlocked("GitHub commit requires at least one changed file from the latest patch.")
    return changed_files


async def _github_call(awaitable):
    try:
        return await awaitable
    except GitHubIntegrationError as exc:
        raise ToolBlocked(str(exc), block_type=ToolBlockType.GITHUB_WRITES_DISABLED) from exc


def _cast(payload: BaseModel, model_type: type[BaseModel]) -> Any:
    if not isinstance(payload, model_type):
        raise TypeError(f"Expected {model_type.__name__}, got {type(payload).__name__}")
    return payload


def _workspace(workspace_path: str) -> Path:
    workspace = Path(workspace_path).expanduser().resolve()
    if not workspace.exists() or not workspace.is_dir():
        raise ToolBlocked(f"Workspace path is not a directory: {workspace}")
    return workspace


def _repository_workspace(workspace_path: str) -> Path:
    workspace = _workspace(workspace_path)
    root = Path(settings.repository_workspace_root).expanduser().resolve()
    if not workspace.is_relative_to(root):
        raise ToolBlocked(f"Repository workspace is outside the configured repository workspace root: {root}")
    return workspace


def _isolated_workspace(run_id: UUID, workspace_path: str) -> Path:
    workspace = _workspace(workspace_path)
    expected = (WORKSPACE_ROOT / str(run_id)).resolve()
    if workspace != expected:
        raise ToolBlocked(f"Workspace write tools may only target isolated run workspace: {expected}")
    return workspace


def _child_path(workspace: Path, relative_path: str) -> Path:
    normalized = PurePosixPath(relative_path.replace("\\", "/"))
    if normalized.is_absolute() or ".." in normalized.parts:
        raise ToolBlocked(f"Unsafe relative path: {relative_path}")
    candidate = (workspace / normalized.as_posix()).resolve()
    if not candidate.is_relative_to(workspace):
        raise ToolBlocked(f"Path escapes workspace: {relative_path}")
    return candidate


def _assert_safe_write_path(workspace: Path, relative_path: str) -> Path:
    path = _child_path(workspace, relative_path)
    rel = path.relative_to(workspace).as_posix()
    if PolicyEngine()._is_high_risk_file(rel):
        raise ToolBlocked(f"Write touches high-risk path: {rel}")
    return path


async def _assert_plan_allows_write_path(db: AsyncSession, *, run_id: UUID, relative_path: str) -> None:
    run = await db.get(AgentRun, run_id)
    if run is None or run.plan_id is None:
        raise ToolBlocked("Write requires an approved plan.", block_type=ToolBlockType.APPROVAL_REQUIRED)
    plan = await db.get(Plan, run.plan_id)
    if plan is None or plan.approval_status != PlanApprovalStatus.APPROVED.value or not approved_plan_hash_matches(plan):
        raise ToolBlocked("Write requires a current approved plan hash.", block_type=ToolBlockType.APPROVAL_REQUIRED)
    implementation_plan = implementation_plan_from_db(plan)
    rel = PurePosixPath(relative_path.replace("\\", "/")).as_posix()
    file_targets = {_plan_workspace_relative_path(path) for path in implementation_plan.files_to_modify}
    test_targets = {_plan_workspace_relative_path(path) for path in implementation_plan.tests_to_add}
    if rel in file_targets or rel in test_targets:
        return
    for target in test_targets:
        if _looks_like_directory_target(target) and rel.startswith(f"{target.rstrip('/')}/"):
            return
    raise ToolBlocked(f"Write path is not approved by the plan: {rel}", block_type=ToolBlockType.POLICY_DENIED)


def _plan_workspace_relative_path(path: str) -> str:
    normalized = PurePosixPath(path.replace("\\", "/"))
    parts = normalized.parts
    if len(parts) >= 3 and parts[0] == "apps" and parts[1] == "api":
        return PurePosixPath(*parts[2:]).as_posix().rstrip("/")
    return normalized.as_posix().rstrip("/")


def _looks_like_directory_target(path: str) -> bool:
    if not path:
        return False
    return path.endswith("/") or PurePosixPath(path).suffix == ""


def _copy_ignore(_directory: str, names: list[str]) -> set[str]:
    return {name for name in names if name in IGNORED_TOOL_DIRS or _is_sensitive_workspace_path(name)}


def _iter_workspace_files(workspace: Path) -> list[Path]:
    files: list[Path] = []
    for path in workspace.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(workspace)
        if any(part in IGNORED_TOOL_DIRS for part in relative.parts):
            continue
        if _is_sensitive_workspace_path(relative.as_posix()):
            continue
        files.append(path)
    return sorted(files)


def _is_test_file(path: str) -> bool:
    lowered = path.lower()
    return "/test" in lowered or lowered.startswith("test") or ".test." in lowered or ".spec." in lowered or lowered.endswith("_test.py")


def _is_sensitive_workspace_path(relative_path: str) -> bool:
    path = PurePosixPath(relative_path.replace("\\", "/"))
    lowered_parts = {part.lower() for part in path.parts}
    if lowered_parts.intersection(SENSITIVE_TOOL_DIR_NAMES):
        return True
    name = path.name.lower()
    if name in SENSITIVE_FILE_NAMES:
        return True
    if any(name.startswith(prefix) for prefix in (".env.", "secret.", "secrets.")):
        return True
    return path.suffix.lower() in SENSITIVE_SUFFIXES


def _framework_hints(corpus: str) -> list[str]:
    frameworks: list[str] = []
    if "from fastapi" in corpus or "import fastapi" in corpus:
        frameworks.append("FastAPI")
    if '"next"' in corpus or "'next'" in corpus or "from \"next" in corpus:
        frameworks.append("Next.js")
    if "pytest" in corpus:
        frameworks.append("pytest")
    if "vitest" in corpus:
        frameworks.append("Vitest")
    return frameworks


def _snapshot(workspace: Path) -> dict[str, dict[str, str]]:
    snapshot: dict[str, dict[str, str]] = {}
    for path in _iter_workspace_files(workspace):
        if path.suffix.lower() not in TEXT_EXTENSIONS and path.suffix:
            continue
        if path.stat().st_size > MAX_READ_BYTES:
            continue
        relative = path.relative_to(workspace).as_posix()
        text = path.read_text(encoding="utf-8", errors="ignore")
        snapshot[relative] = {"sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "content": text}
    return snapshot


def _baseline_path(workspace: Path) -> Path:
    return workspace / INTERNAL_DIR / "baseline.json"


def _write_baseline(workspace: Path) -> None:
    metadata_dir = workspace / INTERNAL_DIR
    metadata_dir.mkdir(parents=True, exist_ok=True)
    _baseline_path(workspace).write_text(json.dumps(_snapshot(workspace), sort_keys=True), encoding="utf-8")


def _load_baseline(workspace: Path) -> dict[str, dict[str, str]]:
    path = _baseline_path(workspace)
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    return {str(key): value for key, value in payload.items() if isinstance(value, dict)}


def _workspace_diff_payload(workspace: Path) -> dict[str, Any]:
    baseline = _load_baseline(workspace)
    current = _snapshot(workspace)
    all_paths = sorted(set(baseline) | set(current))
    changed_files: list[dict[str, Any]] = []
    diff_parts: list[str] = []
    truncated = False

    for path in all_paths:
        old_text = str(baseline.get(path, {}).get("content", ""))
        new_text = str(current.get(path, {}).get("content", ""))
        if old_text == new_text:
            continue
        if path not in baseline:
            change_type = "create"
        elif path not in current:
            change_type = "delete"
        else:
            change_type = "modify"
        diff_lines = list(
            difflib.unified_diff(
                old_text.splitlines(keepends=True),
                new_text.splitlines(keepends=True),
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
            )
        )
        additions = sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++"))
        deletions = sum(1 for line in diff_lines if line.startswith("-") and not line.startswith("---"))
        changed_files.append({"path": path, "change_type": change_type, "additions": additions, "deletions": deletions})
        if sum(len(part) for part in diff_parts) < MAX_DIFF_BYTES:
            diff_parts.extend(diff_lines)
        else:
            truncated = True

    return {"workspace_path": str(workspace), "changed_files": changed_files, "diff": "".join(diff_parts), "truncated": truncated}


def _diff_paths(diff: str) -> set[str]:
    paths: set[str] = set()
    for line in diff.splitlines():
        if line.startswith("+++ b/") or line.startswith("--- a/"):
            path = line[6:]
            if path and path != "/dev/null":
                paths.add(path)
        elif line.startswith("diff --git "):
            match = re.match(r"diff --git a/(.+?) b/(.+)", line)
            if match:
                paths.add(match.group(1))
                paths.add(match.group(2))
    return paths


def _default_lint_command(workspace_path: str) -> str:
    workspace = Path(workspace_path)
    if (workspace / "package.json").is_file():
        return "npm run lint"
    return "ruff check ."


def _default_typecheck_command(workspace_path: str) -> str:
    workspace = Path(workspace_path)
    if (workspace / "package.json").is_file():
        return "npm run typecheck"
    return "mypy ."


_REGISTRY: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = ToolRegistry()
    return _REGISTRY
