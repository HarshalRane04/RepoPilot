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


def test_ci_workflow_checks_provider_retrieval_package_boundary() -> None:
    workflow = ROOT.joinpath(".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "ProviderRetrievalEvalRunner" in workflow


def test_provider_patch_eval_workflow_uploads_report_artifacts() -> None:
    workflow = ROOT.joinpath(".github/workflows/provider-patch-eval.yml").read_text(encoding="utf-8")

    assert "Provider Patch Eval" in workflow
    assert "api_key_secret_name" in workflow
    assert "make provider-patch-eval" in workflow
    assert "REPOPILOT_PROVIDER_API_KEY" in workflow
    assert "provider-patch-eval-${{ github.run_id }}" in workflow
    assert "v1-provider-patch.observed-evidence.json" in workflow


def test_provider_retrieval_eval_workflow_uploads_report_artifacts() -> None:
    workflow = ROOT.joinpath(".github/workflows/provider-retrieval-eval.yml").read_text(encoding="utf-8")

    assert "Provider Retrieval Eval" in workflow
    assert "api_key_secret" in workflow
    assert "make provider-retrieval-eval" in workflow
    assert "REPOPILOT_PROVIDER_API_KEY" in workflow
    assert "provider-retrieval-eval-${{ github.run_id }}" in workflow
    assert "v1-provider-retrieval.observed-evidence.json" in workflow


def test_provider_applied_patch_eval_workflow_uploads_report_artifacts() -> None:
    workflow = ROOT.joinpath(".github/workflows/provider-applied-patch-eval.yml").read_text(encoding="utf-8")

    assert "Provider Applied Patch Eval" in workflow
    assert "api_key_secret_name" in workflow
    assert "make provider-applied-patch-eval" in workflow
    assert "REPOPILOT_PROVIDER_API_KEY" in workflow
    assert "provider-applied-patch-eval-${{ github.run_id }}" in workflow
    assert "v1-provider-applied-patch.observed-evidence.json" in workflow


def test_release_workflow_uploads_local_evidence_bundle_before_images() -> None:
    workflow = ROOT.joinpath(".github/workflows/release.yml").read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "release-evidence:" in workflow
    assert "python -m repopilot_evals.report" in workflow
    assert "scripts/source_boundary_manifest.py" in workflow
    assert "scripts/deployment_validate.py" in workflow
    assert "release-evidence-${{ github.run_id }}" in workflow
    assert "needs: release-evidence" in workflow
