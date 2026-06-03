from app.services.planning import plan_hash_matches


def test_stale_approved_plan_hash_is_rejected() -> None:
    assert plan_hash_matches("new", "old") is False

