from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_ci_workflow_uploads_scanner_posture_evidence() -> None:
    workflow = ROOT.joinpath(".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "scanner-posture:" in workflow
    assert 'SEMGREP_ENABLED: "true"' in workflow
    assert 'DEPENDENCY_AUDIT_ENABLED: "true"' in workflow
    assert 'CODEQL_ENABLED: "false"' in workflow
    assert "scripts/security_scanner_snapshot.py" in workflow
    assert "--allow-warnings" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "security-scanner-posture-${{ github.run_id }}" in workflow
