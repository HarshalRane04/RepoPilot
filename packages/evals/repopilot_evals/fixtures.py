from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from repopilot_contracts import EvalTaskFixture


@dataclass(frozen=True)
class FixtureCheckSummary:
    required: int
    present: int


class FixtureVerifier:
    def __init__(self, *, fixture_root: Path) -> None:
        self.fixture_root = fixture_root

    def fixture_path(self, task: EvalTaskFixture) -> Path:
        return (self.fixture_root / task.fixture_repository).resolve()

    def repository_is_executable(self, fixture_path: Path) -> bool:
        if not fixture_path.is_dir():
            return False
        if (fixture_path / "pyproject.toml").is_file() and (fixture_path / "tests").is_dir():
            return True
        if (fixture_path / "package.json").is_file():
            return True
        return False

    def evaluate_task(self, task: EvalTaskFixture) -> list[str]:
        fixture_path = self.fixture_path(task)
        if not fixture_path.is_dir():
            return [f"Fixture repository is missing: {task.fixture_repository}"]
        return [
            *self.file_failures(task=task, fixture_path=fixture_path),
            *self.command_failures(task=task, fixture_path=fixture_path),
            *self.executable_failures(task=task, fixture_path=fixture_path),
        ]

    def file_failures(self, *, task: EvalTaskFixture, fixture_path: Path) -> list[str]:
        failures: list[str] = []
        for relative_path in task.expected_changed_files:
            if relative_path == "*":
                continue
            if not (fixture_path / relative_path).is_file():
                failures.append(f"Expected file missing from fixture repository: {relative_path}")
        return failures

    def command_failures(self, *, task: EvalTaskFixture, fixture_path: Path) -> list[str]:
        failures: list[str] = []
        for command in task.expected_tests:
            if command == "docs link check":
                if not (fixture_path / "README.md").is_file() or not (fixture_path / "Docs").is_dir():
                    failures.append("docs link check requires README.md and Docs/.")
                continue
            if command == "npm test":
                if not (fixture_path / "package.json").is_file():
                    failures.append("npm test requires package.json.")
                continue
            if command == "policy evaluation":
                if not (fixture_path / "app/services/policy.py").is_file():
                    failures.append("policy evaluation requires app/services/policy.py.")
                continue
            if command == "triage fixture":
                if not task.issue_body:
                    failures.append("triage fixture requires issue body.")
                continue
            if command.startswith("python -m pytest "):
                test_path = command.removeprefix("python -m pytest ").strip()
                if not (fixture_path / test_path).is_file():
                    failures.append(f"pytest command references missing file: {test_path}")
                continue
            failures.append(f"Unsupported expected test command in fixture metadata: {command}")
        return failures

    def executable_failures(self, *, task: EvalTaskFixture, fixture_path: Path) -> list[str]:
        if task.fixture_repository.endswith("python-service"):
            required = ["pyproject.toml", "app/__init__.py", "tests"]
        elif task.fixture_repository.endswith("web-dashboard"):
            required = ["package.json", "apps/web/app/operator-console.tsx", "apps/web/lib/api.ts"]
        else:
            required = []
        return [f"Executable fixture marker missing: {path}" for path in required if not (fixture_path / path).exists()]

    def file_check_summary(self, tasks: list[EvalTaskFixture]) -> FixtureCheckSummary:
        required = 0
        present = 0
        for task in tasks:
            fixture_path = self.fixture_path(task)
            for relative_path in task.expected_changed_files:
                if relative_path == "*":
                    continue
                required += 1
                if (fixture_path / relative_path).is_file():
                    present += 1
        return FixtureCheckSummary(required=required, present=present)

