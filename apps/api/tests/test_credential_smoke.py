from __future__ import annotations

from pathlib import Path

from scripts import credential_smoke, github_app_smoke, github_oauth_smoke, model_provider_smoke


def _oauth(status: str = "blocked", ok: bool = False, detail: str = "Missing GITHUB_CLIENT_ID.") -> github_oauth_smoke.GitHubOAuthSmoke:
    return github_oauth_smoke.GitHubOAuthSmoke(
        generated_at="2026-06-06T00:00:00+00:00",
        ok=ok,
        status=status,
        client_id_configured=ok,
        client_secret_configured=ok,
        callback_url_configured=True,
        web_app_url_configured=True,
        session_secret_configured=True,
        github_base_urls_configured=True,
        authorization_url_generated=ok,
        store_exists=ok,
        store_permissions_ok=True,
        key_permissions_ok=True,
        detail=detail,
    )


def _app(status: str = "blocked", ok: bool = False, detail: str = "Missing GITHUB_APP_ID.") -> github_app_smoke.GitHubAppSmoke:
    return github_app_smoke.GitHubAppSmoke(
        generated_at="2026-06-06T00:00:00+00:00",
        ok=ok,
        status=status,
        app_id_configured=ok,
        private_key_configured=ok,
        installation_id_configured=ok,
        webhook_secret_configured=True,
        store_exists=ok,
        store_permissions_ok=True,
        key_permissions_ok=True,
        verified_at="2026-06-06T00:00:01+00:00" if ok else None,
        installation_id="123" if ok else None,
        token_received=ok,
        detail=detail,
    )


def _model(status: str = "blocked", ok: bool = False, detail: str = "Missing MODEL_API_KEY.") -> model_provider_smoke.ModelProviderSmoke:
    return model_provider_smoke.ModelProviderSmoke(
        generated_at="2026-06-06T00:00:00+00:00",
        ok=ok,
        status=status,
        provider="openrouter",
        model="gemma-4-31b-it:free",
        api_key_configured=ok,
        model_available=ok,
        store_exists=ok,
        store_permissions_ok=True,
        key_permissions_ok=True,
        verified_at="2026-06-06T00:00:01+00:00" if ok else None,
        latency_ms=42 if ok else None,
        detail=detail,
    )


def test_credential_smoke_summary_blocks_when_any_gate_is_blocked() -> None:
    summary = credential_smoke.summarize_credentials(
        generated_at="2026-06-06T00:00:00+00:00",
        github_oauth=_oauth(ok=True, status="passed", detail="OAuth URL generated."),
        github_app=_app(),
        model_provider=_model(ok=True, status="passed", detail="Provider verified."),
    )

    assert summary.ok is False
    assert summary.status == "blocked"
    assert summary.github_app_status == "blocked"
    assert "configure-runtime-secrets" in summary.next_step


def test_credential_smoke_summary_fails_when_any_gate_fails() -> None:
    summary = credential_smoke.summarize_credentials(
        generated_at="2026-06-06T00:00:00+00:00",
        github_oauth=_oauth(ok=True, status="passed", detail="OAuth URL generated."),
        github_app=_app(ok=False, status="failed", detail="GitHub rejected installation token."),
        model_provider=_model(ok=True, status="passed", detail="Provider verified."),
    )

    assert summary.ok is False
    assert summary.status == "failed"
    assert "failed credential smoke" in summary.next_step


def test_credential_smoke_summary_passes_when_all_gates_pass() -> None:
    summary = credential_smoke.summarize_credentials(
        generated_at="2026-06-06T00:00:00+00:00",
        github_oauth=_oauth(ok=True, status="passed", detail="OAuth URL generated."),
        github_app=_app(ok=True, status="passed", detail="Installation token created."),
        model_provider=_model(ok=True, status="passed", detail="Provider verified."),
    )

    assert summary.ok is True
    assert summary.status == "passed"
    assert "draft-PR smoke" in summary.next_step


def test_credential_smoke_writes_redacted_aggregate_artifacts(tmp_path: Path) -> None:
    summary = credential_smoke.summarize_credentials(
        generated_at="2026-06-06T00:00:00+00:00",
        github_oauth=_oauth(),
        github_app=_app(),
        model_provider=_model(),
    )
    json_out = tmp_path / "credential-smoke-summary.json"
    md_out = tmp_path / "credential-smoke-summary.md"

    credential_smoke.write_outputs(summary=summary, json_out=json_out, md_out=md_out)

    rendered = md_out.read_text(encoding="utf-8")
    artifact = json_out.read_text(encoding="utf-8")
    assert "RepoPilot Credential Smoke Summary" in rendered
    assert "Missing GITHUB_APP_ID" in rendered
    assert "sk-or-" not in artifact
    assert "client-secret" not in artifact
