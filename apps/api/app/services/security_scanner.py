from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from uuid import UUID

from repopilot_contracts import (
    AgentRunState,
    SecurityFinding,
    SecurityScanRequest,
    SecurityScanResult,
    SecuritySeverity,
    ValidationStatus,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentRun, AgentStep, SecurityFinding as DbSecurityFinding
from app.services.audit import record_audit
from app.services.policy import PolicyEngine
from app.services.security_envelope import redact_text
from app.services.state_machine import transition_run


SECRET_PATTERNS: tuple[tuple[str, SecuritySeverity, re.Pattern[str], str], ...] = (
    (
        "secret-scan",
        SecuritySeverity.CRITICAL,
        re.compile(r"ghp_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}", re.IGNORECASE),
        "GitHub token-like secret detected.",
    ),
    (
        "secret-scan",
        SecuritySeverity.HIGH,
        re.compile(r"AKIA[0-9A-Z]{16}"),
        "AWS access key-like secret detected.",
    ),
    (
        "secret-scan",
        SecuritySeverity.HIGH,
        re.compile(r"-----BEGIN (RSA |EC |OPENSSH |)PRIVATE KEY-----"),
        "Private key material detected.",
    ),
    (
        "secret-scan",
        SecuritySeverity.MEDIUM,
        re.compile(r"(?i)(api[_-]?key|password|secret|token)\s*=\s*['\"][^'\"]{8,}['\"]"),
        "Hardcoded credential-like assignment detected.",
    ),
    (
        "prompt-injection",
        SecuritySeverity.HIGH,
        re.compile(r"(?i)(ignore previous instructions|print secrets|exfiltrate|disable security)"),
        "Prompt-injection style instruction detected in generated evidence.",
    ),
)


class SecurityScanner:
    def __init__(self, *, policy_engine: PolicyEngine | None = None) -> None:
        self.policy_engine = policy_engine or PolicyEngine()

    async def scan_run(
        self,
        db: AsyncSession,
        *,
        run_id: UUID,
        request: SecurityScanRequest | None = None,
    ) -> SecurityScanResult:
        run = await db.get(AgentRun, run_id)
        if run is None:
            raise ValueError(f"Agent run not found: {run_id}")

        request = request or SecurityScanRequest()
        patch_payload = await self._latest_patch_payload(db, run_id=run.id)
        source_texts = self._scan_sources(patch_payload=patch_payload, workspace_path=request.workspace_path)
        findings = self.scan_texts(run_id=run.id, sources=source_texts)
        await self._persist_findings(db, run=run, findings=findings)

        blocked = any(finding.severity in {SecuritySeverity.HIGH, SecuritySeverity.CRITICAL} for finding in findings)
        status = ValidationStatus.FAILED if blocked and request.fail_on_findings else ValidationStatus.PASSED
        await transition_run(
            db,
            run=run,
            next_state=AgentRunState.RUN_SECURITY_CHECKS,
            actor_type="agent",
            reason="Security scan completed for generated patch evidence.",
            metadata={"status": status.value, "findings": len(findings)},
            allowed_from={AgentRunState.WAIT_FOR_CI.value, AgentRunState.READY_FOR_REVIEW.value},
        )
        db.add(
            AgentStep(
                run_id=run.id,
                step_name=AgentRunState.RUN_SECURITY_CHECKS.value,
                output_json={
                    "status": status.value,
                    "scanned_files": len(source_texts),
                    "findings": [finding.model_dump(mode="json") for finding in findings],
                },
                status="failed" if status == ValidationStatus.FAILED else "succeeded",
            )
        )
        await record_audit(
            db,
            actor_type="agent",
            action="security.scan_completed",
            entity_type="agent_run",
            entity_id=str(run.id),
            metadata={"findings": len(findings), "status": status.value},
        )
        await db.commit()

        return SecurityScanResult(
            run_id=str(run.id),
            status=status,
            scanned_files=len(source_texts),
            findings=findings,
            summary=self._summary(status=status, findings=findings),
        )

    def scan_texts(self, *, run_id: UUID, sources: dict[str, str]) -> list[SecurityFinding]:
        findings: list[SecurityFinding] = []
        for file_path, text in sources.items():
            if self.policy_engine._is_high_risk_file(file_path):
                findings.append(
                    SecurityFinding(
                        run_id=run_id,
                        tool="path-risk",
                        severity=SecuritySeverity.HIGH,
                        file_path=file_path,
                        description="Generated patch touches a high-risk path.",
                    )
                )
            for tool, severity, pattern, description in SECRET_PATTERNS:
                if pattern.search(text):
                    findings.append(
                        SecurityFinding(
                            run_id=run_id,
                            tool=tool,
                            severity=severity,
                            file_path=file_path,
                            description=description,
                        )
                    )
        return findings

    async def ingest_codeql_sarif(
        self,
        db: AsyncSession,
        *,
        run_id: UUID,
        sarif: dict[str, Any],
        source: str = "codeql-sarif",
        fail_on_findings: bool = True,
    ) -> SecurityScanResult:
        run = await db.get(AgentRun, run_id)
        if run is None:
            raise ValueError(f"Agent run not found: {run_id}")

        findings = self.parse_codeql_sarif(run_id=run.id, sarif=sarif)
        await self._persist_findings(db, run=run, findings=findings)
        blocked = fail_on_findings and any(
            finding.severity in {SecuritySeverity.HIGH, SecuritySeverity.CRITICAL} for finding in findings
        )
        status = ValidationStatus.FAILED if blocked else ValidationStatus.PASSED
        scanned_files = len({finding.file_path for finding in findings if finding.file_path})

        db.add(
            AgentStep(
                run_id=run.id,
                step_name="CODEQL_INGEST",
                output_json={
                    "source": source,
                    "status": status.value,
                    "scanned_files": scanned_files,
                    "finding_count": len(findings),
                    "findings": [finding.model_dump(mode="json") for finding in findings[:50]],
                },
                status="failed" if status == ValidationStatus.FAILED else "succeeded",
            )
        )
        await record_audit(
            db,
            actor_type="agent",
            action="security.codeql_sarif_ingested",
            entity_type="agent_run",
            entity_id=str(run.id),
            metadata={"source": source, "findings": len(findings), "status": status.value},
        )
        await db.commit()

        return SecurityScanResult(
            run_id=str(run.id),
            status=status,
            scanned_files=scanned_files,
            findings=findings,
            summary=f"CodeQL SARIF ingestion completed with {len(findings)} finding(s); status={status.value}.",
        )

    async def ingest_codeql_alerts(
        self,
        db: AsyncSession,
        *,
        run_id: UUID,
        alerts: list[dict[str, Any]],
        source: str = "github-code-scanning-alerts",
        fail_on_findings: bool = True,
    ) -> SecurityScanResult:
        run = await db.get(AgentRun, run_id)
        if run is None:
            raise ValueError(f"Agent run not found: {run_id}")

        findings = self.parse_codeql_alerts(run_id=run.id, alerts=alerts)
        await self._persist_findings(db, run=run, findings=findings)
        blocked = fail_on_findings and any(
            finding.severity in {SecuritySeverity.HIGH, SecuritySeverity.CRITICAL} for finding in findings
        )
        status = ValidationStatus.FAILED if blocked else ValidationStatus.PASSED
        scanned_files = len({finding.file_path for finding in findings if finding.file_path})

        db.add(
            AgentStep(
                run_id=run.id,
                step_name="CODEQL_ALERT_FETCH",
                output_json={
                    "source": source,
                    "status": status.value,
                    "alert_count": len(alerts),
                    "scanned_files": scanned_files,
                    "finding_count": len(findings),
                    "findings": [finding.model_dump(mode="json") for finding in findings[:50]],
                },
                status="failed" if status == ValidationStatus.FAILED else "succeeded",
            )
        )
        await record_audit(
            db,
            actor_type="agent",
            action="security.codeql_alerts_ingested",
            entity_type="agent_run",
            entity_id=str(run.id),
            metadata={"source": source, "alerts": len(alerts), "findings": len(findings), "status": status.value},
        )
        await db.commit()

        return SecurityScanResult(
            run_id=str(run.id),
            status=status,
            scanned_files=scanned_files,
            findings=findings,
            summary=f"GitHub CodeQL alert ingestion completed with {len(findings)} finding(s); status={status.value}.",
        )

    def parse_codeql_sarif(self, *, run_id: UUID, sarif: dict[str, Any]) -> list[SecurityFinding]:
        runs = sarif.get("runs") if isinstance(sarif, dict) else None
        if not isinstance(runs, list):
            return [
                SecurityFinding(
                    run_id=run_id,
                    tool="codeql",
                    severity=SecuritySeverity.MEDIUM,
                    file_path=None,
                    description="CodeQL SARIF payload did not contain a valid runs array.",
                )
            ]

        findings: list[SecurityFinding] = []
        for run_payload in runs:
            if not isinstance(run_payload, dict):
                continue
            rule_metadata = self._codeql_rule_metadata(run_payload)
            results = run_payload.get("results")
            for result in results if isinstance(results, list) else []:
                if not isinstance(result, dict):
                    continue
                rule_id = str(result.get("ruleId") or result.get("rule", {}).get("id") or "codeql")
                metadata = rule_metadata.get(rule_id, {})
                message = self._sarif_message_text(result.get("message")) or metadata.get("description") or rule_id
                file_path, line = self._sarif_primary_location(result)
                severity = self._codeql_severity(result=result, metadata=metadata)
                location = f" at line {line}" if line else ""
                findings.append(
                    SecurityFinding(
                        run_id=run_id,
                        tool="codeql",
                        severity=severity,
                        file_path=file_path,
                        description=redact_text(f"CodeQL {rule_id}{location}: {message}")[:1000],
                    )
                )
        return findings

    def parse_codeql_alerts(self, *, run_id: UUID, alerts: list[dict[str, Any]]) -> list[SecurityFinding]:
        findings: list[SecurityFinding] = []
        for alert in alerts:
            if not isinstance(alert, dict) or str(alert.get("state") or "").lower() not in {"open", ""}:
                continue
            rule = alert.get("rule") if isinstance(alert.get("rule"), dict) else {}
            instance = (
                alert.get("most_recent_instance")
                if isinstance(alert.get("most_recent_instance"), dict)
                else {}
            )
            location = instance.get("location") if isinstance(instance.get("location"), dict) else {}
            path = str(location.get("path") or "") or None
            start_line = location.get("start_line")
            rule_id = str(rule.get("id") or alert.get("number") or "codeql")
            description = str(rule.get("description") or rule.get("name") or alert.get("html_url") or "CodeQL alert")
            line = f" at line {start_line}" if isinstance(start_line, int) else ""
            findings.append(
                SecurityFinding(
                    run_id=run_id,
                    tool="codeql",
                    severity=self._codeql_alert_severity(rule),
                    file_path=path,
                    description=redact_text(f"CodeQL {rule_id}{line}: {description}")[:1000],
                )
            )
        return findings

    def _codeql_rule_metadata(self, run_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
        driver = ((run_payload.get("tool") or {}).get("driver") or {}) if isinstance(run_payload.get("tool"), dict) else {}
        rules = driver.get("rules") if isinstance(driver, dict) else []
        metadata: dict[str, dict[str, Any]] = {}
        for rule in rules if isinstance(rules, list) else []:
            if not isinstance(rule, dict):
                continue
            rule_id = str(rule.get("id") or "")
            if not rule_id:
                continue
            properties = rule.get("properties") if isinstance(rule.get("properties"), dict) else {}
            default_configuration = (
                rule.get("defaultConfiguration") if isinstance(rule.get("defaultConfiguration"), dict) else {}
            )
            metadata[rule_id] = {
                "level": default_configuration.get("level"),
                "security_severity": properties.get("security-severity"),
                "description": self._sarif_message_text(rule.get("shortDescription"))
                or self._sarif_message_text(rule.get("fullDescription")),
            }
        return metadata

    def _sarif_message_text(self, message: object) -> str | None:
        if isinstance(message, dict):
            text = message.get("text") or message.get("markdown")
            return str(text) if text else None
        return str(message) if message else None

    def _sarif_primary_location(self, result: dict[str, Any]) -> tuple[str | None, int | None]:
        locations = result.get("locations")
        if not isinstance(locations, list) or not locations:
            return None, None
        first = locations[0]
        if not isinstance(first, dict):
            return None, None
        physical = first.get("physicalLocation") if isinstance(first.get("physicalLocation"), dict) else {}
        artifact = physical.get("artifactLocation") if isinstance(physical.get("artifactLocation"), dict) else {}
        region = physical.get("region") if isinstance(physical.get("region"), dict) else {}
        uri = artifact.get("uri")
        start_line = region.get("startLine")
        return (str(uri) if uri else None, int(start_line) if isinstance(start_line, int) else None)

    def _codeql_severity(self, *, result: dict[str, Any], metadata: dict[str, Any]) -> SecuritySeverity:
        for value in (result.get("properties", {}).get("security-severity") if isinstance(result.get("properties"), dict) else None, metadata.get("security_severity")):
            try:
                score = float(value)
            except (TypeError, ValueError):
                continue
            if score >= 9:
                return SecuritySeverity.CRITICAL
            if score >= 7:
                return SecuritySeverity.HIGH
            if score >= 4:
                return SecuritySeverity.MEDIUM
            return SecuritySeverity.LOW

        level = str(result.get("level") or metadata.get("level") or "").lower()
        if level == "error":
            return SecuritySeverity.HIGH
        if level == "warning":
            return SecuritySeverity.MEDIUM
        if level in {"note", "none"}:
            return SecuritySeverity.LOW
        return SecuritySeverity.MEDIUM

    def _codeql_alert_severity(self, rule: dict[str, Any]) -> SecuritySeverity:
        security_level = str(rule.get("security_severity_level") or "").lower()
        if security_level in {"critical", "high", "medium", "low"}:
            return SecuritySeverity(security_level)
        severity = str(rule.get("severity") or "").lower()
        if severity == "error":
            return SecuritySeverity.HIGH
        if severity == "warning":
            return SecuritySeverity.MEDIUM
        if severity in {"note", "none"}:
            return SecuritySeverity.LOW
        return SecuritySeverity.MEDIUM

    def _scan_sources(self, *, patch_payload: dict[str, object] | None, workspace_path: str | None) -> dict[str, str]:
        sources: dict[str, str] = {}
        if patch_payload:
            diff = str(patch_payload.get("diff") or "")
            if diff:
                sources["generated.patch"] = diff
            workspace = Path(str(patch_payload.get("working_workspace_path") or workspace_path or "")).expanduser()
            for change in patch_payload.get("changed_files", []):
                if not isinstance(change, dict):
                    continue
                relative_path = str(change.get("path") or "")
                candidate = workspace / relative_path
                if candidate.is_file():
                    sources[relative_path] = candidate.read_text(encoding="utf-8", errors="ignore")

        if workspace_path and not sources:
            workspace = Path(workspace_path).expanduser()
            if workspace.is_dir():
                for candidate in workspace.rglob("*"):
                    if candidate.is_file() and candidate.stat().st_size <= 200_000:
                        sources[candidate.relative_to(workspace).as_posix()] = candidate.read_text(
                            encoding="utf-8",
                            errors="ignore",
                        )
        return sources or {"empty.patch": ""}

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

    async def _persist_findings(
        self,
        db: AsyncSession,
        *,
        run: AgentRun,
        findings: list[SecurityFinding],
    ) -> None:
        existing_result = await db.execute(select(DbSecurityFinding).where(DbSecurityFinding.run_id == run.id))
        existing_keys = {
            (finding.tool, finding.severity, finding.file_path, finding.description)
            for finding in existing_result.scalars().all()
        }
        for finding in findings:
            key = (finding.tool, finding.severity.value, finding.file_path, finding.description)
            if key in existing_keys:
                continue
            db.add(
                DbSecurityFinding(
                    run_id=run.id,
                    tool=finding.tool,
                    severity=finding.severity.value,
                    file_path=finding.file_path,
                    description=finding.description,
                    status=finding.status,
                )
            )

    def _summary(self, *, status: ValidationStatus, findings: list[SecurityFinding]) -> str:
        if not findings:
            return "Security scan completed with no findings."
        return f"Security scan completed with {len(findings)} finding(s); status={status.value}."
