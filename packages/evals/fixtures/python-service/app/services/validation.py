def detect_commands(files: list[str]) -> list[str]:
    commands = []
    if any(path.endswith(".py") for path in files):
        commands.append("python -m pytest")
    if any(path.endswith((".ts", ".tsx")) for path in files):
        commands.append("npm test")
    return commands

