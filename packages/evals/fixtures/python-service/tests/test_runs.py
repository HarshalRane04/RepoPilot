from app.api.routes.runs import summarize_run


def test_ready_run_is_terminal() -> None:
    assert summarize_run("READY_FOR_REVIEW")["status"] == "terminal"

