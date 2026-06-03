def approved_write_path(path: str, approved_paths: list[str]) -> bool:
    return path in approved_paths or any(path.startswith(prefix.rstrip("/") + "/") for prefix in approved_paths)

