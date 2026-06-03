from app.services.revision_planner import create_revision_plan


def test_revision_plan_waits_for_approval() -> None:
    assert create_revision_plan("plan-1", "CI failed")["approval_status"] == "waiting"

