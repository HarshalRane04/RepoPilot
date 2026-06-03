from app.services.ci_analyzer import failure_reasons


def test_failure_reasons_extract_error_lines() -> None:
    assert failure_reasons("ok\nERROR failed\nTraceback: boom") == ["ERROR failed", "Traceback: boom"]

