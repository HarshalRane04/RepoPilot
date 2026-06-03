from __future__ import annotations

from pathlib import Path

from scripts.release_hygiene import ReleaseHygieneScanner, render_markdown


def write_required_ignore_files(root: Path) -> None:
    root.joinpath(".gitignore").write_text(
        "\n".join(
            [
                ".DS_Store",
                ".env",
                ".env.*",
                "!.env.example",
                ".secrets/",
                "apps/api/.secrets/",
                "__pycache__/",
                "*.py[cod]",
                "*.egg-info/",
                ".pytest_cache/",
                "node_modules/",
                ".next/",
                "*.tsbuildinfo",
                "celerybeat-schedule",
                "apps/api/celerybeat-schedule",
            ]
        ),
        encoding="utf-8",
    )
    root.joinpath(".dockerignore").write_text(
        "\n".join(
            [
                ".git",
                ".env",
                ".env.*",
                ".secrets",
                "apps/api/.secrets",
                ".DS_Store",
                ".pytest_cache",
                "__pycache__",
                "*.pyc",
                "*.egg-info",
                "apps/web/node_modules",
                "apps/web/.next",
                "Docs",
                "Images",
                "celerybeat-schedule",
                "apps/api/celerybeat-schedule",
            ]
        ),
        encoding="utf-8",
    )


def test_release_hygiene_scanner_reports_generated_artifacts_and_secret_patterns(tmp_path: Path) -> None:
    write_required_ignore_files(tmp_path)
    tmp_path.joinpath(".git").mkdir()
    tmp_path.joinpath("apps/api/.secrets").mkdir(parents=True)
    tmp_path.joinpath("apps/api/.secrets/config.json").write_text("{}", encoding="utf-8")
    tmp_path.joinpath("README.md").write_text("sk-or-v1-" + "abcdefghijklmnopqrstuvwxyz", encoding="utf-8")
    tmp_path.joinpath("README 2.md").write_text("duplicate", encoding="utf-8")
    tmp_path.joinpath("apps/api/celerybeat-schedule").write_bytes(b"beat")
    tmp_path.joinpath("module.pyc").write_bytes(b"cache")

    report = ReleaseHygieneScanner(root=tmp_path).scan()
    findings = [finding.as_dict() for finding in report.findings]

    assert report.failed is True
    assert any(finding["check"] == "secret_store_path" for finding in findings)
    assert any(finding["check"] == "secret_content" and finding["path"] == "README.md" for finding in findings)
    assert any(finding["check"] == "generated_artifact" and finding["path"] == "module.pyc" for finding in findings)
    assert any(finding["check"] == "generated_artifact" and finding["path"] == "apps/api/celerybeat-schedule" for finding in findings)
    assert any(finding["check"] == "manual_review" and finding["status"] == "warning" for finding in findings)
    assert "abcdefghijklmnopqrstuvwxyz" not in render_markdown(report)


def test_release_hygiene_scanner_allows_documented_web_mount_points(tmp_path: Path) -> None:
    write_required_ignore_files(tmp_path)
    tmp_path.joinpath(".git").mkdir()
    tmp_path.joinpath("apps/web/node_modules").mkdir(parents=True)
    tmp_path.joinpath("apps/web/node_modules/docs.md").write_text("-----BEGIN " + "PRIVATE KEY-----\n", encoding="utf-8")
    tmp_path.joinpath("apps/web/.next").mkdir(parents=True)

    report = ReleaseHygieneScanner(root=tmp_path).scan()

    assert any(finding.path == "apps/web/node_modules" and finding.status == "warning" for finding in report.findings)
    assert any(finding.path == "apps/web/.next" and finding.status == "warning" for finding in report.findings)
    assert not any(
        finding.path in {"apps/web/node_modules", "apps/web/.next", "apps/web/node_modules/docs.md"}
        and finding.status == "failed"
        for finding in report.findings
    )


def test_release_hygiene_scanner_reports_missing_ignore_patterns(tmp_path: Path) -> None:
    tmp_path.joinpath(".gitignore").write_text(".DS_Store\n", encoding="utf-8")
    tmp_path.joinpath(".dockerignore").write_text(".git\n", encoding="utf-8")

    report = ReleaseHygieneScanner(root=tmp_path).scan()

    assert any(finding.check == "gitignore_pattern" and "Missing required pattern" in finding.detail for finding in report.findings)
    assert any(finding.check == "dockerignore_pattern" and "Missing required pattern" in finding.detail for finding in report.findings)


def test_release_hygiene_scanner_links_documented_duplicate_readme_decision(tmp_path: Path) -> None:
    write_required_ignore_files(tmp_path)
    tmp_path.joinpath(".git").mkdir()
    tmp_path.joinpath("README 2.md").write_text("duplicate", encoding="utf-8")
    tmp_path.joinpath("Docs").mkdir()
    tmp_path.joinpath("Docs/SOURCE_BOUNDARY_DECISIONS.md").write_text("README 2.md pending owner approval", encoding="utf-8")

    report = ReleaseHygieneScanner(root=tmp_path).scan()

    assert any(
        finding.check == "manual_review"
        and finding.path == "README 2.md"
        and "Docs/SOURCE_BOUNDARY_DECISIONS.md" in finding.detail
        for finding in report.findings
    )
