from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.security_scanner_snapshot import collect_snapshot, render_markdown, write_outputs


def test_scanner_snapshot_records_disabled_external_scanners(tmp_path: Path, monkeypatch) -> None:
    tmp_path.joinpath("apps/web").mkdir(parents=True)
    tmp_path.joinpath("apps/web/package-lock.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr("scripts.security_scanner_snapshot.shutil.which", lambda name: None)

    snapshot = collect_snapshot(root=tmp_path, env={})
    markdown = render_markdown(snapshot)

    assert snapshot.release_scanner_proof_ready is False
    assert snapshot.blockers == []
    assert len(snapshot.warnings) == 3
    assert "apps/web/package-lock.json" in snapshot.dependency_manifests
    assert "SEMGREP_ENABLED is false" in markdown
    assert "DEPENDENCY_AUDIT_ENABLED is false" in markdown
    assert "CODEQL_ENABLED is false" in markdown
    assert "code-scanning/Advanced Security access" in markdown


def test_scanner_snapshot_blocks_enabled_semgrep_when_tool_is_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("scripts.security_scanner_snapshot.shutil.which", lambda name: None)

    snapshot = collect_snapshot(root=tmp_path, env={"SEMGREP_ENABLED": "true"})

    assert snapshot.release_scanner_proof_ready is False
    assert any("semgrep is not installed" in item for item in snapshot.blockers)
    assert any(scanner.name == "semgrep" and scanner.status == "blocked" for scanner in snapshot.scanners)


def test_scanner_snapshot_checks_dependency_audit_tools_for_manifest_types(tmp_path: Path, monkeypatch) -> None:
    tmp_path.joinpath("apps/api").mkdir(parents=True)
    tmp_path.joinpath("apps/api/requirements.txt").write_text("fastapi\n", encoding="utf-8")
    tmp_path.joinpath("apps/web").mkdir(parents=True)
    tmp_path.joinpath("apps/web/package-lock.json").write_text("{}", encoding="utf-8")

    def fake_which(name: str) -> str | None:
        return "/usr/bin/npm" if name == "npm" else None

    monkeypatch.setattr("scripts.security_scanner_snapshot.shutil.which", fake_which)

    snapshot = collect_snapshot(root=tmp_path, env={"DEPENDENCY_AUDIT_ENABLED": "true"})

    assert any("pip-audit" in item for item in snapshot.blockers)
    assert any(scanner.name == "dependency_audit" and scanner.status == "blocked" for scanner in snapshot.scanners)


def test_scanner_snapshot_writes_markdown_and_json(tmp_path: Path, monkeypatch) -> None:
    tmp_path.joinpath(".github/workflows").mkdir(parents=True)
    tmp_path.joinpath(".github/workflows/codeql.yml").write_text("name: CodeQL\n", encoding="utf-8")
    tmp_path.joinpath("apps/web").mkdir(parents=True)
    tmp_path.joinpath("apps/web/package-lock.json").write_text("{}", encoding="utf-8")
    tmp_path.joinpath("apps/api").mkdir(parents=True)
    tmp_path.joinpath("apps/api/requirements.txt").write_text("fastapi\n", encoding="utf-8")

    def fake_which(name: str) -> str:
        return f"/usr/bin/{name}"

    def fake_runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=command, returncode=0, stdout=f"{command[0]} 1.0\n", stderr="")

    monkeypatch.setattr("scripts.security_scanner_snapshot.shutil.which", fake_which)
    snapshot = collect_snapshot(
        root=tmp_path,
        env={"SEMGREP_ENABLED": "true", "DEPENDENCY_AUDIT_ENABLED": "true", "CODEQL_ENABLED": "true"},
        runner=fake_runner,
    )
    json_out = tmp_path / "security-scanner-snapshot.json"
    md_out = tmp_path / "security-scanner-snapshot.md"

    write_outputs(snapshot=snapshot, json_out=json_out, md_out=md_out)

    assert snapshot.release_scanner_proof_ready is True
    assert "Release scanner proof ready: `True`" in md_out.read_text(encoding="utf-8")
    assert '"codeql_workflow_present": true' in json_out.read_text(encoding="utf-8")
