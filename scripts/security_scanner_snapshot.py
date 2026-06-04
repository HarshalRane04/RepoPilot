from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Sequence


DEFAULT_JSON_OUT = Path("Docs/release-artifacts/security-scanner-snapshot.json")
DEFAULT_MD_OUT = Path("Docs/release-artifacts/security-scanner-snapshot.md")
SECURITY_ENV_KEYS = ("SEMGREP_ENABLED", "DEPENDENCY_AUDIT_ENABLED", "CODEQL_ENABLED")
DEPENDENCY_MANIFEST_PATTERNS = ("package-lock.json", "requirements.txt", "pyproject.toml")


Runner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


@dataclass
class ToolVersion:
    name: str
    command: list[str]
    available: bool
    version: str | None = None
    detail: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "command": self.command,
            "available": self.available,
            "version": self.version,
            "detail": self.detail,
        }


@dataclass
class ScannerStatus:
    name: str
    env_key: str | None
    enabled: bool
    status: str
    detail: str
    required_for_release: bool
    tools: list[str] = field(default_factory=list)
    next_step: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "env_key": self.env_key,
            "enabled": self.enabled,
            "status": self.status,
            "detail": self.detail,
            "required_for_release": self.required_for_release,
            "tools": self.tools,
            "next_step": self.next_step,
        }


@dataclass
class SecurityScannerSnapshot:
    generated_at: str
    root: str
    release_scanner_proof_ready: bool
    environment: dict[str, bool]
    dependency_manifests: list[str]
    codeql_workflow_present: bool
    tool_versions: list[ToolVersion]
    scanners: list[ScannerStatus]
    warnings: list[str]
    blockers: list[str]

    def as_dict(self) -> dict[str, object]:
        return {
            "generated_at": self.generated_at,
            "root": self.root,
            "release_scanner_proof_ready": self.release_scanner_proof_ready,
            "environment": self.environment,
            "dependency_manifests": self.dependency_manifests,
            "codeql_workflow_present": self.codeql_workflow_present,
            "tool_versions": [tool.as_dict() for tool in self.tool_versions],
            "scanners": [scanner.as_dict() for scanner in self.scanners],
            "warnings": self.warnings,
            "blockers": self.blockers,
        }


