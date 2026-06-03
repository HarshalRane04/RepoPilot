def stale_workspace(path: str, *, age_seconds: int, max_age_seconds: int = 86400) -> bool:
    return path.startswith("/tmp/repopilot-agent-workspaces/") and age_seconds > max_age_seconds

