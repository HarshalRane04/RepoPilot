ROLE_MAP = {"admin": "owner", "maintain": "maintainer", "write": "developer", "triage": "triager", "read": "viewer"}


def map_github_role(role: str) -> str:
    return ROLE_MAP.get(role, "viewer")

