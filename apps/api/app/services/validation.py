from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from app.services.policy import PolicyEngine


@dataclass(frozen=True)
class ProjectProfile:
    language: str
    frameworks: list[str] = field(default_factory=list)
    validation_commands: list[str] = field(default_factory=list)


class ProjectDetector:
    def detect(self, workspace_path: str | Path) -> ProjectProfile:
        workspace = Path(workspace_path).expanduser().resolve()
        frameworks: list[str] = []
        commands: list[str] = []

        package_json = workspace / "package.json"
        if package_json.is_file():
            scripts = self._package_scripts(package_json)
            language = "typescript" if (workspace / "tsconfig.json").is_file() else "javascript"
            if "next" in self._package_text(package_json):
                frameworks.append("Next.js")
            for script, command in (
                ("test", "npm test"),
                ("lint", "npm run lint"),
                ("typecheck", "npm run typecheck"),
            ):
                if script in scripts:
                    commands.append(command)
            return ProjectProfile(language=language, frameworks=frameworks, validation_commands=commands or ["npm test"])

        if (workspace / "go.mod").is_file():
            return ProjectProfile(language="go", frameworks=["Go"], validation_commands=["go test ./..."])

        python_files = list(workspace.glob("*.py")) + list(workspace.glob("src/**/*.py")) + list(workspace.glob("app/**/*.py"))
        if python_files or (workspace / "pyproject.toml").is_file() or (workspace / "pytest.ini").is_file():
            if (workspace / "pytest.ini").is_file() or (workspace / "tests").is_dir():
                frameworks.append("pytest")
            commands.append("python -m pytest")
            if self._has_ruff_config(workspace):
                commands.append("ruff check .")
            if self._has_mypy_config(workspace):
                commands.append("mypy .")
            return ProjectProfile(language="python", frameworks=frameworks, validation_commands=commands)

        return ProjectProfile(language="unknown", frameworks=[], validation_commands=["pytest"])

    def _package_scripts(self, package_json: Path) -> set[str]:
        try:
            payload = json.loads(package_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return set()
        scripts = payload.get("scripts")
        if not isinstance(scripts, dict):
            return set()
        return {str(script) for script in scripts}

    def _package_text(self, package_json: Path) -> str:
        return package_json.read_text(encoding="utf-8", errors="ignore").lower()

    def _has_ruff_config(self, workspace: Path) -> bool:
        pyproject = workspace / "pyproject.toml"
        return pyproject.is_file() and "ruff" in pyproject.read_text(encoding="utf-8", errors="ignore").lower()

    def _has_mypy_config(self, workspace: Path) -> bool:
        pyproject = workspace / "pyproject.toml"
        return (
            (workspace / "mypy.ini").is_file()
            or (workspace / "setup.cfg").is_file()
            or (pyproject.is_file() and "mypy" in pyproject.read_text(encoding="utf-8", errors="ignore").lower())
        )


class ValidationPlanner:
    def __init__(self, *, policy_engine: PolicyEngine | None = None) -> None:
        self.policy_engine = policy_engine or PolicyEngine()

    def commands_for(self, *, workspace_path: str | Path, plan_commands: list[str]) -> list[str]:
        detector_commands = ProjectDetector().detect(workspace_path).validation_commands
        commands = [*plan_commands, *detector_commands]
        deduped: list[str] = []
        for command in commands:
            normalized = self._normalize(command)
            if not normalized or normalized in deduped:
                continue
            if self.policy_engine.is_command_allowed(normalized):
                deduped.append(normalized)
        return deduped or ["python -m pytest"]

    def _normalize(self, command: str) -> str:
        normalized = " ".join(command.split())
        if normalized == "pytest" or normalized.startswith("pytest "):
            return f"python -m {normalized}"
        if normalized == "python3 -m pytest" or normalized.startswith("python3 -m pytest "):
            return f"python{normalized.removeprefix('python3')}"
        return normalized
