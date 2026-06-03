from __future__ import annotations

from pathlib import Path

import pytest

from scripts.release_gifs import FLOWS, ReleaseGifBuilder, render_markdown, write_outputs


def write_flow_inputs(root: Path) -> None:
    artifact_dir = root / "Docs/release-artifacts"
    artifact_dir.mkdir(parents=True)
    for flow in FLOWS:
        for input_name in flow.inputs:
            path = artifact_dir / input_name
            path.write_bytes(b"png")


def make_builder(root: Path) -> ReleaseGifBuilder:
    return ReleaseGifBuilder(
        root=root,
        artifact_dir=root / "Docs/release-artifacts",
        stamp="2026-06-03",
        frame_duration_seconds=1.6,
        width=960,
        ffmpeg_bin="ffmpeg",
    )


def test_release_gif_builder_reports_missing_inputs(tmp_path: Path) -> None:
    builder = make_builder(tmp_path)

    missing = builder.missing_inputs()

    assert "Docs/release-artifacts/operator-console-plan-review-2026-06-01.png" in missing
    with pytest.raises(FileNotFoundError):
        builder.build(dry_run=True)


def test_release_gif_builder_plans_expected_artifacts(tmp_path: Path) -> None:
    write_flow_inputs(tmp_path)
    builder = make_builder(tmp_path)

    artifacts = builder.build(dry_run=True)
    markdown = render_markdown(artifacts=artifacts, root=tmp_path, stamp="2026-06-03", dry_run=True)

    assert {artifact.flow.name for artifact in artifacts} == {"operator-console-plan-to-pr-flow", "operator-console-governance-flow"}
    assert "operator-console-plan-to-pr-flow-2026-06-03.gif" in markdown
    assert "local operator-console visual-flow evidence only" in markdown


def test_release_gif_builder_writes_manifest_outputs(tmp_path: Path) -> None:
    write_flow_inputs(tmp_path)
    artifacts = make_builder(tmp_path).build(dry_run=True)

    write_outputs(
        artifacts=artifacts,
        root=tmp_path,
        stamp="2026-06-03",
        dry_run=True,
        json_out=tmp_path / "Docs/release-artifacts/release-gifs.json",
        md_out=tmp_path / "Docs/release-artifacts/release-gifs.md",
    )

    assert "operator-console-governance-flow-2026-06-03.gif" in tmp_path.joinpath("Docs/release-artifacts/release-gifs.json").read_text(encoding="utf-8")
    assert "Release GIF Evidence" in tmp_path.joinpath("Docs/release-artifacts/release-gifs.md").read_text(encoding="utf-8")
