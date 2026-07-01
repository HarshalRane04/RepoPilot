from __future__ import annotations

import asyncio
import json
from uuid import uuid4

from repopilot_contracts import DraftPullRequestRequest, SecuritySeverity

from app.db.models import AgentRun, AgentStep, Branch, Installation, Issue, LLMTrace, Plan, PullRequest, Repository, SecurityFinding, ValidationResult
from app.services.ci_analyzer import CIAnalyzer, CISummarySuggestion
from app.services.draft_pr import DraftPullRequestService
from app.services.eval_runner import EvalRunner
from app.services.integration_readiness import IntegrationReadinessService
from app.services.security_scanner import SecurityScanner
from app.services.state_machine import can_transition, next_states


class FakeCIGateway:
    def __init__(self, suggestion: CISummarySuggestion) -> None:
        self.suggestion = suggestion
        self.payload: dict[str, object] | None = None

    async def complete_json(self, _db, **kwargs):
        self.payload = json.loads(kwargs["user_prompt"])
        return self.suggestion


class FakeScalarResult:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows

    def scalars(self) -> "FakeScalarResult":
        return self

    def all(self) -> list[object]:
        return self.rows

    def first(self) -> object | None:
        return self.rows[0] if self.rows else None


class FakeDraftPrBodyDb:
    def __init__(
        self,
        *,
        validations: list[ValidationResult],
        findings: list[SecurityFinding],
        traces: list[LLMTrace],
        patch_step: AgentStep,
    ) -> None:
        self.validations = validations
        self.findings = findings
        self.traces = traces
        self.patch_step = patch_step

    async def execute(self, statement) -> FakeScalarResult:
        sql = str(statement)
        if "FROM validation_results" in sql:
            return FakeScalarResult(self.validations)
        if "FROM security_findings" in sql:
            return FakeScalarResult(self.findings)
        if "FROM llm_traces" in sql:
            return FakeScalarResult(self.traces)
        if "FROM agent_steps" in sql:
            return FakeScalarResult([self.patch_step])
        return FakeScalarResult([])


class FakeInstallationDb:
    def __init__(self, installation: Installation) -> None:
        self.installation = installation

    async def get(self, model, item_id):
        if model is Installation and self.installation.id == item_id:
            return self.installation
        return None


def test_security_scanner_detects_secret_like_patch_text() -> None:
    run_id = uuid4()
    findings = SecurityScanner().scan_texts(
        run_id=run_id,
        sources={"tests/test_secret.py": "TOKEN='ghp_abcdefghijklmnopqrstuvwxyz123456'"},
    )

    assert findings
    assert findings[0].severity == SecuritySeverity.CRITICAL
    assert findings[0].tool == "secret-scan"


def test_security_scanner_flags_high_risk_paths() -> None:
    findings = SecurityScanner().scan_texts(run_id=uuid4(), sources={".github/workflows/ci.yml": "name: ci"})

    assert findings
    assert findings[0].tool == "path-risk"
    assert findings[0].severity == SecuritySeverity.HIGH


def test_ci_analyzer_summarizes_failure_log() -> None:
    analyzer = CIAnalyzer()

    reasons = analyzer.failure_reasons("ok\nERROR tests failed\nTraceback: boom")
    summary = analyzer.summary(conclusion="failure", failure_reasons=reasons)

    assert reasons == ["ERROR tests failed", "Traceback: boom"]
    assert "ERROR tests failed" in summary


def test_ci_analyzer_model_summary_uses_gateway_and_redacts_logs() -> None:
    secret = "sk-live-secret-value-1234567890"
    suggestion = CISummarySuggestion(
        summary="CI failed because pytest reported a regression.",
        failure_reasons=["ERROR tests failed"],
        root_cause="ERROR tests failed",
        proposed_fix_path="tests/test_demo.py",
    )
    gateway = FakeCIGateway(suggestion)

    result = asyncio.run(
        CIAnalyzer(model_gateway=gateway).summary_with_model(
            object(),
            run_id=uuid4(),
            workflow_name="pytest",
            conclusion="failure",
            log_text=f"Run pytest\nERROR tests failed\nTOKEN={secret}",
            deterministic_summary=CISummarySuggestion(
                summary="CI concluded failure; first failure signal: ERROR tests failed",
                failure_reasons=["ERROR tests failed"],
                root_cause="ERROR tests failed",
                proposed_fix_path="tests/test_demo.py",
            ),
        )
    )

    assert result.summary == "CI failed because pytest reported a regression."
    assert gateway.payload is not None
    assert secret not in json.dumps(gateway.payload)
    assert "[REDACTED_SECRET]" in str(gateway.payload)


