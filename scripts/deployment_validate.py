from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


REQUIRED_SERVICES = {"api", "web", "worker", "beat", "postgres", "redis"}
REQUIRED_VOLUMES = {"postgres_data", "agent_workspaces", "agent_artifacts", "web_node_modules", "web_next"}
REQUIRED_ENV_KEYS = {
    "POSTGRES_PASSWORD",
    "REDIS_PASSWORD",
    "GITHUB_WEBHOOK_SECRET",
    "SESSION_SECRET_KEY",
    "GITHUB_APP_ID",
    "GITHUB_INSTALLATION_ID",
    "GITHUB_CLIENT_ID",
    "GITHUB_CLIENT_SECRET",
    "MODEL_PROVIDER",
    "MODEL_NAME",
    "MODEL_API_KEY",
    "GITHUB_WRITES_ENABLED",
    "REPOPILOT_ARTIFACT_STORE_ROOT",
    "REPOPILOT_RUNTIME_SECRETS_KEY_PATH",
    "REPOPILOT_RUNTIME_SECRETS_STORE_PATH",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
}
REQUIRED_GUIDE_SECTIONS = {
    "Local Docker Compose",
    "Single-VM Deployment",
    "Managed Postgres And Redis",
    "Secrets",
    "Storage And Cleanup",
    "Backups",
    "Observability",
    "Rollback",
    "Production Readiness Gate",
}
REQUIRED_RELEASE_ARTIFACTS = {
    "Docs/release-artifacts/source-boundary-hygiene.md",
    "Docs/release-artifacts/source-boundary-hygiene.json",
    "Docs/release-artifacts/source-boundary-manifest.md",
    "Docs/release-artifacts/source-boundary-manifest.json",
    "Docs/release-artifacts/release-gifs.md",
    "Docs/release-artifacts/release-gifs.json",
    "Docs/release-artifacts/deployment-runtime-smoke.md",
    "Docs/release-artifacts/deployment-runtime-smoke.json",
    "Docs/release-artifacts/credential-readiness-snapshot.md",
    "Docs/release-artifacts/credential-readiness-snapshot.json",
    "Docs/release-artifacts/credential-smoke-summary.md",
    "Docs/release-artifacts/credential-smoke-summary.json",
    "Docs/release-artifacts/security-scanner-snapshot.md",
    "Docs/release-artifacts/security-scanner-snapshot.json",
    "Docs/release-artifacts/model-provider-smoke.md",
    "Docs/release-artifacts/model-provider-smoke.json",
    "Docs/release-artifacts/github-app-smoke.md",
    "Docs/release-artifacts/github-app-smoke.json",
    "Docs/release-artifacts/github-oauth-smoke.md",
    "Docs/release-artifacts/github-oauth-smoke.json",
    "Docs/eval-reports/v1-local-latest.md",
    "Docs/eval-reports/v1-local-latest.json",
}


@dataclass
class DeploymentFinding:
    check: str
    status: str
    detail: str
    target: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {"check": self.check, "status": self.status, "target": self.target, "detail": self.detail}


@dataclass
class DeploymentValidationReport:
    root: str
    findings: list[DeploymentFinding] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        return any(finding.status == "failed" for finding in self.findings)

    @property
    def failed_count(self) -> int:
        return sum(1 for finding in self.findings if finding.status == "failed")

    @property
    def warning_count(self) -> int:
        return sum(1 for finding in self.findings if finding.status == "warning")

    def as_dict(self) -> dict[str, object]:
        return {
            "root": self.root,
            "failed": self.failed,
            "failed_count": self.failed_count,
            "warning_count": self.warning_count,
            "findings": [finding.as_dict() for finding in self.findings],
        }


