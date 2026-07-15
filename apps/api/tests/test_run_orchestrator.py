from __future__ import annotations

import asyncio
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

from repopilot_contracts import ImplementationPlan, ValidationStatus

from app.core.config import settings
from app.db.models import AgentRun, AgentStep, Issue, Plan, RepositoryIndex, utc_now
from app.services.run_orchestrator import RunOrchestrator
from app.services.security_envelope import stable_json_hash
from app.worker.celery_app import celery_app
from app.worker.tasks import execute_agent_run_task, reconcile_stale_agent_runs_task


class FakeDb:
    def __init__(self, *, run, plan, issue, index):
        self.run = run
        self.objects = {(type(item), item.id): item for item in (run, plan, issue, index)}
        self.index = index
        self.added = []
        self.commits = 0
        self.scalar_count = 0

    async def get(self, model, item_id):
        return self.objects.get((model, item_id))

    async def scalar(self, _statement):
        self.scalar_count += 1
        if self.scalar_count == 1:
            return self.run
        if self.scalar_count == 2:
            return None
        return self.index

    def add(self, item):
        self.added.append(item)

    async def commit(self):
        self.commits += 1

    async def flush(self):
        for item in self.added:
            if getattr(item, "id", None) is None:
                item.id = uuid4()


class ModelPayload(SimpleNamespace):
    def model_dump(self, **_kwargs):
        return dict(self.payload)


class FakeScalarRows:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self.rows)


class FakeReconcileDb:
    def __init__(self, *, run: AgentRun, candidate: AgentStep) -> None:
        self.run = run
        self.candidate = candidate
        self.scalar_count = 0
        self.added: list[object] = []
        self.commits = 0

    async def execute(self, _statement):
        return FakeScalarRows([self.candidate])

    async def scalar(self, _statement):
        self.scalar_count += 1
        return self.run if self.scalar_count == 1 else self.candidate

    def add(self, item: object) -> None:
        self.added.append(item)

    async def commit(self) -> None:
        self.commits += 1


def test_run_orchestrator_executes_to_wait_for_ci(monkeypatch) -> None:
    issue_id = uuid4()
    plan_id = uuid4()
    run = AgentRun(id=uuid4(), issue_id=issue_id, plan_id=plan_id, state="WAIT_FOR_APPROVAL")
    implementation_plan = ImplementationPlan(
        plan_id=str(plan_id),
        issue_id=str(issue_id),
        files_to_modify=["app/demo.py"],
        commands_to_run=["python -m pytest"],
        rollback_plan="Close the draft PR.",
    )
    plan_payload = implementation_plan.model_dump(mode="json")
    approved_hash = stable_json_hash(implementation_plan.model_dump(mode="json", exclude={"plan_hash"}))
    plan_payload.update({"plan_hash": approved_hash, "approved_plan_hash": approved_hash})
    plan = Plan(id=plan_id, issue_id=issue_id, plan_json=plan_payload, approval_status="approved")
    issue = Issue(id=issue_id, repository_id=uuid4(), number=1, title="Fix bug")
    index = RepositoryIndex(
        id=uuid4(), repository_id=issue.repository_id, source_path="/tmp/repopilot-repositories/demo",
        commit_sha="a" * 40, content_fingerprint="fingerprint", files_indexed=1, chunks_indexed=1,
        skipped_files=0, embedding_provider="mock", embedding_model="mock-embedding",
        embedding_dimensions=1536, chunker_version="semantic-v1", status="ready", metadata_json={},
    )
    db = FakeDb(run=run, plan=plan, issue=issue, index=index)

    class FakeImplementationAgent:
        async def execute(self, _db, *, run_id, request):
            assert run_id == run.id
            assert request.workspace_path == index.source_path
            run.state = "RUN_LOCAL_VALIDATION"
            return ModelPayload(
                status=ValidationStatus.PASSED,
                patch=SimpleNamespace(patch_hash="b" * 64),
                payload={"status": "passed", "patch_hash": "b" * 64},
            )

    class FakeSecurityScanner:
        async def scan_run(self, _db, *, run_id):
            assert run_id == run.id
            run.state = "RUN_SECURITY_CHECKS"
            return ModelPayload(status=ValidationStatus.PASSED, payload={"status": "passed", "findings": []})

    class FakeDraftPullRequestService:
        async def open_draft_pr(self, _db, *, run_id):
            assert run_id == run.id
            run.state = "WAIT_FOR_CI"
            return ModelPayload(payload={"pr_id": str(uuid4()), "status": "draft"})

    monkeypatch.setattr("app.services.run_orchestrator.ImplementationAgent", FakeImplementationAgent)
    monkeypatch.setattr("app.services.run_orchestrator.SecurityScanner", FakeSecurityScanner)
    monkeypatch.setattr("app.services.run_orchestrator.DraftPullRequestService", FakeDraftPullRequestService)

    result = asyncio.run(RunOrchestrator().execute(db, run_id=run.id, actor_id="owner"))

    assert result["status"] == "succeeded"
    assert result["boundary"] == "WAIT_FOR_CI"
    orchestration_steps = [item for item in db.added if isinstance(item, AgentStep) and item.step_name == "ORCHESTRATE_RUN"]
    assert [step.status for step in orchestration_steps] == ["running", "succeeded"]
    assert db.commits == 2
    assert execute_agent_run_task.name == "repopilot.run.execute"
    assert reconcile_stale_agent_runs_task.name == "repopilot.run.reconcile_stale"
    assert settings.run_orchestration_stale_seconds > celery_app.conf.task_time_limit
    assert (
        celery_app.conf.beat_schedule["repopilot.run.reconcile_stale"]["schedule"]
        == settings.run_orchestration_reconcile_interval_seconds
    )