def test_ci_analyzer_model_summary_rejects_invented_failure_reasons() -> None:
    deterministic = CISummarySuggestion(
        summary="CI concluded failure; first failure signal: ERROR tests failed",
        failure_reasons=["ERROR tests failed"],
        root_cause="ERROR tests failed",
    )
    gateway = FakeCIGateway(
        CISummarySuggestion(
            summary="Invented dependency outage.",
            failure_reasons=["External service outage"],
            root_cause="External service outage",
        )
    )

    result = asyncio.run(
        CIAnalyzer(model_gateway=gateway).summary_with_model(
            object(),
            run_id=uuid4(),
            workflow_name="pytest",
            conclusion="failure",
            log_text="ERROR tests failed",
            deterministic_summary=deterministic,
        )
    )

    assert result == deterministic


def test_draft_pr_branch_names_are_deterministic_and_scoped() -> None:
    issue = Issue(
        repository_id=uuid4(),
        number=42,
        title="Fix Repository List Issue Count Display",
    )
    run = AgentRun(id=uuid4(), issue_id=issue.id, state="RUN_LOCAL_VALIDATION")

    branch = DraftPullRequestService()._branch_name(
        request=DraftPullRequestRequest(branch_prefix="repopilot"),
        issue=issue,
        run=run,
    )

    assert branch.startswith("repopilot/42-fix-repository-list-issue-count-display-")
    assert str(run.id)[:8] in branch


def test_draft_pr_local_result_is_not_a_github_url() -> None:
    run_id = uuid4()
    service = DraftPullRequestService()
    repository = Repository(owner="octo", name="demo", default_branch="main")
    pr = PullRequest(id=uuid4(), run_id=run_id, pr_number=7, url=service._pr_url(repository=repository, pr_number=7), status="draft")
    branch = Branch(run_id=run_id, branch_name="repopilot/7-demo", base_sha="local-base", head_sha="patch-sha")

    result = service._result(pr=pr, branch=branch, summary="Local record created.")

    assert result.url == "local://repopilot/draft-pr/7"
    assert result.pr_mode == "local_record"
    assert result.is_local_record is True
    assert result.github_url is None


def test_draft_pr_base_sha_guard_rejects_synthetic_index_markers() -> None:
    service = DraftPullRequestService()

    assert service._looks_like_commit_sha("19593aa1a73b28134c215020b853c8c650f6bbc4") is True
    assert service._looks_like_commit_sha("live-smoke-2026-06-19") is False
    assert service._looks_like_commit_sha(None) is False


def test_real_github_write_rejects_oauth_synced_repository() -> None:
    service = DraftPullRequestService()
    run = AgentRun(id=uuid4(), issue_id=uuid4(), state="RUN_SECURITY_CHECKS")
    issue = Issue(id=run.issue_id, repository_id=uuid4(), number=1, title="Smoke")
    installation = Installation(id=uuid4(), github_installation_id="oauth:123", account_name="octo")
    repository = Repository(
        id=issue.repository_id,
        installation_id=installation.id,
        owner="octo",
        name="demo",
        default_branch="main",
    )
    plan = Plan(id=uuid4(), issue_id=issue.id, approval_status="approved", plan_json={})

    try:
        asyncio.run(
            service._write_real_github_pr(
                FakeInstallationDb(installation),
                run=run,
                request=DraftPullRequestRequest(),
                issue=issue,
                repository=repository,
                plan=plan,
                branch_name="repopilot/1-smoke",
                patch_hash="patch",
                body="body",
                title="title",
                body_hash="body-hash",
            )
        )
    except ValueError as exc:
        assert "GitHub App to be installed" in str(exc)
    else:
        raise AssertionError("OAuth-synced repositories must be rejected before GitHub writes.")


