ALLOWLISTED_COMMANDS = {"python -m pytest", "npm test", "npm run typecheck"}
HIGH_RISK_PATHS = (".github/workflows/", "app/services/auth", "app/db/models.py")


def command_allowed(command: str) -> bool:
    return any(command.startswith(prefix) for prefix in ALLOWLISTED_COMMANDS)


def path_requires_escalation(path: str) -> bool:
    return any(path.startswith(prefix) or path == prefix for prefix in HIGH_RISK_PATHS)