def parse_bool(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def default_runner(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, check=False, text=True, timeout=15)


def collect_tool_version(name: str, command: list[str], *, runner: Runner = default_runner) -> ToolVersion:
    if shutil.which(command[0]) is None:
        return ToolVersion(name=name, command=command, available=False, detail=f"{command[0]} executable was not found.")
    try:
        result = runner(command)
    except (OSError, subprocess.SubprocessError) as exc:
        return ToolVersion(name=name, command=command, available=True, detail=str(exc))
    output = (result.stdout or result.stderr or "").strip()
    first_line = output.splitlines()[0] if output else None
    if result.returncode != 0:
        return ToolVersion(name=name, command=command, available=True, version=first_line, detail=f"Version command exited {result.returncode}.")
    return ToolVersion(name=name, command=command, available=True, version=first_line)


def find_dependency_manifests(root: Path) -> list[str]:
    manifests: list[str] = []
    ignored_parts = {".git", "node_modules", ".next", "__pycache__", ".pytest_cache"}
    for pattern in DEPENDENCY_MANIFEST_PATTERNS:
        for path in root.rglob(pattern):
            if ignored_parts.intersection(path.relative_to(root).parts):
                continue
            manifests.append(path.relative_to(root).as_posix())
    return sorted(set(manifests))


def has_tool(tools: Mapping[str, ToolVersion], name: str) -> bool:
    return bool(tools[name].available)


def collect_snapshot(
    *,
    root: Path,
    env: Mapping[str, str] | None = None,
    runner: Runner = default_runner,
) -> SecurityScannerSnapshot:
    root = root.resolve()
    env = env or os.environ
    env_flags = {key: parse_bool(env.get(key)) for key in SECURITY_ENV_KEYS}
    dependency_manifests = find_dependency_manifests(root)
    codeql_workflow_present = any((root / ".github/workflows").glob("*codeql*.yml")) or any(
        (root / ".github/workflows").glob("*codeql*.yaml")
    )

    versions = [
        collect_tool_version("semgrep", ["semgrep", "--version"], runner=runner),
        collect_tool_version("npm", ["npm", "--version"], runner=runner),
        collect_tool_version("pip-audit", ["pip-audit", "--version"], runner=runner),
        collect_tool_version("codeql", ["codeql", "--version"], runner=runner),
    ]
    tools = {tool.name: tool for tool in versions}
    scanners: list[ScannerStatus] = [
        ScannerStatus(
            name="built_in_prompt_and_secret_guards",
            env_key=None,
            enabled=True,
            status="ready",
            detail="Deterministic prompt-injection and secret-pattern guards are implemented in the local control plane.",
            required_for_release=True,
            tools=[],
        ),
        ScannerStatus(
            name="release_hygiene_secret_scan",
            env_key=None,
            enabled=True,
            status="ready",
            detail="Source-boundary hygiene scanning is available through make release-hygiene.",
            required_for_release=True,
            tools=[],
        ),
    ]
    blockers: list[str] = []
    warnings: list[str] = []

    if env_flags["SEMGREP_ENABLED"]:
        if has_tool(tools, "semgrep"):
            scanners.append(
                ScannerStatus(
                    name="semgrep",
                    env_key="SEMGREP_ENABLED",
                    enabled=True,
                    status="ready",
                    detail="Semgrep is enabled and the executable is available for sandbox security gates.",
                    required_for_release=True,
                    tools=["semgrep"],
                )
            )
        else:
            detail = "SEMGREP_ENABLED is true, but semgrep is not installed in this runtime."
            blockers.append(detail)
            scanners.append(
                ScannerStatus(
                    name="semgrep",
                    env_key="SEMGREP_ENABLED",
                    enabled=True,
                    status="blocked",
                    detail=detail,
                    required_for_release=True,
                    tools=["semgrep"],
                    next_step="Install Semgrep in the API/worker runtime or disable the gate until the tool image includes it.",
                )
            )
    else:
        detail = "SEMGREP_ENABLED is false; Semgrep evidence remains local-placeholder only."
        warnings.append(detail)
        scanners.append(
            ScannerStatus(
                name="semgrep",
                env_key="SEMGREP_ENABLED",
                enabled=False,
                status="disabled",
                detail=detail,
                required_for_release=True,
                tools=["semgrep"],
                next_step="Install Semgrep and set SEMGREP_ENABLED=true for release scanner proof.",
            )
        )

    if env_flags["DEPENDENCY_AUDIT_ENABLED"]:
        missing_tools: list[str] = []
        if any(path.endswith("package-lock.json") for path in dependency_manifests) and not has_tool(tools, "npm"):
            missing_tools.append("npm")
        if any(path.endswith(("requirements.txt", "pyproject.toml")) for path in dependency_manifests) and not has_tool(tools, "pip-audit"):
            missing_tools.append("pip-audit")
        if missing_tools:
            detail = f"DEPENDENCY_AUDIT_ENABLED is true, but required tool(s) are unavailable: {', '.join(missing_tools)}."
            blockers.append(detail)
            status = "blocked"
            next_step = "Install the missing dependency audit tools in the API/worker runtime."
        elif dependency_manifests:
            detail = f"Dependency audit is enabled and manifests were found: {len(dependency_manifests)}."
            status = "ready"
            next_step = None
        else:
            detail = "Dependency audit is enabled, but no dependency manifests were found in the source boundary."
            warnings.append(detail)
            status = "warning"
            next_step = "Confirm whether this source boundary intentionally has no dependency manifests."
        scanners.append(
            ScannerStatus(
                name="dependency_audit",
                env_key="DEPENDENCY_AUDIT_ENABLED",
                enabled=True,
                status=status,
                detail=detail,
                required_for_release=True,
                tools=["npm", "pip-audit"],
                next_step=next_step,
            )
        )
    else:
        detail = "DEPENDENCY_AUDIT_ENABLED is false; npm/pip audit evidence is not production-proven."
        warnings.append(detail)
        scanners.append(
            ScannerStatus(
                name="dependency_audit",
                env_key="DEPENDENCY_AUDIT_ENABLED",
                enabled=False,
                status="disabled",
                detail=detail,
                required_for_release=True,
                tools=["npm", "pip-audit"],
                next_step="Install audit tools and set DEPENDENCY_AUDIT_ENABLED=true for release scanner proof.",
            )
        )

    if env_flags["CODEQL_ENABLED"]:
        if codeql_workflow_present:
            if has_tool(tools, "codeql"):
                detail = "CODEQL_ENABLED is true, a CodeQL workflow file is present, and the local CodeQL executable is available."
                status = "ready"
                next_step = None
            else:
                detail = "CODEQL_ENABLED is true and a CodeQL workflow file is present; GitHub code-scanning run evidence is still required."
                warnings.append(detail)
                status = "workflow_ready"
                next_step = "Run the GitHub CodeQL workflow on a code-scanning-enabled repository and capture alert/SARIF evidence."
        else:
            detail = "CODEQL_ENABLED is true, but no CodeQL workflow file is present under .github/workflows."
            blockers.append(detail)
            status = "blocked"
            next_step = "Add the recommended CodeQL workflow and capture credentialed alert-fetch evidence."
        scanners.append(
            ScannerStatus(
                name="codeql",
                env_key="CODEQL_ENABLED",
                enabled=True,
                status=status,
                detail=detail,
                required_for_release=True,
                tools=["codeql"],
                next_step=next_step,
            )
        )
    else:
        if codeql_workflow_present:
            detail = "CODEQL_ENABLED is false; CodeQL workflow is present, but SARIF/alert evidence remains credential-blocked."
            next_step = "Set CODEQL_ENABLED=true after GitHub credentials and code-scanning/Advanced Security access are verified."
        else:
            detail = "CODEQL_ENABLED is false; CodeQL SARIF/alert evidence remains credential-blocked."
            next_step = "Add/enable CodeQL workflow proof and set CODEQL_ENABLED=true after GitHub credentials and code-scanning/Advanced Security access are verified."
        warnings.append(detail)
        scanners.append(
            ScannerStatus(
                name="codeql",
                env_key="CODEQL_ENABLED",
                enabled=False,
                status="disabled",
                detail=detail,
                required_for_release=True,
                tools=["codeql"],
                next_step=next_step,
            )
        )

    release_scanner_proof_ready = (
        not blockers
        and not warnings
        and all(scanner.status == "ready" for scanner in scanners if scanner.required_for_release)
    )
    return SecurityScannerSnapshot(
        generated_at=datetime.now(timezone.utc).isoformat(),
        root=str(root),
        release_scanner_proof_ready=release_scanner_proof_ready,
        environment=env_flags,
        dependency_manifests=dependency_manifests,
        codeql_workflow_present=codeql_workflow_present,
        tool_versions=versions,
        scanners=scanners,
        warnings=warnings,
        blockers=blockers,
    )


def render_markdown(snapshot: SecurityScannerSnapshot) -> str:
    lines = [
        "# RepoPilot Security Scanner Snapshot",
        "",
        f"- Generated at: `{snapshot.generated_at}`",
        f"- Root: `{snapshot.root}`",
        f"- Release scanner proof ready: `{snapshot.release_scanner_proof_ready}`",
        f"- CodeQL workflow present: `{snapshot.codeql_workflow_present}`",
        f"- Dependency manifests found: `{len(snapshot.dependency_manifests)}`",
        "",
        "## Scanner Status",
        "",
        "| Scanner | Env Key | Enabled | Status | Required For Release | Detail | Next Step |",
        "|---|---|---|---|---|---|---|",
    ]
    for scanner in snapshot.scanners:
        lines.append(
            "| "
            + " | ".join(
                [
                    scanner.name,
                    scanner.env_key or "",
                    str(scanner.enabled),
                    scanner.status,
                    str(scanner.required_for_release),
                    scanner.detail.replace("|", "/"),
                    (scanner.next_step or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Tool Availability",
            "",
            "| Tool | Available | Version | Detail |",
            "|---|---|---|---|",
        ]
    )
    for tool in snapshot.tool_versions:
        lines.append(
            "| "
            + " | ".join(
                [
                    tool.name,
                    str(tool.available),
                    (tool.version or "").replace("|", "/"),
                    (tool.detail or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.extend(["", "## Dependency Manifests", ""])
    if snapshot.dependency_manifests:
        for manifest in snapshot.dependency_manifests:
            lines.append(f"- `{manifest}`")
    else:
        lines.append("- None found.")
    if snapshot.blockers:
        lines.extend(["", "## Blockers", ""])
        lines.extend(f"- {item}" for item in snapshot.blockers)
    if snapshot.warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {item}" for item in snapshot.warnings)
    lines.append("")
    return "\n".join(lines)


def write_outputs(*, snapshot: SecurityScannerSnapshot, json_out: Path, md_out: Path) -> None:
    json_out.parent.mkdir(parents=True, exist_ok=True)
    md_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(snapshot.as_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_out.write_text(render_markdown(snapshot), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Capture redacted security scanner readiness evidence.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--json-out", type=Path, default=DEFAULT_JSON_OUT)
    parser.add_argument("--md-out", type=Path, default=DEFAULT_MD_OUT)
    parser.add_argument("--allow-warnings", action="store_true")
    parser.add_argument("--allow-blockers", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    snapshot = collect_snapshot(root=args.root)
    write_outputs(snapshot=snapshot, json_out=args.json_out, md_out=args.md_out)
    print(json.dumps(snapshot.as_dict(), indent=2, sort_keys=True))
    if snapshot.blockers and not args.allow_blockers:
        return 2
    if snapshot.warnings and not args.allow_warnings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
