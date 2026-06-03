def create_revision_plan(parent_plan_id: str, ci_summary: str) -> dict[str, str]:
    return {"parent_plan_id": parent_plan_id, "summary": ci_summary, "approval_status": "waiting"}

