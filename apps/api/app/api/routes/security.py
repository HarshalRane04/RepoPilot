from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from repopilot_contracts import (
    CodeQLAlertFetchRequest,
    CodeQLRecommendationResponse,
    CodeQLSarifIngestionRequest,
    SecurityFindingDetailResponse,
    SecurityScanResult,
    ValidationStatus,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import AgentRun, Installation, Issue, PullRequest, Repository, SecurityFinding, utc_now
from app.db.session import get_db
from app.services.audit import record_audit
from app.services.auth import CurrentUser, get_current_user
from app.services.authorization import require_run_access
from app.services.github_app import GitHubApiClient, GitHubIntegrationError
from app.services.security_scanner import SecurityScanner

router = APIRouter()

FINDING_STATUSES = {"open", "acknowledged", "fixed", "false_positive"}


class SecurityFindingStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = Field(pattern="^(open|acknowledged|fixed|false_positive)$")
    reason: str | None = Field(default=None, max_length=2000)


CODEQL_WORKFLOW = """name: CodeQL

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]
  schedule:
    - cron: "24 3 * * 1"

jobs:
  analyze:
    name: Analyze
    runs-on: ubuntu-latest
    permissions:
      security-events: write
      packages: read
      actions: read
      contents: read
    strategy:
      fail-fast: false
      matrix:
        language: [python, javascript-typescript]
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      - name: Initialize CodeQL
        uses: github/codeql-action/init@v3
        with:
          languages: ${{ matrix.language }}
      - name: Autobuild
        uses: github/codeql-action/autobuild@v3
      - name: Perform CodeQL Analysis
        uses: github/codeql-action/analyze@v3
"""


@router.get("/codeql/recommendation", response_model=CodeQLRecommendationResponse)
async def get_codeql_recommendation() -> dict[str, object]:
    return {
        "enabled": settings.codeql_enabled,
        "tool": "codeql",
        "workflow_path": ".github/workflows/codeql.yml",
        "summary": (
            "CODEQL_ENABLED is true; SARIF ingestion is enabled."
            if settings.codeql_enabled
            else "CODEQL_ENABLED is false; add this workflow and enable ingestion when CI CodeQL results are ready."
        ),
        "workflow_yaml": CODEQL_WORKFLOW,
    }


@router.post("/runs/{run_id}/codeql/sarif", response_model=SecurityScanResult)
async def ingest_codeql_sarif(
    run_id: UUID,
    request: CodeQLSarifIngestionRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SecurityScanResult:
    await require_run_access(db, run_id=run_id, current_user=current_user, action="write")
    if not settings.codeql_enabled:
        await record_audit(
            db,
            actor_type="user",
            actor_id=current_user.username,
            action="security.codeql_sarif_skipped",
            entity_type="agent_run",
            entity_id=str(run_id),
            metadata={"source": request.source, "reason": "CODEQL_ENABLED is false"},
        )
        await db.commit()
        return SecurityScanResult(
            run_id=str(run_id),
            status=ValidationStatus.SKIPPED,
            scanned_files=0,
            findings=[],
            summary="CODEQL_ENABLED is false; CodeQL SARIF ingestion skipped.",
        )
    return await SecurityScanner().ingest_codeql_sarif(
        db,
        run_id=run_id,
        sarif=request.sarif,
        source=request.source,
        fail_on_findings=request.fail_on_findings,
    )


@router.post("/runs/{run_id}/codeql/alerts/fetch", response_model=SecurityScanResult)
async def fetch_codeql_alerts(
    run_id: UUID,
    request: CodeQLAlertFetchRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SecurityScanResult:
    run = await require_run_access(db, run_id=run_id, current_user=current_user, action="write")
    if not settings.codeql_enabled:
        await record_audit(
            db,
            actor_type="user",
            actor_id=current_user.username,
            action="security.codeql_alert_fetch_skipped",
            entity_type="agent_run",
            entity_id=str(run_id),
            metadata={"reason": "CODEQL_ENABLED is false"},
        )
        await db.commit()
        return SecurityScanResult(
            run_id=str(run_id),
            status=ValidationStatus.SKIPPED,
            scanned_files=0,
            findings=[],
            summary="CODEQL_ENABLED is false; GitHub CodeQL alert fetch skipped.",
        )

    repository, installation = await _run_repository_installation(db, run)
    try:
        alerts = await GitHubApiClient().fetch_code_scanning_alerts(
            installation_id=installation.github_installation_id,
            owner=repository.owner,
            repo=repository.name,
            state=request.state,
            ref=request.ref,
            tool_name=request.tool_name,
            per_page=request.per_page,
        )
    except GitHubIntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return await SecurityScanner().ingest_codeql_alerts(
        db,
        run_id=run_id,
        alerts=alerts,
        source="github-code-scanning-alerts",
        fail_on_findings=request.fail_on_findings,
    )


@router.get("/findings", response_model=list[SecurityFindingDetailResponse])
async def list_security_findings(
    limit: int = Query(default=200, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, object]]:
    result = await db.execute(select(SecurityFinding).limit(limit))
    findings = result.scalars().all()
    return [await _finding_response(finding, db) for finding in findings]


@router.get("/findings/{finding_id}", response_model=SecurityFindingDetailResponse)
async def get_security_finding(finding_id: UUID, db: AsyncSession = Depends(get_db)) -> dict[str, object]:
    finding = await db.get(SecurityFinding, finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="Security finding not found")
    return await _finding_response(finding, db)


@router.patch("/findings/{finding_id}/status", response_model=SecurityFindingDetailResponse)
async def update_security_finding_status(
    finding_id: UUID,
    request: SecurityFindingStatusRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    finding = await db.get(SecurityFinding, finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="Security finding not found")
    await require_run_access(db, run_id=finding.run_id, current_user=current_user, action="write")
    if request.status not in FINDING_STATUSES:
        raise HTTPException(status_code=422, detail="Unsupported security finding status")
    if request.status in {"acknowledged", "false_positive"} and not request.reason:
        raise HTTPException(status_code=422, detail="A reason is required to acknowledge or mark a finding false positive")

    previous_status = finding.status
    finding.status = request.status
    finding.status_reason = request.reason
    finding.status_actor = current_user.username
    finding.status_changed_at = utc_now()
    await record_audit(
        db,
        actor_type="user",
        actor_id=current_user.username,
        action="security.finding_status_changed",
        entity_type="security_finding",
        entity_id=str(finding.id),
        metadata={"from_status": previous_status, "to_status": finding.status, "reason": request.reason},
    )
    await db.commit()
    return await _finding_response(finding, db)


async def _finding_response(finding: SecurityFinding, db: AsyncSession) -> dict[str, object]:
    run = await db.get(AgentRun, finding.run_id)
    issue = await db.get(Issue, run.issue_id) if run and run.issue_id else None
    repository = await db.get(Repository, issue.repository_id) if issue else None
    pr_result = await db.execute(select(PullRequest).where(PullRequest.run_id == finding.run_id).limit(1))
    pr = pr_result.scalars().first()
    return {
        "id": str(finding.id),
        "run_id": str(finding.run_id),
        "tool": finding.tool,
        "severity": finding.severity,
        "file_path": finding.file_path,
        "description": finding.description,
        "status": finding.status,
        "status_reason": finding.status_reason,
        "status_actor": finding.status_actor,
        "status_changed_at": finding.status_changed_at,
        "run": {
            "id": str(run.id),
            "state": run.state,
            "started_at": run.started_at,
            "completed_at": run.completed_at,
        }
        if run
        else None,
        "issue": {
            "id": str(issue.id),
            "number": issue.number,
            "title": issue.title,
            "status": issue.status,
        }
        if issue
        else None,
        "repository": {
            "id": str(repository.id),
            "owner": repository.owner,
            "name": repository.name,
        }
        if repository
        else None,
        "pull_request": {
            "id": str(pr.id),
            "number": pr.pr_number,
            "url": pr.url,
            "status": pr.status,
            "ci_status": pr.ci_status,
        }
        if pr
        else None,
    }


async def _run_repository_installation(db: AsyncSession, run: AgentRun) -> tuple[Repository, Installation]:
    if run.issue_id is None:
        raise HTTPException(status_code=422, detail="CodeQL alert fetch requires a run linked to an issue repository.")
    issue = await db.get(Issue, run.issue_id)
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found for run.")
    repository = await db.get(Repository, issue.repository_id)
    if repository is None:
        raise HTTPException(status_code=404, detail="Repository not found for run.")
    installation = await db.get(Installation, repository.installation_id)
    if installation is None:
        raise HTTPException(status_code=404, detail="Installation not found for repository.")
    return repository, installation
