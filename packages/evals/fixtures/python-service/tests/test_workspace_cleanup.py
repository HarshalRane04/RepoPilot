from app.services.workspace_cleanup import stale_workspace


def test_old_run_workspace_is_stale() -> None:
    assert stale_workspace("/tmp/repopilot-agent-workspaces/run-1", age_seconds=90000)