def test_run_orchestrator_creates_fresh_retry_for_blocked_attempt(monkeypatch) -> None:
    issue_id = uuid4()
    plan_id = uuid4()
    run = AgentRun(id=uuid4(), issue_id=issue_id, plan_id=plan_id, state="IMPLEMENT_PATCH")
    implementation_plan = ImplementationPlan(
        plan_id=str(plan_id),
        issue_id=str(issue_id),
        files_to_modify=["Docs/RUNBOOK.md"],
        commands_to_run=["python -m pytest"],
        rollback_plan="Close the draft PR.",
    )
    approved_hash = stable_json_hash(implementation_plan.model_dump(mode="json", exclude={"plan_hash"}))
    plan_payload = implementation_plan.model_dump(mode="json")
    plan_payload.update({"plan_hash": approved_hash, "approved_plan_hash": approved_hash})
    plan = Plan(id=plan_id, issue_id=issue_id, plan_json=plan_payload, approval_status="approved")
    issue = Issue(id=issue_id, repository_id=uuid4(), number=2, title="Update docs")
    index = RepositoryIndex(
        id=uuid4(), repository_id=issue.repository_id, source_path="/tmp/repopilot-repositories/demo",
        commit_sha="a" * 40, content_fingerprint="fingerprint", files_indexed=1, chunks_indexed=1,
        skipped_files=0, embedding_provider="mock", embedding_model="mock-embedding",
        embedding_dimensions=1536, chunker_version="semantic-v1", status="ready", metadata_json={},
    )
    db = FakeDb(run=run, plan=plan, issue=issue, index=index)
    blocked_step = AgentStep(run_id=run.id, step_name="ORCHESTRATE_RUN", status="blocked", output_json={})

    async def retry_scalar(_statement):
        db.scalar_count += 1
        return run if db.scalar_count == 1 else blocked_step

    monkeypatch.setattr(db, "scalar", retry_scalar)
    retry_run = asyncio.run(RunOrchestrator().create_retry_run(db, run_id=run.id, actor_id="owner"))

    assert run.state == "FAILED"
    assert retry_run.id != run.id
    assert retry_run.issue_id == run.issue_id
    assert retry_run.plan_id == run.plan_id
    assert retry_run.state == "CREATE_BRANCH"
    retry_step = next(item for item in db.added if isinstance(item, AgentStep) and item.step_name == "RETRY_CREATED")
    assert retry_step.output_json["retry_of_run_id"] == str(run.id)


def test_run_orchestrator_reconciles_abandoned_running_attempt() -> None:
    run = AgentRun(id=uuid4(), state="IMPLEMENT_PATCH")
    candidate = AgentStep(
        id=uuid4(),
        run_id=run.id,
        step_name="ORCHESTRATE_RUN",
        status="running",
        output_json={"phase": "started"},
        created_at=utc_now() - timedelta(minutes=20),
    )
    db = FakeReconcileDb(run=run, candidate=candidate)

    result = asyncio.run(
        RunOrchestrator().reconcile_stale_runs(
            db,
            stale_before=utc_now() - timedelta(minutes=16),
        )
    )

    assert result == {"candidates": 1, "recovered": 1, "runs_failed": 1}
    assert run.state == "FAILED"
    reconciled = next(
        item
        for item in db.added
        if isinstance(item, AgentStep)
        and item.step_name == "ORCHESTRATE_RUN"
        and item.output_json.get("phase") == "reconciled_stale"
    )
    assert reconciled.status == "failed"
    assert reconciled.output_json["stale_step_id"] == str(candidate.id)
    assert db.commits == 1
