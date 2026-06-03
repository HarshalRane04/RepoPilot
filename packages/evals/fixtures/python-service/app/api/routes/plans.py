def approve_plan(plan: dict[str, object], *, plan_hash: str) -> dict[str, object]:
    updated = dict(plan)
    updated["approval_status"] = "approved"
    updated["approved_plan_hash"] = plan_hash
    return updated

