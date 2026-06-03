def failure_reasons(log: str) -> list[str]:
    return [line for line in log.splitlines() if "ERROR" in line or "Traceback" in line]

