def eval_report(task_outcomes: list[dict[str, object]]) -> dict[str, object]:
    return {"task_outcomes": task_outcomes, "task_count": len(task_outcomes)}

