from __future__ import annotations

import asyncio
from uuid import uuid4

from app.api.routes.prs import _pr_mode
from app.db.models import AgentStep, PullRequest


class FakeScalarResult:
    def __init__(self, step: AgentStep | None) -> None:
        self.step = step

    def scalar_one_or_none(self) -> AgentStep | None:
        return self.step


class FakeDb:
    def __init__(self, step: AgentStep | None) -> None:
        self.step = step

    async def execute(self, _statement: object) -> FakeScalarResult:
        return FakeScalarResult(self.step)


async def mode_for(pr: PullRequest, step: AgentStep | None) -> str:
    return await _pr_mode(pr, FakeDb(step))  # type: ignore[arg-type]


def test_pr_mode_prefers_local_step_evidence() -> None:
    run_id = uuid4()
    pr = PullRequest(id=uuid4(), run_id=run_id, pr_number=3, url="https://github.com/acme/demo/pull/3")
    step = AgentStep(run_id=run_id, step_name="OPEN_DRAFT_PR", output_json={"mode": "local_record"}, status="succeeded")

    assert asyncio.run(mode_for(pr, step)) == "local_record"


def test_pr_mode_prefers_real_github_step_evidence() -> None:
    run_id = uuid4()
    pr = PullRequest(id=uuid4(), run_id=run_id, pr_number=3, url="https://github.example.com/acme/demo/pull/3")
    step = AgentStep(run_id=run_id, step_name="OPEN_DRAFT_PR", output_json={"mode": "real_github_write"}, status="succeeded")

    assert asyncio.run(mode_for(pr, step)) == "real_github"


def test_pr_mode_legacy_url_fallbacks() -> None:
    local = PullRequest(id=uuid4(), run_id=uuid4(), pr_number=1, url="local://repopilot/draft-pr/1")
    real = PullRequest(id=uuid4(), run_id=uuid4(), pr_number=2, url="https://github.com/acme/demo/pull/2")

    assert asyncio.run(mode_for(local, None)) == "local_record"
    assert asyncio.run(mode_for(real, None)) == "real_github"
