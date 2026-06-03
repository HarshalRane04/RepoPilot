def normalize_event(event_type: str, payload: dict[str, object]) -> dict[str, object]:
    return {"event_type": event_type, "action": payload.get("action")}

