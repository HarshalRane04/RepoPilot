def score_outcomes(outcomes: list[dict[str, object]]) -> float:
    if not outcomes:
        return 0.0
    return sum(1 for item in outcomes if item.get("status") == "passed") / len(outcomes)

