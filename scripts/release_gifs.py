from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class ReleaseGifFlow:
    name: str
    title: str
    proof: str
    inputs: tuple[str, ...]

    def output_name(self, stamp: str) -> str:
        return f"{self.name}-{stamp}.gif"


FLOWS = (
    ReleaseGifFlow(
        name="operator-console-plan-to-pr-flow",
        title="Plan To PR Evidence Flow",
        proof="Local operator journey through plan review, agent runs, run trace, and draft PR evidence surfaces.",
        inputs=(
            "operator-console-plan-review-2026-06-01.png",
            "operator-console-agent-runs-2026-06-01.png",
            "operator-console-run-trace-2026-06-01.png",
            "operator-console-pull-requests-2026-06-01.png",
        ),
    ),
    ReleaseGifFlow(
        name="operator-console-governance-flow",
        title="Governance Evidence Flow",
        proof="Local operator journey through security findings, evaluation metrics, readiness settings, and dashboard overview.",
        inputs=(
            "operator-console-security-2026-06-01.png",
            "operator-console-evaluations-2026-06-01.png",
            "operator-console-settings-2026-06-01.png",
            "operator-console-desktop-2026-06-01.png",
        ),
    ),
)


@dataclass(frozen=True)
class GifArtifact:
    flow: ReleaseGifFlow
    output_path: Path
    input_paths: tuple[Path, ...]

    def as_dict(self, root: Path) -> dict[str, object]:
        return {
            "name": self.flow.name,
            "title": self.flow.title,
            "proof": self.flow.proof,
            "output": relative_to_root(self.output_path, root),
            "inputs": [relative_to_root(path, root) for path in self.input_paths],
        }


def relative_to_root(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


class ReleaseGifBuilder:
    def __init__(
        self,
        *,
        root: Path,
        artifact_dir: Path,
        stamp: str,
        frame_duration_seconds: float,
        width: int,
        ffmpeg_bin: str,
    ) -> None:
        self.root = root.resolve()
        self.artifact_dir = artifact_dir.resolve()
        self.stamp = stamp
        self.frame_duration_seconds = frame_duration_seconds
        self.width = width
        self.ffmpeg_bin = ffmpeg_bin

    def plan(self) -> list[GifArtifact]:
        return [
            GifArtifact(
                flow=flow,
                output_path=self.artifact_dir / flow.output_name(self.stamp),
                input_paths=tuple(self.artifact_dir / item for item in flow.inputs),
            )
            for flow in FLOWS
        ]

    def missing_inputs(self) -> list[str]:
        missing: list[str] = []
        for artifact in self.plan():
            for input_path in artifact.input_paths:
                if not input_path.is_file():
                    missing.append(relative_to_root(input_path, self.root))
        return sorted(set(missing))

    def build(self, *, dry_run: bool = False) -> list[GifArtifact]:
        missing = self.missing_inputs()
        if missing:
            raise FileNotFoundError("Missing release GIF input screenshots: " + ", ".join(missing))
        artifacts = self.plan()
        if dry_run:
            return artifacts
        ffmpeg_path = shutil.which(self.ffmpeg_bin)
        if ffmpeg_path is None:
            raise RuntimeError(f"`{self.ffmpeg_bin}` is required to build release GIFs.")
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        for artifact in artifacts:
            self.build_artifact(artifact, ffmpeg_path=ffmpeg_path)
        return artifacts

    def build_artifact(self, artifact: GifArtifact, *, ffmpeg_path: str) -> None:
        with tempfile.TemporaryDirectory(prefix="repopilot-release-gif-") as tmpdir:
            frame_list = Path(tmpdir) / "frames.txt"
            frame_list.write_text(self.render_concat_file(artifact.input_paths), encoding="utf-8")
            filter_spec = (
                f"fps=2,scale={self.width}:-1:flags=lanczos,"
                "split[s0][s1];[s0]palettegen=max_colors=128[p];[s1][p]paletteuse=dither=bayer:bayer_scale=5"
            )
            subprocess.run(
                [
                    ffmpeg_path,
                    "-y",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    str(frame_list),
                    "-vf",
                    filter_spec,
                    str(artifact.output_path),
                ],
                check=True,
            )

    def render_concat_file(self, input_paths: tuple[Path, ...]) -> str:
        lines: list[str] = []
        for input_path in input_paths:
            lines.append(f"file '{input_path.as_posix()}'")
            lines.append(f"duration {self.frame_duration_seconds:.3f}")
        lines.append(f"file '{input_paths[-1].as_posix()}'")
        return "\n".join(lines) + "\n"


def render_markdown(*, artifacts: list[GifArtifact], root: Path, stamp: str, dry_run: bool) -> str:
    status = "planned" if dry_run else "generated"
    lines = [
        "# RepoPilot Release GIF Evidence",
        "",
        f"- Stamp: `{stamp}`",
        f"- Status: `{status}`",
        "- Scope: local operator-console visual-flow evidence only; this does not prove credentialed GitHub writes or live model quality.",
        "",
        "| Artifact | Proof | Inputs |",
        "|---|---|---|",
    ]
    for artifact in artifacts:
        output = relative_to_root(artifact.output_path, root)
        inputs = "<br>".join(relative_to_root(path, root) for path in artifact.input_paths)
        lines.append(f"| `{output}` | {artifact.flow.proof} | {inputs} |")
    lines.append("")
    return "\n".join(lines)


def write_outputs(*, artifacts: list[GifArtifact], root: Path, stamp: str, dry_run: bool, json_out: Path | None, md_out: Path | None) -> None:
    payload = {
        "stamp": stamp,
        "status": "planned" if dry_run else "generated",
        "scope": "local operator-console visual-flow evidence only",
        "artifacts": [artifact.as_dict(root) for artifact in artifacts],
    }
    if json_out:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if md_out:
        md_out.parent.mkdir(parents=True, exist_ok=True)
        md_out.write_text(render_markdown(artifacts=artifacts, root=root, stamp=stamp, dry_run=dry_run), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build RepoPilot release GIF evidence from captured operator-console screenshots.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--artifact-dir", type=Path, default=Path("Docs/release-artifacts"))
    parser.add_argument("--stamp", default=date.today().isoformat())
    parser.add_argument("--frame-duration-seconds", type=float, default=1.6)
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--ffmpeg-bin", default="ffmpeg")
    parser.add_argument("--json-out", type=Path, default=Path("Docs/release-artifacts/release-gifs.json"))
    parser.add_argument("--md-out", type=Path, default=Path("Docs/release-artifacts/release-gifs.md"))
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    artifact_dir = args.artifact_dir if args.artifact_dir.is_absolute() else root / args.artifact_dir
    builder = ReleaseGifBuilder(
        root=root,
        artifact_dir=artifact_dir,
        stamp=args.stamp,
        frame_duration_seconds=args.frame_duration_seconds,
        width=args.width,
        ffmpeg_bin=args.ffmpeg_bin,
    )
    artifacts = builder.build(dry_run=args.dry_run)
    json_out = args.json_out if args.json_out.is_absolute() else root / args.json_out
    md_out = args.md_out if args.md_out.is_absolute() else root / args.md_out
    write_outputs(artifacts=artifacts, root=root, stamp=args.stamp, dry_run=args.dry_run, json_out=json_out, md_out=md_out)
    print(render_markdown(artifacts=artifacts, root=root, stamp=args.stamp, dry_run=args.dry_run))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
