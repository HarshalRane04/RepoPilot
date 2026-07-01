from __future__ import annotations

import re
from pathlib import Path
from uuid import UUID

from repopilot_contracts import (
    AgentRunState,
    DraftPullRequestRequest,
    DraftPullRequestResult,
    SecurityScanRequest,
    SecuritySeverity,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import (
    AgentRun,
    AgentStep,
    Branch,
    Issue,
    Installation,
    LLMTrace,
    Plan,
    PullRequest,
    Repository,
    SecurityFinding,
    ValidationResult,
)
from app.services.audit import record_audit
from app.services.github_app import GitHubApiClient, GitHubIntegrationError
from app.services.planning import approved_plan_hash_matches, implementation_plan_from_db
from app.services.runtime_secrets import effective_settings
from app.services.security_envelope import redact_text, stable_json_hash
from app.services.security_scanner import SecurityScanner
from app.services.state_machine import transition_run


class DraftPullRequestService:
    async def open_draft_pr(
        self,
        db: AsyncSession,
        *,
        run_id: UUID,
        request: DraftPullRequestRequest | None = None,
    ) -> DraftPullRequestResult:
        run = await db.get(AgentRun, run_id)
        if run is None:
            raise ValueError(f"Agent run not found: {run_id}")
        if run.plan_id is None:
            raise ValueError("Run has no approved plan.")
        plan = await db.get(Plan, run.plan_id)
        if plan is None or plan.approval_status != "approved":
            raise ValueError("Run cannot open a draft PR until its plan is approved.")
        if not approved_plan_hash_matches(plan):
            raise ValueError("Run cannot open a draft PR because the approved plan hash no longer matches the current plan.")
        if not await self._has_passed_validation(db, run_id=run.id):
            raise ValueError("Run cannot open a draft PR without passing validation evidence.")

        await self._ensure_security_scan(db, run_id=run.id)
        blocking_findings = await self._blocking_security_findings(db, run_id=run.id)
        if blocking_findings:
            raise ValueError("Run has blocking high or critical security findings.")

        existing = await self._existing_pr(db, run_id=run.id)
        if existing:
            branch = await self._branch_for_run(db, run_id=run.id)
            return self._result(pr=existing, branch=branch, summary="Existing draft PR record reused.")

        request = request or DraftPullRequestRequest()
        issue = await db.get(Issue, run.issue_id) if run.issue_id else None
        repository = await db.get(Repository, issue.repository_id) if issue else None
        branch_name = self._branch_name(request=request, issue=issue, run=run)
        patch_hash = await self._latest_patch_hash(db, run_id=run.id)
        body = request.body or await self._default_body(db, run=run, plan=plan)
        body_hash = self._body_hash(body)
        title = request.title or self._default_title(issue=issue)
        real_write_evidence: dict[str, object] = {}
        runtime_settings = effective_settings(settings)
        if runtime_settings.github_writes_enabled:
            real_write_evidence = await self._write_real_github_pr(
                db,
                run=run,
                request=request,
                issue=issue,
                repository=repository,
                plan=plan,
                branch_name=branch_name,
                patch_hash=patch_hash,
                body=body,
                title=title,
                body_hash=body_hash,
            )

        branch = Branch(
            run_id=run.id,
            branch_name=branch_name,
            base_sha=str(real_write_evidence.get("base_sha") or (repository.last_indexed_sha if repository and repository.last_indexed_sha else "local-base")),
            head_sha=str(real_write_evidence.get("head_sha") or patch_hash or ""),
            status="pushed" if real_write_evidence else "created",
        )
        db.add(branch)
        await db.flush()

        pr_number = (await db.scalar(select(func.count()).select_from(PullRequest)) or 0) + 1
        if real_write_evidence.get("pr_number"):
            pr_number = int(real_write_evidence["pr_number"])
        pr = PullRequest(
            run_id=run.id,
            pr_number=pr_number,
            url=str(real_write_evidence.get("url") or self._pr_url(repository=repository, pr_number=pr_number)),
            status="draft",
            ci_status="pending",
            risk_score=issue.risk_score if issue else 0,
        )
        db.add(pr)
        await transition_run(
            db,
            run=run,
            next_state=AgentRunState.OPEN_DRAFT_PR,
            actor_type="agent",
            reason="Opening draft PR after validation and security gates.",
            metadata={"github_writes_enabled": runtime_settings.github_writes_enabled, "pr_number": pr_number},
            allowed_from={AgentRunState.RUN_LOCAL_VALIDATION.value, AgentRunState.RUN_SECURITY_CHECKS.value},
        )
        db.add(
            AgentStep(
                run_id=run.id,
                step_name=AgentRunState.OPEN_DRAFT_PR.value,
                output_json={
                    "pr_number": pr_number,
                    "url": pr.url,
                    "branch_name": branch.branch_name,
                    "body": body,
                    "body_hash": body_hash,
                    "title": title,
                    "mode": "real_github_write" if real_write_evidence else "local_record",
                    "github_write_evidence": real_write_evidence,
                },
                status="succeeded",
            )
        )
        await transition_run(
            db,
            run=run,
            next_state=AgentRunState.WAIT_FOR_CI,
            actor_type="agent",
            reason="Draft PR is waiting for CI evidence.",
            metadata={"pr_number": pr_number, "url": pr.url},
        )
        await record_audit(
            db,
            actor_type="agent",
            action="draft_pr.opened",
            entity_type="agent_run",
            entity_id=str(run.id),
            metadata={"pr_number": pr_number, "url": pr.url, "body_hash": body_hash},
        )
        await db.commit()
        await db.refresh(pr)
        await db.refresh(branch)
        mode = "real GitHub write" if real_write_evidence else "local draft PR record"
        return self._result(pr=pr, branch=branch, summary=f"Draft PR opened as {mode} with validation and security evidence.")

    async def _ensure_security_scan(self, db: AsyncSession, *, run_id: UUID) -> None:
        result = await db.execute(
            select(AgentStep).where(AgentStep.run_id == run_id, AgentStep.step_name == AgentRunState.RUN_SECURITY_CHECKS.value)
        )
        if result.scalars().first() is None:
            await SecurityScanner().scan_run(db, run_id=run_id, request=SecurityScanRequest())

    async def _has_passed_validation(self, db: AsyncSession, *, run_id: UUID) -> bool:
        result = await db.execute(select(ValidationResult).where(ValidationResult.run_id == run_id))
        return any(validation.status == "passed" for validation in result.scalars().all())

    async def _blocking_security_findings(self, db: AsyncSession, *, run_id: UUID) -> list[SecurityFinding]:
        result = await db.execute(
            select(SecurityFinding).where(
                SecurityFinding.run_id == run_id,
                SecurityFinding.status == "open",
                SecurityFinding.severity.in_([SecuritySeverity.HIGH.value, SecuritySeverity.CRITICAL.value]),
            )
        )
        return list(result.scalars().all())

    async def _existing_pr(self, db: AsyncSession, *, run_id: UUID) -> PullRequest | None:
        result = await db.execute(select(PullRequest).where(PullRequest.run_id == run_id).order_by(PullRequest.created_at.desc()))
        return result.scalars().first()

    async def _branch_for_run(self, db: AsyncSession, *, run_id: UUID) -> Branch | None:
        result = await db.execute(select(Branch).where(Branch.run_id == run_id).order_by(Branch.created_at.desc()))
        return result.scalars().first()

    async def _latest_patch_hash(self, db: AsyncSession, *, run_id: UUID) -> str | None:
        result = await db.execute(
            select(AgentStep)
            .where(AgentStep.run_id == run_id, AgentStep.step_name == AgentRunState.IMPLEMENT_PATCH.value)
            .order_by(AgentStep.created_at.desc())
        )
        step = result.scalars().first()
        if not step or not isinstance(step.output_json, dict):
            return None
        value = step.output_json.get("patch_hash")
        return str(value) if value else None

    async def _latest_patch_payload(self, db: AsyncSession, *, run_id: UUID) -> dict[str, object] | None:
        result = await db.execute(
            select(AgentStep)
            .where(AgentStep.run_id == run_id, AgentStep.step_name == AgentRunState.IMPLEMENT_PATCH.value)
            .order_by(AgentStep.created_at.desc())
        )
        step = result.scalars().first()
        if not step or not isinstance(step.output_json, dict):
            return None
        return step.output_json

    async def _write_real_github_pr(
        self,
        db: AsyncSession,
        *,
        run: AgentRun,
        request: DraftPullRequestRequest,
        issue: Issue | None,
        repository: Repository | None,
        plan: Plan,
        branch_name: str,
        patch_hash: str | None,
        body: str,
        title: str,
        body_hash: str,
    ) -> dict[str, object]:
        if repository is None or issue is None:
            raise ValueError("Real GitHub PR creation requires a linked repository and issue.")
        installation = await db.get(Installation, repository.installation_id)
        if installation is None:
            raise ValueError("Real GitHub PR creation requires a linked GitHub App installation.")
        if installation.github_installation_id.startswith("oauth:"):
            raise ValueError(
                "Real GitHub PR creation requires the GitHub App to be installed on this repository; "
                "OAuth-synced repositories are read-only for write-mode PR creation."
            )
        patch_payload = await self._latest_patch_payload(db, run_id=run.id)
        if not patch_payload or patch_payload.get("patch_hash") != patch_hash:
            raise ValueError("Real GitHub PR creation requires the latest validated patch hash.")

        client = GitHubApiClient()
        try:
            base_sha = repository.last_indexed_sha if self._looks_like_commit_sha(repository.last_indexed_sha) else None
            if base_sha is None:
                base_sha = await client.get_ref_sha(
                    installation_id=installation.github_installation_id,
                    owner=repository.owner,
                    repo=repository.name,
                    branch=repository.default_branch,
                )
            await client.create_branch(
                installation_id=installation.github_installation_id,
                owner=repository.owner,
                repo=repository.name,
                branch_name=branch_name,
                base_sha=base_sha,
            )
            head_sha = await client.commit_patch(
                installation_id=installation.github_installation_id,
                owner=repository.owner,
                repo=repository.name,
                branch_name=branch_name,
                message=f"RepoPilot: {issue.title}",
                changed_files=self._changed_file_contents(patch_payload),
            )
            pr_payload = await client.open_pull_request(
                installation_id=installation.github_installation_id,
                owner=repository.owner,
                repo=repository.name,
                branch_name=branch_name,
                base_branch=request.base_branch or repository.default_branch,
                title=title,
                body=body,
                draft=True,
            )
            await client.comment_issue(
                installation_id=installation.github_installation_id,
                owner=repository.owner,
                repo=repository.name,
                issue_number=issue.number,
                body=f"RepoPilot opened draft PR #{pr_payload.get('number')} with validation and security evidence.",
            )
        except GitHubIntegrationError as exc:
            raise ValueError(f"Real GitHub PR creation failed: {exc}") from exc

        return {
            "base_sha": base_sha,
            "head_sha": head_sha,
            "pr_number": pr_payload.get("number"),
            "url": pr_payload.get("html_url") or pr_payload.get("url"),
            "patch_hash": patch_hash,
            "body_hash": body_hash,
        }

    def _looks_like_commit_sha(self, value: str | None) -> bool:
        return bool(value and re.fullmatch(r"[0-9a-fA-F]{40}", value))

    def _changed_file_contents(self, patch_payload: dict[str, object]) -> list[dict[str, str | None]]:
        workspace = Path(str(patch_payload.get("working_workspace_path") or "")).expanduser()
        changed_files: list[dict[str, str | None]] = []
        for change in patch_payload.get("changed_files", []):
            if not isinstance(change, dict):
                continue
            path = str(change.get("path") or "")
            if not path:
                continue
            candidate = workspace / path
            content = candidate.read_text(encoding="utf-8", errors="ignore") if candidate.is_file() else None
            changed_files.append({"path": path, "content": content})
        if not changed_files:
            raise ValueError("Real GitHub PR creation requires changed files in the latest patch payload.")
        return changed_files

    async def _default_body(self, db: AsyncSession, *, run: AgentRun, plan: Plan) -> str:
        implementation_plan = implementation_plan_from_db(plan)
        validations_result = await db.execute(select(ValidationResult).where(ValidationResult.run_id == run.id))
        validations = list(validations_result.scalars().all())
        findings_result = await db.execute(select(SecurityFinding).where(SecurityFinding.run_id == run.id))
        findings = list(findings_result.scalars().all())
        traces_result = await db.execute(select(LLMTrace).where(LLMTrace.agent_run_id == run.id))
        traces = list(traces_result.scalars().all())
        patch_payload = await self._latest_patch_payload(db, run_id=run.id)
        patch_hash = str(patch_payload.get("patch_hash")) if patch_payload and patch_payload.get("patch_hash") else None
        plan_hash = self._plan_evidence_hash(plan)
        return "\n".join(
            [
                "## RepoPilot Evidence",
                "",
                "### Approved plan",
                f"- Plan hash: `{plan_hash}`" if plan_hash else "- Plan hash: not recorded",
                "- Target files:",
                *[f"- `{path}`" for path in implementation_plan.files_to_modify],
                "",
                "### Patch",
                f"- Patch hash: `{patch_hash}`" if patch_hash else "- Patch hash: not recorded",
                *self._changed_file_evidence_lines(patch_payload),
                "",
                "### Validation",
                *self._validation_evidence_lines(validations),
                "",
                "### Security",
                *self._security_evidence_lines(findings),
                "",
                "### Model trace",
                *self._model_trace_evidence_lines(traces),
                "",
                "### Rollback",
                f"- {self._short(redact_text(implementation_plan.rollback_plan), limit=400)}",
            ]
        )

    def _body_hash(self, body: str) -> str:
        return stable_json_hash({"body": body})

    def _plan_evidence_hash(self, plan: Plan) -> str | None:
        for key in ("approved_plan_hash", "plan_hash"):
            value = plan.plan_json.get(key)
            if isinstance(value, str) and value:
                return value
        return None

    def _changed_file_evidence_lines(self, patch_payload: dict[str, object] | None) -> list[str]:
        if not patch_payload:
            return []
        changed_files = patch_payload.get("changed_files")
        if not isinstance(changed_files, list) or not changed_files:
            return []
        lines = ["- Changed files:"]
        for change in changed_files[:20]:
            if not isinstance(change, dict):
                continue
            path = change.get("path")
            if path:
                lines.append(f"- `{redact_text(str(path))}`")
        if len(changed_files) > 20:
            lines.append(f"- ...and {len(changed_files) - 20} more files")
        return lines

    def _validation_evidence_lines(self, validations: list[ValidationResult]) -> list[str]:
        if not validations:
            return ["- No validation evidence recorded."]
        lines: list[str] = []
        for validation in validations:
            details: list[str] = []
            if validation.parsed_summary:
                details.append(self._short(redact_text(validation.parsed_summary)))
            if validation.evidence_hash:
                details.append(f"evidence `{validation.evidence_hash}`")
            if validation.log_uri:
                details.append(f"log `{redact_text(validation.log_uri)}`")
            if validation.duration_ms is not None:
                details.append(f"{validation.duration_ms} ms")
            suffix = f" ({'; '.join(details)})" if details else ""
            lines.append(f"- `{redact_text(validation.command)}`: {validation.status}{suffix}")
        return lines

    def _security_evidence_lines(self, findings: list[SecurityFinding]) -> list[str]:
        if not findings:
            return ["- No security findings recorded by enforced scans."]
        open_findings = [finding for finding in findings if finding.status == "open"]
        blocking_findings = [
            finding
            for finding in open_findings
            if finding.severity in {SecuritySeverity.HIGH.value, SecuritySeverity.CRITICAL.value}
        ]
        lines = [
            f"- Finding count: {len(findings)} total, {len(open_findings)} open, {len(blocking_findings)} blocking.",
        ]
        for finding in findings[:20]:
            path = f" in `{redact_text(finding.file_path)}`" if finding.file_path else ""
            reason = f"; reason: {self._short(redact_text(finding.status_reason))}" if finding.status_reason else ""
            description = self._short(redact_text(finding.description))
            lines.append(
                f"- `{finding.severity}` via `{finding.tool}`{path}: {description} "
                f"(status: {finding.status}{reason})"
            )
        if len(findings) > 20:
            lines.append(f"- ...and {len(findings) - 20} more findings")
        return lines

    def _model_trace_evidence_lines(self, traces: list[LLMTrace]) -> list[str]:
        if not traces:
            return ["- No LLM trace evidence recorded for this run."]
        total_tokens = sum(trace.tokens or 0 for trace in traces)
        total_cost = sum(trace.cost or 0.0 for trace in traces)
        providers = sorted({f"{trace.provider}/{trace.model}" for trace in traces})
        lines = [
            f"- Calls: {len(traces)}; tokens: {total_tokens}; cost: ${total_cost:.6f}.",
            f"- Providers: {', '.join(providers)}.",
        ]
        for trace in traces[:10]:
            response = f"; response `{trace.response_hash}`" if trace.response_hash else ""
            latency = f"; {trace.latency_ms} ms" if trace.latency_ms is not None else ""
            lines.append(
                f"- `{trace.agent_name}`: {trace.provider}/{trace.model} ({trace.mode}); "
                f"prompt `{trace.prompt_hash}`{response}; tokens {trace.tokens}; cost ${trace.cost:.6f}{latency}"
            )
        if len(traces) > 10:
            lines.append(f"- ...and {len(traces) - 10} more LLM calls")
        return lines

    def _short(self, value: str | None, *, limit: int = 180) -> str:
        if not value:
            return ""
        collapsed = " ".join(value.split())
        return collapsed if len(collapsed) <= limit else f"{collapsed[: limit - 1]}..."

    def _branch_name(self, *, request: DraftPullRequestRequest, issue: Issue | None, run: AgentRun) -> str:
        issue_part = str(issue.number) if issue else "run"
        title_part = self._slug(issue.title if issue else "agent-run")
        return f"{request.branch_prefix}/{issue_part}-{title_part}-{str(run.id)[:8]}"

    def _default_title(self, *, issue: Issue | None) -> str:
        return f"RepoPilot: {issue.title}" if issue else "RepoPilot generated draft PR"

    def _slug(self, value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:48] or "task"

    def _pr_url(self, *, repository: Repository | None, pr_number: int) -> str:
        return f"local://repopilot/draft-pr/{pr_number}"

    def _result(self, *, pr: PullRequest, branch: Branch | None, summary: str) -> DraftPullRequestResult:
        is_real_github_pr = pr.url.startswith(("https://", "http://"))
        return DraftPullRequestResult(
            pr_id=str(pr.id),
            run_id=str(pr.run_id),
            pr_number=pr.pr_number,
            url=pr.url,
            pr_mode="real_github" if is_real_github_pr else "local_record",
            is_local_record=not is_real_github_pr,
            github_url=pr.url if is_real_github_pr else None,
            status=pr.status,
            branch_name=branch.branch_name if branch else "unknown",
            ci_status=pr.ci_status,
            summary=summary,
        )
