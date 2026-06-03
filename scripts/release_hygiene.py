from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


FORBIDDEN_NAMES = {
    ".DS_Store",
    ".pytest_cache",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".next",
    "node_modules",
    "tsconfig.tsbuildinfo",
    "celerybeat-schedule",
}
FORBIDDEN_SUFFIXES = {".pyc", ".pyo"}
FORBIDDEN_DIR_SUFFIXES = {".egg-info"}
FORBIDDEN_SECRET_PATHS = {".secrets", "apps/api/.secrets"}
ALLOWED_MOUNT_POINTS = {"apps/web/node_modules", "apps/web/.next"}
SOURCE_BOUNDARY_DECISION_FILE = "Docs/SOURCE_BOUNDARY_DECISIONS.md"
REQUIRED_GITIGNORE_PATTERNS = {
    ".DS_Store",
    ".env",
    ".env.*",
    "!.env.example",
    ".secrets/",
    "apps/api/.secrets/",
    "__pycache__/",
    "*.py[cod]",
    "*.egg-info/",
    ".pytest_cache/",
    "node_modules/",
    ".next/",
    "*.tsbuildinfo",
    "celerybeat-schedule",
    "apps/api/celerybeat-schedule",
}
REQUIRED_DOCKERIGNORE_PATTERNS = {
    ".git",
    ".env",
    ".env.*",
    ".secrets",
    "apps/api/.secrets",
    ".DS_Store",
    ".pytest_cache",
    "__pycache__",
    "*.pyc",
    "*.egg-info",
    "apps/web/node_modules",
    "apps/web/.next",
    "Docs",
    "Images",
    "celerybeat-schedule",
    "apps/api/celerybeat-schedule",
}
SECRET_CONTENT_PATTERNS = {
    "openrouter_api_key": re.compile(r"sk-or-v1-[A-Za-z0-9]{16,}"),
    "github_oauth_secret": re.compile(r"github client secret\s*[:=]\s*[A-Za-z0-9]{20,}", re.IGNORECASE),
    "private_key_block": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY-----"),
}
SCAN_SUFFIXES = {
    ".env",
    ".example",
    ".json",
    ".md",
    ".py",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yml",
    ".yaml",
}


@dataclass
class HygieneFinding:
    check: str
    status: str
    path: str | None = None
    detail: str = ""

    def as_dict(self) -> dict[str, str | None]:
        return {"check": self.check, "status": self.status, "path": self.path, "detail": self.detail}


@dataclass
class HygieneReport:
    root: str
    findings: list[HygieneFinding] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        return any(finding.status == "failed" for finding in self.findings)

    @property
    def warning_count(self) -> int:
        return sum(1 for finding in self.findings if finding.status == "warning")

    @property
    def failed_count(self) -> int:
        return sum(1 for finding in self.findings if finding.status == "failed")

    def as_dict(self) -> dict[str, object]:
        return {
            "root": self.root,
            "failed": self.failed,
            "failed_count": self.failed_count,
            "warning_count": self.warning_count,
            "findings": [finding.as_dict() for finding in self.findings],
        }


