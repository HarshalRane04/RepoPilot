def update_finding_status(status: str, *, reason: str | None = None) -> dict[str, str | None]:
    if status in {"acknowledged", "false_positive"} and not reason:
        raise ValueError("reason is required")
    return {"status": status, "reason": reason}

