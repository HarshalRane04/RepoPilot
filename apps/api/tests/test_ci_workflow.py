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


def test_provider_patch_eval_workflow_uploads_report_artifacts() -> None:
    workflow = ROOT.joinpath(".github/workflows/provider-patch-eval.yml").read_text(encoding="utf-8")

    assert "Provider Patch Eval" in workflow
    assert "api_key_secret_name" in workflow
    assert "make provider-patch-eval" in workflow
    assert "REPOPILOT_PROVIDER_API_KEY" in workflow
    assert "provider-patch-eval-${{ github.run_id }}" in workflow
    assert "v1-provider-patch.observed-evidence.json" in workflow
