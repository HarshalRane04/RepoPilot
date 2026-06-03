from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_JSON_OUT = Path("Docs/release-artifacts/source-boundary-manifest.json")
DEFAULT_MD_OUT = Path("Docs/release-artifacts/source-boundary-manifest.md")
DEFAULT_EXCLUDED_OUTPUTS = {DEFAULT_JSON_OUT.as_posix(), DEFAULT_MD_OUT.as_posix()}


@dataclass(frozen=True)
class ManifestEntry:
    path: str
    kind: str
    bytes: int
    sha256: str

    def as_dict(self) -> dict[str, object]:
        return {"path": self.path, "kind": self.kind, "bytes": self.bytes, "sha256": self.sha256}


@dataclass(frozen=True)
class SourceBoundaryManifest:
    root: str
    generated_at: str
    head_sha: str | None
    status_count: int
    file_count: int
    total_bytes: int
    manifest_sha256: str
    excluded_outputs: tuple[str, ...]
    entries: tuple[ManifestEntry, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "root": self.root,
            "generated_at": self.generated_at,
            "head_sha": self.head_sha,
            "status_count": self.status_count,
            "file_count": self.file_count,
            "total_bytes": self.total_bytes,
            "manifest_sha256": self.manifest_sha256,
            "excluded_outputs": list(self.excluded_outputs),
            "entries": [entry.as_dict() for entry in self.entries],
        }


class SourceBoundaryManifestBuilder:
    def __init__(self, *, root: Path, excluded_outputs: set[str] | None = None) -> None:
        self.root = root.resolve()
        self.excluded_outputs = excluded_outputs if excluded_outputs is not None else set(DEFAULT_EXCLUDED_OUTPUTS)

    def build(self) -> SourceBoundaryManifest:
        paths = self.git_source_paths()
        entries = tuple(self.entry_for_path(path) for path in paths)
        total_bytes = sum(entry.bytes for entry in entries)
        digest = hashlib.sha256()
        for entry in entries:
            digest.update(entry.path.encode("utf-8"))
            digest.update(b"\0")
            digest.update(entry.kind.encode("utf-8"))
            digest.update(b"\0")
            digest.update(str(entry.bytes).encode("utf-8"))
            digest.update(b"\0")
            digest.update(entry.sha256.encode("utf-8"))
            digest.update(b"\n")
        return SourceBoundaryManifest(
            root=str(self.root),
            generated_at=datetime.now(timezone.utc).isoformat(),
            head_sha=self.git_head_sha(),
            status_count=len(self.git_status_lines()),
            file_count=len(entries),
            total_bytes=total_bytes,
            manifest_sha256=digest.hexdigest(),
            excluded_outputs=tuple(sorted(self.excluded_outputs)),
            entries=entries,
        )

    def git_source_paths(self) -> list[str]:
        result = self.run_git(["ls-files", "--cached", "--others", "--exclude-standard", "-z"])
        raw_paths = [item for item in result.stdout.split("\0") if item]
        paths = [path for path in raw_paths if path not in self.excluded_outputs and (self.root / path).exists()]
        return sorted(paths)

    def entry_for_path(self, relative_path: str) -> ManifestEntry:
        path = self.root / relative_path
        if path.is_symlink():
            target = path.readlink().as_posix().encode("utf-8")
            return ManifestEntry(path=relative_path, kind="symlink", bytes=len(target), sha256=hashlib.sha256(target).hexdigest())
        data = path.read_bytes()
        return ManifestEntry(path=relative_path, kind="file", bytes=len(data), sha256=hashlib.sha256(data).hexdigest())

    def git_head_sha(self) -> str | None:
        result = self.run_git(["rev-parse", "--verify", "HEAD"], check=False)
        if result.returncode != 0:
            return None
        return result.stdout.strip()

    def git_status_lines(self) -> list[str]:
        result = self.run_git(["status", "--porcelain"], check=False)
        return [line for line in result.stdout.splitlines() if line.strip()]

    def run_git(self, args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", *args], cwd=self.root, capture_output=True, check=check, text=True)


def render_markdown(manifest: SourceBoundaryManifest, *, max_entries: int = 80) -> str:
    lines = [
        "# RepoPilot Source-Boundary Manifest",
        "",
        f"- Root: `{manifest.root}`",
        f"- Generated at: `{manifest.generated_at}`",
        f"- Git HEAD: `{manifest.head_sha or 'none'}`",
        f"- Git status entries: `{manifest.status_count}`",
        f"- Source candidate files: `{manifest.file_count}`",
        f"- Total bytes: `{manifest.total_bytes}`",
        f"- Manifest SHA-256: `{manifest.manifest_sha256}`",
        f"- Excluded self-output files: `{', '.join(manifest.excluded_outputs)}`",
        "",
        "| Path | Type | Bytes | SHA-256 |",
        "|---|---|---:|---|",
    ]
    for entry in manifest.entries[:max_entries]:
        lines.append(f"| `{entry.path}` | {entry.kind} | {entry.bytes} | `{entry.sha256}` |")
    remaining = manifest.file_count - max_entries
    if remaining > 0:
        lines.extend(["", f"_JSON manifest contains {remaining} additional file entries._"])
    lines.append("")
    return "\n".join(lines)


def write_outputs(*, manifest: SourceBoundaryManifest, json_out: Path | None, md_out: Path | None) -> None:
    if json_out:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps(manifest.as_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if md_out:
        md_out.parent.mkdir(parents=True, exist_ok=True)
        md_out.write_text(render_markdown(manifest), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a source-boundary manifest using Git ignore rules.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--json-out", type=Path, default=DEFAULT_JSON_OUT)
    parser.add_argument("--md-out", type=Path, default=DEFAULT_MD_OUT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    json_out = args.json_out if args.json_out.is_absolute() else root / args.json_out
    md_out = args.md_out if args.md_out.is_absolute() else root / args.md_out
    excluded = {path.relative_to(root).as_posix() if path.is_absolute() and path.is_relative_to(root) else path.as_posix() for path in (json_out, md_out)}
    manifest = SourceBoundaryManifestBuilder(root=root, excluded_outputs=excluded).build()
    write_outputs(manifest=manifest, json_out=json_out, md_out=md_out)
    print(render_markdown(manifest, max_entries=20))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
