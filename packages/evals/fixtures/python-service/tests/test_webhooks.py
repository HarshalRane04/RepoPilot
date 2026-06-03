from app.services.github_webhooks import normalize_event


def test_normalize_event_keeps_action() -> None:
    assert normalize_event("issues", {"action": "opened"})["action"] == "opened"

