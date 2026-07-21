from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_ci_workflow_runs_feature_branch_matrix_once_and_cancels_stale_runs() -> None:
    workflow = ROOT.joinpath(".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "on:\n  push:\n    branches:\n      - main\n  pull_request:" in workflow
    assert "concurrency:" in workflow
    assert "github.event.pull_request.number || github.ref" in workflow
    assert "cancel-in-progress: true" in workflow
    assert workflow.count("timeout-minutes:") == 6


def test_dependabot_docker_updates_cover_every_runtime_dockerfile_directory() -> None:
    config = ROOT.joinpath(".github/dependabot.yml").read_text(encoding="utf-8")
    update_blocks = config.split("\n  - package-ecosystem: ")
    docker_block = next(block for block in update_blocks if block.startswith('"docker"'))
    directories_match = re.search(
        r'(?m)^    directories:\n(?P<items>(?:      - "[^"]+"\n?)+)',
        docker_block,
    )

    assert directories_match is not None
    configured_directories = re.findall(
        r'^      - "([^"]+)"$',
        directories_match.group("items"),
        flags=re.MULTILINE,
    )
    generated_path_parts = {".git", ".next", "node_modules", "output"}
    dockerfile_directories = {
        f"/{path.parent.relative_to(ROOT).as_posix()}"
        for path in ROOT.rglob("Dockerfile")
        if not generated_path_parts.intersection(path.relative_to(ROOT).parts)
    }

    assert len(configured_directories) == len(set(configured_directories))
    assert set(configured_directories) == dockerfile_directories


def test_ci_workflow_uploads_scanner_posture_evidence() -> None:
    workflow = ROOT.joinpath(".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "scanner-posture:" in workflow
    assert 'SEMGREP_ENABLED: "true"' in workflow
    assert 'DEPENDENCY_AUDIT_ENABLED: "true"' in workflow
    assert 'CODEQL_ENABLED: "false"' in workflow
    assert "scripts/security_scanner_snapshot.py" in workflow
    assert "--allow-warnings" in workflow
    assert "actions/upload-artifact@v6" in workflow
    assert "security-scanner-posture-${{ github.run_id }}" in workflow


def test_ci_workflow_guards_ui_truth_and_privacy_copy() -> None:
    workflow = ROOT.joinpath(".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "Guard UI truth and privacy copy" in workflow
    assert "scripts/ui_truth_guard.py" in workflow


def test_ci_workflow_uses_node24_backed_github_actions() -> None:
    workflow_paths = [
        ".github/workflows/ci.yml",
        ".github/workflows/codeql.yml",
        ".github/workflows/provider-applied-patch-eval.yml",
        ".github/workflows/provider-patch-eval.yml",
        ".github/workflows/provider-planning-eval.yml",
        ".github/workflows/provider-retrieval-eval.yml",
        ".github/workflows/release.yml",
    ]
    combined = "\n".join(ROOT.joinpath(path).read_text(encoding="utf-8") for path in workflow_paths)

    assert "actions/checkout@v4" not in combined
    assert "actions/setup-node@v4" not in combined
    assert "actions/setup-python@v5" not in combined
    assert "actions/upload-artifact@v4" not in combined
    assert "actions/checkout@v5" in combined
    assert "actions/setup-node@v6" in combined
    assert "actions/setup-python@v6" in combined
    assert "actions/upload-artifact@v6" in combined


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
    assert "publish_images:" in workflow
    assert "release-evidence:" in workflow
    assert "python -m repopilot_evals.report" in workflow
    assert 'strict_release=false' in workflow
    assert '[[ "${GITHUB_REF}" == refs/tags/* ]]' in workflow
    assert '"${{ inputs.publish_images }}" == "true"' in workflow
    assert "scripts/source_boundary_manifest.py" in workflow
    assert "Build credential smoke summary" in workflow
    assert "scripts/credential_smoke.py" in workflow
    assert "args+=(--allow-blocked)" in workflow
    assert "args+=(--allow-failed-gates)" in workflow
    assert "Build security scanner snapshot" in workflow
    assert "scripts/security_scanner_snapshot.py" in workflow
    assert "scripts/deployment_validate.py" in workflow
    assert "release-evidence-${{ github.run_id }}" in workflow
    assert "needs: release-evidence" in workflow
    assert "docker/login-action@v3" in workflow
    assert "docker/metadata-action@v5" in workflow
    assert "docker/build-push-action@v6" in workflow
    assert "ghcr.io/${owner_lc}/repopilot-api" in workflow
    assert "ghcr.io/${owner_lc}/repopilot-web" in workflow
    assert "ghcr.io/${owner_lc}/repopilot-sandbox" in workflow
    assert "push: ${{ startsWith(github.ref, 'refs/tags/') || (github.event_name == 'workflow_dispatch' && inputs.publish_images == true) }}" in workflow
    assert "release-images-${{ github.run_id }}" in workflow
    assert "steps.api-build.outputs.digest" in workflow
