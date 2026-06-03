from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.source_boundary_manifest import SourceBoundaryManifestBuilder, render_markdown, write_outputs


def init_git_repo(root: Path) -> None:
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True, text=True)


def test_source_boundary_manifest_uses_git_ignore_rules_and_hashes_files(tmp_path: Path) -> None:
    init_git_repo(tmp_path)
    tmp_path.joinpath(".gitignore").write_text("ignored.txt\n", encoding="utf-8")
    tmp_path.joinpath("README.md").write_text("hello\n", encoding="utf-8")
    tmp_path.joinpath("ignored.txt").write_text("skip me\n", encoding="utf-8")
    tmp_path.joinpath("Docs/release-artifacts").mkdir(parents=True)
    tmp_path.joinpath("Docs/release-artifacts/source-boundary-manifest.json").write_text("old", encoding="utf-8")
    tmp_path.joinpath("Docs/release-artifacts/source-boundary-manifest.md").write_text("old", encoding="utf-8")

    manifest = SourceBoundaryManifestBuilder(root=tmp_path).build()

    paths = {entry.path for entry in manifest.entries}
    assert "README.md" in paths
    assert ".gitignore" in paths
    assert "ignored.txt" not in paths
    assert "Docs/release-artifacts/source-boundary-manifest.json" not in paths
    assert manifest.file_count == 2
    assert len(manifest.manifest_sha256) == 64


def test_source_boundary_manifest_writes_markdown_and_json(tmp_path: Path) -> None:
    init_git_repo(tmp_path)
    tmp_path.joinpath("README.md").write_text("hello\n", encoding="utf-8")
    manifest = SourceBoundaryManifestBuilder(root=tmp_path).build()
    json_out = tmp_path / "Docs/release-artifacts/source-boundary-manifest.json"
    md_out = tmp_path / "Docs/release-artifacts/source-boundary-manifest.md"

    write_outputs(manifest=manifest, json_out=json_out, md_out=md_out)

    assert "README.md" in json_out.read_text(encoding="utf-8")
    assert "Source-Boundary Manifest" in md_out.read_text(encoding="utf-8")
    assert manifest.manifest_sha256 in render_markdown(manifest)
