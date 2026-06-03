from app.services.validation import detect_commands


def test_python_detection_returns_pytest() -> None:
    assert detect_commands(["app/demo.py"]) == ["python -m pytest"]

