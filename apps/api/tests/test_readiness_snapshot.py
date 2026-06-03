from __future__ import annotations

from pathlib import Path

from scripts.readiness_snapshot import ReadinessSnapshot, redact, render_markdown, write_outputs


def test_readiness_snapshot_redacts_sensitive_values() -> None:
    payload = {
        "model_api_key": "secret-value",
        "github_client_secret": "client-secret",
        "nested": {"installation_token": "token-value", "configured": True},
        "safe": "visible",
    }

    redacted = redact(payload)

    assert redacted["model_api_key"] == "[redacted]"
    assert redacted["github_client_secret"] == "[redacted]"
    assert redacted["nested"]["installation_token"] == "[redacted]"
    assert redacted["nested"]["configured"] is True
    assert redacted["safe"] == "visible"


def test_readiness_snapshot_renders_and_writes_reports(tmp_path: Path) -> None:
    snapshot = ReadinessSnapshot(
        generated_at="2026-06-03T00:00:00+00:00",
        readiness={
            "environment": "local",
            "production_ready": False,
            "github_mode": "missing_credentials",
            "model_mode": "live_model_verified",
            "github_writes_enabled": False,
            "integrations": [
                {
                    "name": "GitHub App installation credentials",
                    "state": "missing",
                    "mode": "missing_credentials",
                    "required_for_production": True,
                    "detail": "Required for installation tokens.",
                    "next_step": "Set GitHub App credentials.",
                }
            ],
            "blockers": ["GitHub App installation credentials: Set GitHub App credentials."],
            "warnings": [],
        },
        github_app={"fields": [{"name": "GITHUB_APP_PRIVATE_KEY", "configured": False, "secret": True, "source": "environment"}]},
    )
    json_out = tmp_path / "credential-readiness-snapshot.json"
    md_out = tmp_path / "credential-readiness-snapshot.md"

    write_outputs(snapshot=snapshot, json_out=json_out, md_out=md_out)

    assert "missing_credentials" in render_markdown(snapshot)
    assert "live_model_verified" in md_out.read_text(encoding="utf-8")
    assert "GITHUB_APP_PRIVATE_KEY" in json_out.read_text(encoding="utf-8")