class DeploymentValidator:
    def __init__(self, *, root: Path) -> None:
        self.root = root.resolve()

    def validate(self, *, check_runtime: bool = False) -> DeploymentValidationReport:
        report = DeploymentValidationReport(root=str(self.root))
        self.validate_compose(report)
        self.validate_env_example(report)
        self.validate_deployment_guide(report)
        self.validate_release_artifacts(report)
        if check_runtime:
            self.validate_runtime(report)
        if not report.findings:
            report.findings.append(DeploymentFinding(check="deployment_validation", status="passed", detail="All deployment checks passed."))
        return report

    def validate_compose(self, report: DeploymentValidationReport) -> None:
        compose = self.read_file("docker-compose.yml", report, check="compose_file")
        if compose is None:
            return
        services = self.extract_mapping_keys(compose, section="services")
        volumes = self.extract_mapping_keys(compose, section="volumes")
        for service in sorted(REQUIRED_SERVICES.difference(services)):
            report.findings.append(DeploymentFinding(check="compose_service", status="failed", target=service, detail="Required Compose service is missing."))
        for volume in sorted(REQUIRED_VOLUMES.difference(volumes)):
            report.findings.append(DeploymentFinding(check="compose_volume", status="failed", target=volume, detail="Required Compose volume is missing."))
        for service in ["postgres", "redis"]:
            if not self.service_block(compose, service) or "healthcheck:" not in self.service_block(compose, service):
                report.findings.append(DeploymentFinding(check="compose_healthcheck", status="failed", target=service, detail="Service needs a healthcheck."))
        for service in ["api", "worker", "beat"]:
            block = self.service_block(compose, service)
            if "agent_workspaces:" not in block:
                report.findings.append(DeploymentFinding(check="compose_workspace_volume", status="failed", target=service, detail="Service must mount agent_workspaces."))
            if service in {"api", "worker", "beat"} and "agent_artifacts:" not in block:
                report.findings.append(DeploymentFinding(check="compose_artifact_volume", status="failed", target=service, detail="Service must mount agent_artifacts."))
            if "./.local/repopilot-secrets:/home/appuser/.repopilot" not in block:
                report.findings.append(
                    DeploymentFinding(
                        check="compose_runtime_secret_volume",
                        status="failed",
                        target=service,
                        detail="Service must mount the repo-local encrypted runtime secret store.",
                    )
                )
            for env_key in ["REPOPILOT_RUNTIME_SECRETS_KEY_PATH", "REPOPILOT_RUNTIME_SECRETS_STORE_PATH"]:
                if env_key not in block:
                    report.findings.append(
                        DeploymentFinding(
                            check="compose_runtime_secret_env",
                            status="failed",
                            target=f"{service}:{env_key}",
                            detail="Service must use the mounted runtime secret store path.",
                        )
                    )

    def validate_env_example(self, report: DeploymentValidationReport) -> None:
        env_text = self.read_file(".env.example", report, check="env_example")
        if env_text is None:
            return
        keys = {
            line.split("=", 1)[0].strip()
            for line in env_text.splitlines()
            if line.strip() and not line.strip().startswith("#") and "=" in line
        }
        for key in sorted(REQUIRED_ENV_KEYS.difference(keys)):
            report.findings.append(DeploymentFinding(check="env_example_key", status="failed", target=key, detail="Required env placeholder is missing."))

    def validate_deployment_guide(self, report: DeploymentValidationReport) -> None:
        guide = self.read_file("Docs/DEPLOYMENT_GUIDE.md", report, check="deployment_guide")
        if guide is None:
            return
        headings = {line.removeprefix("## ").strip() for line in guide.splitlines() if line.startswith("## ")}
        for section in sorted(REQUIRED_GUIDE_SECTIONS.difference(headings)):
            report.findings.append(DeploymentFinding(check="deployment_guide_section", status="failed", target=section, detail="Required deployment guide section is missing."))
        for phrase in ["docker compose up -d --build", "alembic upgrade head", "GITHUB_WRITES_ENABLED=false", "OTEL_EXPORTER_OTLP_ENDPOINT"]:
            if phrase not in guide:
                report.findings.append(DeploymentFinding(check="deployment_guide_content", status="failed", target=phrase, detail="Required deployment instruction is missing."))

    def validate_release_artifacts(self, report: DeploymentValidationReport) -> None:
        for artifact in sorted(REQUIRED_RELEASE_ARTIFACTS):
            path = self.root / artifact
            if not path.is_file():
                report.findings.append(DeploymentFinding(check="release_artifact", status="failed", target=artifact, detail="Required release evidence artifact is missing."))
        screenshots = sorted((self.root / "Docs/release-artifacts").glob("operator-console-*.png"))
        if len(screenshots) < 6:
            report.findings.append(
                DeploymentFinding(check="release_artifact", status="warning", target="Docs/release-artifacts", detail="Fewer than six operator-console screenshots were found.")
            )
        gifs = sorted((self.root / "Docs/release-artifacts").glob("operator-console-*.gif"))
        if len(gifs) < 2:
            report.findings.append(
                DeploymentFinding(check="release_artifact", status="failed", target="Docs/release-artifacts", detail="Fewer than two operator-console release GIFs were found.")
            )

    def validate_runtime(self, report: DeploymentValidationReport) -> None:
        for name, url in {"api_health": "http://127.0.0.1:8000/health", "web": "http://127.0.0.1:3001/"}.items():
            try:
                status = self.probe_http_status(url)
                if status >= 400:
                    report.findings.append(DeploymentFinding(check="runtime_http", status="failed", target=name, detail=f"{url} returned HTTP {status}."))
            except (RuntimeError, OSError) as exc:
                report.findings.append(DeploymentFinding(check="runtime_http", status="failed", target=name, detail=f"{url} failed: {exc}."))

    def probe_http_status(self, url: str) -> int:
        curl_path = shutil.which("curl")
        if curl_path is None:
            raise RuntimeError("curl is required for runtime HTTP smoke checks.")
        last_error = ""
        for attempt in range(1, 4):
            result = subprocess.run(
                [curl_path, "-sS", "-L", "--max-time", "30", "--output", "/dev/null", "--write-out", "%{http_code}", url],
                capture_output=True,
                check=False,
                text=True,
            )
            if result.returncode == 0:
                status_text = result.stdout.strip()[-3:]
                if not status_text.isdigit():
                    raise RuntimeError(f"curl returned an invalid HTTP status: {result.stdout.strip()!r}")
                return int(status_text)
            last_error = (result.stderr or result.stdout).strip() or f"curl exited with {result.returncode}"
            if attempt < 3:
                time.sleep(2)
        raise RuntimeError(last_error)

    def read_file(self, relative_path: str, report: DeploymentValidationReport, *, check: str) -> str | None:
        path = self.root / relative_path
        if not path.is_file():
            report.findings.append(DeploymentFinding(check=check, status="failed", target=relative_path, detail="Required file is missing."))
            return None
        return path.read_text(encoding="utf-8")

    def extract_mapping_keys(self, text: str, *, section: str) -> set[str]:
        body = self.section_body(text, section=section)
        return {
            line.split(":", 1)[0].strip()
            for line in body
            if line.startswith("  ") and not line.startswith("    ") and ":" in line
        }

    def service_block(self, compose: str, service: str) -> str:
        services_body = self.section_body(compose, section="services")
        block: list[str] = []
        collecting = False
        for line in services_body:
            if line.startswith("  ") and not line.startswith("    "):
                current = line.split(":", 1)[0].strip()
                collecting = current == service
                if collecting:
                    block.append(line)
                continue
            if collecting:
                block.append(line)
        return "\n".join(block)

    def section_body(self, text: str, *, section: str) -> list[str]:
        lines = text.splitlines()
        body: list[str] = []
        collecting = False
        for line in lines:
            if line == f"{section}:":
                collecting = True
                continue
            if collecting and line and not line.startswith(" "):
                break
            if collecting:
                body.append(line)
        return body


def render_markdown(report: DeploymentValidationReport) -> str:
    lines = [
        "# RepoPilot Deployment Validation Report",
        "",
        f"- Root: `{report.root}`",
        f"- Failed findings: `{report.failed_count}`",
        f"- Warnings: `{report.warning_count}`",
        "",
        "| Check | Status | Target | Detail |",
        "|---|---|---|---|",
    ]
    for finding in report.findings:
        lines.append(
            "| "
            + " | ".join(
                [
                    finding.check,
                    finding.status,
                    finding.target or "",
                    finding.detail.replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate RepoPilot deployment documentation and local topology.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--md-out", type=Path, default=None)
    parser.add_argument("--check-runtime", action="store_true")
    parser.add_argument("--allow-warnings", action="store_true")
    parser.add_argument("--allow-failures", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = DeploymentValidator(root=args.root).validate(check_runtime=args.check_runtime)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report.as_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.md_out:
        args.md_out.parent.mkdir(parents=True, exist_ok=True)
        args.md_out.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
    if report.failed and not args.allow_failures:
        return 2
    if report.warning_count and not args.allow_warnings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
