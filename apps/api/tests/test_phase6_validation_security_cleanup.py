from __future__ import annotations

import os
import time
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException
from repopilot_contracts import CodeQLAlertFetchRequest, ValidationStatus

from app.api.routes.security import (
    SecurityFindingStatusRequest,
    fetch_codeql_alerts,
    get_codeql_recommendation,
    update_security_finding_status,
)
from app.core.config import settings
from app.db.models import AgentRun, ArtifactRecord, Issue, Repository, SecurityFinding, ValidationResult
from app.services.auth import CurrentUser
from app.services.security_scanner import SecurityScanner
from app.services.tools.registry import _persist_validation_result
from app.services.validation import ProjectDetector, ValidationPlanner
from app.services.workspace_cleanup import WorkspaceCleanupService
from app.worker.celery_app import celery_app
from app.worker.tasks import cleanup_artifacts_retention_task, cleanup_stale_workspaces_task


class FakeDb:
    def __init__(self, **items: object) -> None:
        self.items = items
        self.added: list[object] = []
        self.commits = 0

    async def get(self, model, item_id):
        for item in self.items.values():
            if isinstance(item, model) and getattr(item, "id", None) == item_id:
                return item
        return None

    def add(self, item: object) -> None:
        self.added.append(item)

    async def commit(self) -> None:
        self.commits += 1

    async def execute(self, _statement):
        class EmptyResult:
            def scalars(self):
                return self

            def first(self):
                return None

            def all(self):
                return []

        return EmptyResult()


def test_project_detector_detects_typescript_and_python_defaults(tmp_path: Path) -> None:
    web = tmp_path / "web"
    web.mkdir()
    (web / "package.json").write_text('{"scripts":{"test":"vitest","lint":"eslint .","typecheck":"tsc"}}', encoding="utf-8")
    (web / "tsconfig.json").write_text("{}", encoding="utf-8")

    api = tmp_path / "api"
    (api / "tests").mkdir(parents=True)
    (api / "app.py").write_text("VALUE = 1\n", encoding="utf-8")

    assert ProjectDetector().detect(web).validation_commands == ["npm test", "npm run lint", "npm run typecheck"]
    assert ProjectDetector().detect(api).validation_commands[0] == "python -m pytest"


def test_validation_planner_keeps_allowlisted_commands_only(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text("module demo\n", encoding="utf-8")

    commands = ValidationPlanner().commands_for(
        workspace_path=tmp_path,
        plan_commands=["pytest", "rm -rf /", "go test ./..."],
    )

    assert commands == ["python -m pytest", "go test ./..."]


def test_validation_result_persistence_redacts_and_hashes_logs() -> None:
    db = FakeDb()
    secret = "ghp_abcdefghijklmnopqrstuvwxyz123456"

    _persist_validation_result(
        db,
        run_id=uuid4(),
        command="python -m pytest",
        status=ValidationStatus.FAILED,
        duration_ms=25,
        summary=f"failed with {secret}",
        stdout=f"stdout {secret}",
        stderr="stderr",
    )

    validation = next(item for item in db.added if isinstance(item, ValidationResult))
    artifact = next(item for item in db.added if isinstance(item, ArtifactRecord))
    assert secret not in (validation.parsed_summary or "")
    assert validation.log_uri == artifact.uri
    assert validation.log_uri and validation.log_uri.startswith("local://artifacts/")
    assert artifact.artifact_type == "validation.log"
    assert artifact.sha256 and len(artifact.sha256) == 64
    assert validation.evidence_hash and len(validation.evidence_hash) == 64


def test_workspace_cleanup_removes_stale_inactive_workspace(tmp_path: Path) -> None:
    stale = tmp_path / "stale-run"
    active = tmp_path / "active-run"
    stale.mkdir()
    active.mkdir()
    old = time.time() - 7200
    os.utime(stale, (old, old))

    result = WorkspaceCleanupService(workspace_root=tmp_path, max_age_seconds=3600).cleanup_stale_workspaces(
        active_run_ids={"active-run"}
    )

    assert result["removed"] == ["stale-run"]
    assert not stale.exists()
    assert active.exists()


def test_workspace_cleanup_is_registered_as_periodic_celery_task() -> None:
    assert cleanup_stale_workspaces_task.name == "repopilot.workspace.cleanup"
    assert "repopilot.workspace.cleanup" in celery_app.tasks

    schedule = celery_app.conf.beat_schedule["repopilot.workspace.cleanup"]
    assert schedule["task"] == "repopilot.workspace.cleanup"
    assert schedule["schedule"] > 0

    assert cleanup_artifacts_retention_task.name == "repopilot.artifacts.retention_cleanup"
    assert "repopilot.artifacts.retention_cleanup" in celery_app.tasks

    artifact_schedule = celery_app.conf.beat_schedule["repopilot.artifacts.retention_cleanup"]
    assert artifact_schedule["task"] == "repopilot.artifacts.retention_cleanup"
    assert artifact_schedule["schedule"] > 0


def test_codeql_sarif_ingestion_persists_high_finding() -> None:
    import asyncio

    run = AgentRun(id=uuid4(), issue_id=None, state="RUN_SECURITY_CHECKS")
    db = FakeDb(run=run)
    sarif = {
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "CodeQL",
                        "rules": [
                            {
                                "id": "py/path-injection",
                                "shortDescription": {"text": "Path injection"},
                                "properties": {"security-severity": "8.1"},
                            }
                        ],
                    }
                },
                "results": [
                    {
                        "ruleId": "py/path-injection",
                        "message": {"text": "User-controlled path reaches filesystem API."},
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {"uri": "app/routes/files.py"},
                                    "region": {"startLine": 42},
                                }
                            }
                        ],
                    }
                ],
            }
        ],
    }

    result = asyncio.run(SecurityScanner().ingest_codeql_sarif(db, run_id=run.id, sarif=sarif))

    assert result.status == ValidationStatus.FAILED
    assert result.scanned_files == 1
    finding = next(item for item in db.added if isinstance(item, SecurityFinding))
    assert finding.tool == "codeql"
    assert finding.severity == "high"
    assert finding.file_path == "app/routes/files.py"
    assert "py/path-injection" in finding.description
    assert any(getattr(item, "step_name", "") == "CODEQL_INGEST" for item in db.added)


