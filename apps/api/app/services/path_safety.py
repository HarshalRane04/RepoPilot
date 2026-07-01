from __future__ import annotations

from pathlib import Path


class UnsafePathError(ValueError):
    pass


def existing_directory_under_root(path_value: str, *, root_value: str, label: str) -> Path:
    root = Path(root_value).expanduser().resolve()
    try:
        candidate = Path(path_value).expanduser().resolve(strict=True)
    except OSError as exc:
        raise UnsafePathError(f"{label} path could not be resolved.") from exc
    if not candidate.is_dir():
        raise UnsafePathError(f"{label} path is not a directory.")
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise UnsafePathError(f"{label} path is outside the allowed root: {root}") from exc
    return candidate


def exact_existing_directory(path_value: str, *, expected: Path, label: str) -> Path:
    try:
        candidate = Path(path_value).expanduser().resolve(strict=True)
    except OSError as exc:
        raise UnsafePathError(f"{label} path could not be resolved.") from exc
    expected_resolved = expected.expanduser().resolve()
    if candidate != expected_resolved:
        raise UnsafePathError(f"{label} path must be the isolated run workspace: {expected_resolved}")
    if not candidate.is_dir():
        raise UnsafePathError(f"{label} path is not a directory.")
    return candidate
