from app.services.eval_runner import score_outcomes


def test_eval_outcomes_score() -> None:
    assert score_outcomes([{"status": "passed"}, {"status": "failed"}]) == 0.5