def test_codeql_alert_ingestion_persists_critical_finding() -> None:
    import asyncio

    run = AgentRun(id=uuid4(), issue_id=None, state="RUN_SECURITY_CHECKS")
    db = FakeDb(run=run)
    alerts = [
        {
            "state": "open",
            "rule": {
                "id": "js/xss",
                "description": "User-controlled HTML reaches a browser sink.",
                "security_severity_level": "critical",
            },
            "most_recent_instance": {"location": {"path": "apps/web/app/page.tsx", "start_line": 7}},
        }
    ]

    result = asyncio.run(SecurityScanner().ingest_codeql_alerts(db, run_id=run.id, alerts=alerts))

    assert result.status == ValidationStatus.FAILED
    finding = next(item for item in db.added if isinstance(item, SecurityFinding))
    assert finding.tool == "codeql"
    assert finding.severity == "critical"
    assert finding.file_path == "apps/web/app/page.tsx"
    assert any(getattr(item, "step_name", "") == "CODEQL_ALERT_FETCH" for item in db.added)


def test_codeql_recommendation_exposes_workflow(monkeypatch) -> None:
    import asyncio

    monkeypatch.setattr(settings, "codeql_enabled", True)

    response = asyncio.run(get_codeql_recommendation())

    assert response["enabled"] is True
    assert response["workflow_path"] == ".github/workflows/codeql.yml"
    assert "github/codeql-action/init@v4" in response["workflow_yaml"]
    assert "github/codeql-action/analyze@v4" in response["workflow_yaml"]
    assert "vars.CODEQL_ENABLED == 'true'" in response["workflow_yaml"]


def test_codeql_alert_fetch_route_skips_when_disabled(monkeypatch) -> None:
    import asyncio

    monkeypatch.setattr(settings, "codeql_enabled", False)
    run = AgentRun(id=uuid4(), issue_id=None, state="RUN_SECURITY_CHECKS")
    db = FakeDb(run=run)

    response = asyncio.run(
        fetch_codeql_alerts(
            run_id=run.id,
            request=CodeQLAlertFetchRequest(),
            current_user=CurrentUser(username="owner", role="owner"),
            db=db,
        )
    )

    assert response.status == ValidationStatus.SKIPPED
    assert response.summary == "CODEQL_ENABLED is false; GitHub CodeQL alert fetch skipped."
    assert db.commits == 1


def test_security_finding_status_requires_reason() -> None:
    finding = SecurityFinding(id=uuid4(), run_id=uuid4(), tool="secret", severity="high", description="secret")
    run = AgentRun(id=finding.run_id, issue_id=None, state="RUN_SECURITY_CHECKS")
    db = FakeDb(finding=finding, run=run)

    with pytest.raises(HTTPException):
        import asyncio

        asyncio.run(
            update_security_finding_status(
                finding_id=finding.id,
                request=SecurityFindingStatusRequest(status="false_positive"),
                current_user=CurrentUser(username="owner", role="owner"),
                db=db,
            )
        )


def test_security_finding_status_update_is_audited() -> None:
    import asyncio

    repository = Repository(id=uuid4(), installation_id=uuid4(), owner="octo", name="demo")
    issue = Issue(id=uuid4(), repository_id=repository.id, number=1, title="Fix")
    run = AgentRun(id=uuid4(), issue_id=issue.id, state="RUN_SECURITY_CHECKS")
    finding = SecurityFinding(id=uuid4(), run_id=run.id, tool="secret", severity="high", description="secret")
    db = FakeDb(finding=finding, run=run, issue=issue, repository=repository)

    response = asyncio.run(
        update_security_finding_status(
            finding_id=finding.id,
            request=SecurityFindingStatusRequest(status="acknowledged", reason="Accepted risk in local fixture."),
            current_user=CurrentUser(username="owner", role="owner"),
            db=db,
        )
    )

    assert response["status"] == "acknowledged"
    assert finding.status_reason == "Accepted risk in local fixture."
    assert finding.status_actor == "owner"
    assert db.commits == 1
