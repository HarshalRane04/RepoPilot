def summarize_run(state: str) -> dict[str, str]:
    return {"state": state, "status": "active" if state not in {"READY_FOR_REVIEW", "BLOCKED"} else "terminal"}