class ReleaseHygieneScanner:
    def __init__(self, *, root: Path) -> None:
        self.root = root.resolve()

    def scan(self) -> HygieneReport:
        report = HygieneReport(root=str(self.root))
        self.scan_generated_artifacts(report)
        self.scan_ignore_files(report)
        self.scan_secret_content(report)
        self.scan_manual_review_items(report)
        self.scan_git_boundary(report)
        if not report.findings:
            report.findings.append(HygieneFinding(check="release_hygiene", status="passed", detail="No hygiene findings."))
        return report

    def scan_generated_artifacts(self, report: HygieneReport) -> None:
        for path in self.walk_paths():
            relative = self.relative(path)
            if self.is_allowed_mount_child(relative):
                continue
            if relative in ALLOWED_MOUNT_POINTS:
                report.findings.append(
                    HygieneFinding(
                        check="generated_artifact",
                        status="warning",
                        path=relative,
                        detail="Allowed Docker mount point; stop the web service before final source-boundary packaging if physical absence is required.",
                    )
                )
                continue
            if relative in FORBIDDEN_SECRET_PATHS or any(relative.startswith(f"{item}/") for item in FORBIDDEN_SECRET_PATHS):
                report.findings.append(
                    HygieneFinding(check="secret_store_path", status="failed", path=relative, detail="Runtime secret store must not be in the source boundary.")
                )
                continue
            if self.is_forbidden_generated_path(path):
                report.findings.append(
                    HygieneFinding(check="generated_artifact", status="failed", path=relative, detail="Generated artifact or cache path is present.")
                )
            if path.name.startswith(".env") and path.name != ".env.example":
                report.findings.append(
                    HygieneFinding(check="env_file", status="failed", path=relative, detail="Environment files other than .env.example must stay outside source control.")
                )

    def scan_ignore_files(self, report: HygieneReport) -> None:
        self.require_patterns(report, file_path=self.root / ".gitignore", required=REQUIRED_GITIGNORE_PATTERNS, check="gitignore_pattern")
        self.require_patterns(report, file_path=self.root / ".dockerignore", required=REQUIRED_DOCKERIGNORE_PATTERNS, check="dockerignore_pattern")

    def scan_secret_content(self, report: HygieneReport) -> None:
        for path in self.walk_paths():
            relative = self.relative(path)
            if self.is_allowed_mount_path(relative):
                continue
            if not path.is_file() or not self.should_scan_content(path):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for pattern_name, pattern in SECRET_CONTENT_PATTERNS.items():
                if pattern.search(text):
                    status = "warning" if pattern_name == "private_key_block" and relative.startswith("apps/api/tests/") else "failed"
                    report.findings.append(
                        HygieneFinding(
                            check="secret_content",
                            status=status,
                            path=relative,
                            detail=f"Secret-like content matched pattern {pattern_name}; value intentionally omitted.",
                        )
                    )

    def scan_manual_review_items(self, report: HygieneReport) -> None:
        duplicate_readme = self.root / "README 2.md"
        if duplicate_readme.exists():
            decision_file = self.root / SOURCE_BOUNDARY_DECISION_FILE
            if decision_file.is_file():
                detail = f"Duplicate README is documented in {SOURCE_BOUNDARY_DECISION_FILE}; owner decision is still required before release packaging."
            else:
                detail = "Duplicate README needs owner decision before release packaging."
            report.findings.append(
                HygieneFinding(
                    check="manual_review",
                    status="warning",
                    path="README 2.md",
                    detail=detail,
                )
            )

    def scan_git_boundary(self, report: HygieneReport) -> None:
        if not (self.root / ".git").exists():
            report.findings.append(HygieneFinding(check="git_boundary", status="failed", detail="Git repository is missing."))
            return
        head = self.run_git(["rev-parse", "--verify", "HEAD"])
        if head.returncode != 0:
            report.findings.append(HygieneFinding(check="git_boundary", status="failed", detail="No baseline commit exists yet."))
        status = self.run_git(["status", "--porcelain"])
        if status.stdout.strip():
            report.findings.append(
                HygieneFinding(
                    check="git_boundary",
                    status="warning",
                    detail="Working tree has uncommitted or untracked changes; release source boundary is not frozen.",
                )
            )

    def require_patterns(
        self,
        report: HygieneReport,
        *,
        file_path: Path,
        required: set[str],
        check: str,
    ) -> None:
        if not file_path.is_file():
            report.findings.append(HygieneFinding(check=check, status="failed", path=self.relative(file_path), detail="Ignore file is missing."))
            return
        patterns = {
            line.strip()
            for line in file_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        }
        for pattern in sorted(required.difference(patterns)):
            report.findings.append(
                HygieneFinding(check=check, status="failed", path=self.relative(file_path), detail=f"Missing required pattern: {pattern}")
            )

    def walk_paths(self) -> Iterable[Path]:
        skip_parts = {".git"}
        for path in self.root.rglob("*"):
            if any(part in skip_parts for part in path.relative_to(self.root).parts):
                continue
            yield path

    def is_forbidden_generated_path(self, path: Path) -> bool:
        if path.name in FORBIDDEN_NAMES:
            return True
        if path.suffix in FORBIDDEN_SUFFIXES:
            return True
        return any(path.name.endswith(suffix) for suffix in FORBIDDEN_DIR_SUFFIXES)

    def is_allowed_mount_path(self, relative: str) -> bool:
        return relative in ALLOWED_MOUNT_POINTS or self.is_allowed_mount_child(relative)

    def is_allowed_mount_child(self, relative: str) -> bool:
        return any(relative.startswith(f"{mount}/") for mount in ALLOWED_MOUNT_POINTS)

    def should_scan_content(self, path: Path) -> bool:
        relative = self.relative(path)
        if relative.startswith("Docs/RepoPilot_AI_") and path.suffix == ".docx":
            return False
        if path.stat().st_size > 500_000:
            return False
        if path.name == ".env.example":
            return True
        if path.suffix in SCAN_SUFFIXES:
            return True
        return fnmatch.fnmatch(path.name, ".env*")

    def relative(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.root).as_posix()
        except ValueError:
            return path.as_posix()

    def run_git(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", *args], cwd=self.root, text=True, capture_output=True, check=False)


def render_markdown(report: HygieneReport) -> str:
    lines = [
        "# RepoPilot Release Hygiene Report",
        "",
        f"- Root: `{report.root}`",
        f"- Failed findings: `{report.failed_count}`",
        f"- Warnings: `{report.warning_count}`",
        "",
        "| Check | Status | Path | Detail |",
        "|---|---|---|---|",
    ]
    for finding in report.findings:
        lines.append(
            "| "
            + " | ".join(
                [
                    finding.check,
                    finding.status,
                    finding.path or "",
                    finding.detail.replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scan RepoPilot source-boundary release hygiene.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--md-out", type=Path, default=None)
    parser.add_argument("--allow-warnings", action="store_true")
    parser.add_argument("--allow-failures", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = ReleaseHygieneScanner(root=args.root).scan()
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
