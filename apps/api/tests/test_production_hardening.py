from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from repopilot_contracts import ImplementationPlan

from app.db.models import Issue
from app.services.path_safety import UnsafePathError, existing_directory_under_root
from app.services.planning import PlanningService
from app.services.url_safety import UnsafeUrlError, provider_base_url


def test_provider_base_url_rejects_private_or_unexpected_hosts() -> None:
    assert (
        provider_base_url(
            "https://openrouter.ai/api/v1",
            default_base_url="https://openrouter.ai/api/v1",
            provider_id="openrouter",
        )
        == "https://openrouter.ai/api/v1"
    )

    with pytest.raises(UnsafeUrlError):
        provider_base_url(
            "http://169.254.169.254/latest",
            default_base_url="https://openrouter.ai/api/v1",
            provider_id="openrouter",
        )

    with pytest.raises(UnsafeUrlError):
        provider_base_url(
            "https://evil.example.com/api/v1",
            default_base_url="https://openrouter.ai/api/v1",
            provider_id="openrouter",
        )


def test_existing_directory_under_root_rejects_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "repos"
    root.mkdir()
    safe_repo = root / "demo"
    safe_repo.mkdir()
    assert existing_directory_under_root(str(safe_repo), root_value=str(root), label="repo") == safe_repo.resolve()

    outside = tmp_path / "outside"
    outside.mkdir()
    escape = root / "escape"
    escape.symlink_to(outside, target_is_directory=True)
    with pytest.raises(UnsafePathError):
        existing_directory_under_root(str(escape), root_value=str(root), label="repo")


def test_docs_only_planning_ignores_source_file_context() -> None:
    issue = Issue(
        id=uuid4(),
        repository_id=uuid4(),
        number=7,
        title="Final audit operator prompt smoke",
        body_text="Create a documentation-only verification plan. Do not modify code.",
        issue_type="docs",
        risk_score=20,
    )

    plan = PlanningService()._build_plan(
        issue=issue,
        context_citations=["smoke_app.py:1-2", "Docs/RUNBOOK.md:10-20", "tests/test_smoke_app.py:1-5"],
    )

    assert plan.files_to_modify == ["Docs/RUNBOOK.md"]
    assert plan.tests_to_add == []
    assert "smoke_app.py" not in plan.files_to_inspect
    assert "documentation-only" in " ".join(plan.assumptions).lower()


def test_docs_only_planning_filters_model_code_plan() -> None:
    issue = Issue(
        id=uuid4(),
        repository_id=uuid4(),
        number=8,
        title="Docs only verification",
        body_text="Docs only. No code changes.",
        issue_type="docs",
        risk_score=20,
    )
    deterministic = PlanningService()._build_plan(issue=issue, context_citations=["Docs/RUNBOOK.md:1-4"])
    model_plan = ImplementationPlan(
        plan_id="candidate",
        issue_id=str(issue.id),
        summary="Modify smoke app",
        files_to_inspect=["smoke_app.py", "Docs/RUNBOOK.md"],
        files_to_modify=["smoke_app.py", "Docs/RUNBOOK.md"],
        tests_to_add=["tests/test_smoke_app.py"],
        commands_to_run=["pytest"],
        intended_changes=["Change smoke app", "Update docs"],
        validation_strategy=["Run tests"],
        assumptions=[],
        context_citations=["smoke_app.py:1-2", "Docs/RUNBOOK.md:1-4"],
        rollback_plan="Revert the PR.",
    )

    enforced = PlanningService()._enforce_issue_intent(issue=issue, plan=model_plan, deterministic_plan=deterministic)

    assert enforced.files_to_modify == ["Docs/RUNBOOK.md"]
    assert enforced.tests_to_add == []
    assert enforced.commands_to_run == []
    assert all(not path.endswith(".py") for path in enforced.files_to_modify)
