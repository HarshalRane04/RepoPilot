import pytest

from app.api.routes.security import update_finding_status


def test_false_positive_requires_reason() -> None:
    with pytest.raises(ValueError):
        update_finding_status("false_positive")