def test_draft_pr_default_body_includes_evidence_hashes_and_redacted_security_details() -> None:
    run_id = uuid4()
    issue_id = uuid4()
    secret = "sk-live-secret-value-1234567890"
    run = AgentRun(id=run_id, issue_id=issue_id, state="RUN_LOCAL_VALIDATION")
    plan = Plan(
        id=uuid4(),
        issue_id=issue_id,
        approval_status="approved",
        plan_json={
            "issue_id": str(issue_id),
            "summary": "Fix evidence body.",
            "files_to_modify": ["apps/api/app/services/draft_pr.py"],
            "commands_to_run": ["pytest apps/api/tests/test_phase10_to_13_services.py"],
            "rollback_plan": "Close the draft PR and delete the generated branch.",
            "approved_plan_hash": "approved-plan-hash",
        },
    )
    validation = ValidationResult(
        run_id=run_id,
        command=f"pytest TOKEN={secret}",
        status="passed",
        duration_ms=1234,
        log_uri=f"local://artifacts/{secret}/validation.log",
        evidence_hash="validation-evidence-sha",
        parsed_summary=f"2 passed with TOKEN={secret}",
    )
    finding = SecurityFinding(
        run_id=run_id,
        tool="secret-scan",
        severity="low",
        file_path="apps/api/app/services/draft_pr.py",
        description=f"Scanner redacted TOKEN={secret}",
        status="fixed",
        status_reason="Allowed after generated test fixture was removed.",
    )
    patch_step = AgentStep(
        run_id=run_id,
        step_name="IMPLEMENT_PATCH",
        output_json={
            "patch_hash": "patch-evidence-sha",
            "changed_files": [{"path": "apps/api/app/services/draft_pr.py"}],
        },
        status="succeeded",
    )
    trace = LLMTrace(
        agent_run_id=run_id,
        agent_name="planning",
        prompt_hash="prompt-evidence-sha",
        response_hash="response-evidence-sha",
        provider="openrouter",
        model="google/gemma-4-31b-it:free",
        mode="live",
        tokens=42,
        cost=0.0012,
        latency_ms=900,
    )
    service = DraftPullRequestService()

    body = asyncio.run(
        service._default_body(
            FakeDraftPrBodyDb(validations=[validation], findings=[finding], traces=[trace], patch_step=patch_step),
            run=run,
            plan=plan,
        )
    )

    assert "approved-plan-hash" in body
    assert "patch-evidence-sha" in body
    assert "validation-evidence-sha" in body
    assert "local://artifacts/[REDACTED_SECRET]/validation.log" in body
    assert "`low` via `secret-scan`" in body
    assert "status: fixed" in body
    assert "response-evidence-sha" in body
    assert "google/gemma-4-31b-it:free" in body
    assert "Close the draft PR and delete the generated branch." in body
    assert secret not in body
    assert "[REDACTED_SECRET]" in body
    assert service._body_hash(body) == service._body_hash(body)
    assert service._body_hash(body) != service._body_hash(f"{body}\nchanged")


def test_eval_runner_ratio_handles_empty_denominator() -> None:
    runner = EvalRunner()

    assert runner._ratio(3, 0) == 0.0
    assert runner._ratio(1, 4) == 0.25


def test_readiness_reports_placeholder_gates() -> None:
    readiness = IntegrationReadinessService().readiness()

    assert readiness.production_ready is False
    assert readiness.local_record_mode is True
    assert any(item.name == "GitHub App installation credentials" for item in readiness.integrations)


def test_state_machine_blocks_invalid_skip_to_ready() -> None:
    assert can_transition("WAIT_FOR_APPROVAL", "READY_FOR_REVIEW") is False
    assert "CREATE_BRANCH" in next_states("WAIT_FOR_APPROVAL")
