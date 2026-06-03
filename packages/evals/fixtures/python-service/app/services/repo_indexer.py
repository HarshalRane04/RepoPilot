SKIPPED_FILENAMES = {".env", ".secrets"}


def should_index(path: str) -> bool:
    return not any(part in SKIPPED_FILENAMES for part in path.split("/"))

