from __future__ import annotations

from pathlib import Path

from scripts.ui_truth_guard import render_markdown, scan_targets


def write_ui_targets(root: Path, *, layout: str, console: str) -> None:
    root.joinpath("apps/web/app").mkdir(parents=True)
    root.joinpath("apps/web/app/layout.tsx").write_text(layout, encoding="utf-8")
    root.joinpath("apps/web/app/operator-console.tsx").write_text(console, encoding="utf-8")


def truthful_layout() -> str:
    return 'export const metadata = { description: "Local-first GitHub issue planning" };\n'


def truthful_console() -> str:
    return "\n".join(
        [
            "Draft PR records",
            "CI Evidence Analyzer",
            "Verify with live call",
            "External data transfer",
            "source-transfer consent",
        ]
    )


def test_ui_truth_guard_passes_for_current_copy_contract(tmp_path: Path) -> None:
    write_ui_targets(tmp_path, layout=truthful_layout(), console=truthful_console())

    report = scan_targets(tmp_path)

    assert report.failed is False
    assert "Status: `passed`" in render_markdown(report)


def test_ui_truth_guard_fails_on_overclaim_and_missing_privacy_copy(tmp_path: Path) -> None:
    write_ui_targets(
        tmp_path,
        layout='export const metadata = { description: "Agentic GitHub Development" };\n',
        console="Generate production-ready code and open draft pull requests.\nModel provider saved securely.\n",
    )

    report = scan_targets(tmp_path)

    assert report.failed is True
    assert any(finding.check == "banned_phrase" and finding.phrase == "production-ready code" for finding in report.findings)
    assert any(finding.check == "banned_phrase" and finding.phrase == "Model provider saved securely" for finding in report.findings)
    assert any(finding.check == "required_phrase" and finding.phrase == "External data transfer" for finding in report.findings)


def test_ui_truth_guard_scans_current_repo_copy() -> None:
    report = scan_targets(Path(__file__).resolve().parents[3])

    assert report.failed is False
