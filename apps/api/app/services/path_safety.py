from __future__ import annotations

from pathlib import Path, PurePath


class UnsafePathError(ValueError):
    pass


def existing_directory_under_root(path_value: str, *, root_value: str, label: str) -> Path:
    configured_root = Path(root_value).expanduser()
    root = configured_root.resolve()
    try:
        candidate = _candidate_below_resolved_root(path_value, configured_root=configured_root, root=root, label=label)
        resolved_candidate = candidate.resolve(strict=True)
    except OSError as exc:
        raise UnsafePathError(f"{label} path could not be resolved.") from exc
    if not resolved_candidate.is_dir():
        raise UnsafePathError(f"{label} path is not a directory.")
    try:
        resolved_candidate.relative_to(root)
    except ValueError as exc:
        raise UnsafePathError(f"{label} path is outside the allowed root: {root}") from exc
    return resolved_candidate


def exact_existing_directory(path_value: str, *, expected: Path, label: str) -> Path:
    expected_resolved = expected.expanduser().resolve()
    supplied = path_value.strip()
    if supplied not in {str(expected), str(expected_resolved)}:
        raise UnsafePathError(f"{label} path must be the isolated run workspace: {expected_resolved}")
    if not expected_resolved.is_dir():
        raise UnsafePathError(f"{label} path is not a directory.")
    return expected_resolved


def _candidate_below_resolved_root(path_value: str, *, configured_root: Path, root: Path, label: str) -> Path:
    raw = path_value.strip()
    if not raw:
        raise UnsafePathError(f"{label} path is required.")
    if raw.startswith("~"):
        raise UnsafePathError(f"{label} path must be an absolute path under {root}.")
    lexical_candidate = PurePath(raw)
    if lexical_candidate.is_absolute():
        relative_parts = _relative_parts_for_any_root(
            lexical_candidate,
            roots=(PurePath(configured_root), PurePath(root)),
        )
        if relative_parts is None:
            raise UnsafePathError(f"{label} path is outside the allowed root: {root}")
    else:
        relative_parts = lexical_candidate.parts
    if any(part in {"", ".", ".."} for part in relative_parts):
        raise UnsafePathError(f"{label} path contains unsafe traversal segments.")
    candidate = root.joinpath(*relative_parts)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise UnsafePathError(f"{label} path is outside the allowed root: {root}") from exc
    return candidate


def _relative_parts_for_any_root(candidate: PurePath, *, roots: tuple[PurePath, ...]) -> tuple[str, ...] | None:
    for root in roots:
        try:
            return candidate.relative_to(root).parts
        except ValueError:
            continue
    return None
