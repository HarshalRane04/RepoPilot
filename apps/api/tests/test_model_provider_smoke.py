from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from scripts import model_provider_smoke


class FakeStore:
    def __init__(self) -> None:
        self.saved: dict[str, str] = {}

    def summary(self, fields: set[str]) -> dict[str, object]:
        return {
            "fields": [{"name": field, "configured": False, "secret": field.endswith("KEY"), "source": "encrypted_store"} for field in fields],
            "store_exists": False,
            "store_permissions_ok": True,
            "key_permissions_ok": True,
        }

    def save_values(self, values: dict[str, str]) -> None:
        self.saved.update(values)


def test_model_provider_smoke_blocks_when_api_key_missing(monkeypatch) -> None:
    store = FakeStore()
    monkeypatch.setattr(model_provider_smoke, "runtime_secret_store", lambda: store)
    monkeypatch.setattr(
        model_provider_smoke,
        "effective_settings",
        lambda settings: SimpleNamespace(
            model_provider="openrouter",
            model_name="gemma-4-31b-it:free",
            model_api_key="",
            model_base_url="https://openrouter.ai/api/v1",
            model_request_timeout_seconds=5,
        ),
    )
    monkeypatch.setattr(model_provider_smoke, "provider_by_id", lambda provider_id: SimpleNamespace(id=provider_id, default_base_url="https://openrouter.ai/api/v1"))

    smoke = model_provider_smoke.asyncio.run(model_provider_smoke.capture_model_provider_smoke())

    assert smoke.ok is False
    assert smoke.status == "blocked"
    assert smoke.api_key_configured is False
    assert "MODEL_API_KEY" in smoke.detail


def test_model_provider_smoke_blocks_when_mock_provider_configured(monkeypatch) -> None:
    store = FakeStore()
    monkeypatch.setattr(model_provider_smoke, "runtime_secret_store", lambda: store)
    monkeypatch.setattr(
        model_provider_smoke,
        "effective_settings",
        lambda settings: SimpleNamespace(
            model_provider="mock",
            model_name="mock-planner",
            model_api_key="",
            model_base_url=None,
            model_request_timeout_seconds=5,
        ),
    )

    smoke = model_provider_smoke.asyncio.run(model_provider_smoke.capture_model_provider_smoke())

    assert smoke.ok is False
    assert smoke.status == "blocked"
    assert "live model provider" in smoke.detail


def test_model_provider_smoke_persists_verified_marker(monkeypatch) -> None:
    store = FakeStore()
    provider = SimpleNamespace(id="openrouter", default_base_url="https://openrouter.ai/api/v1")
    monkeypatch.setattr(model_provider_smoke, "runtime_secret_store", lambda: store)
    monkeypatch.setattr(
        model_provider_smoke,
        "effective_settings",
        lambda settings: SimpleNamespace(
            model_provider="openrouter",
            model_name="gemma-4-31b-it:free",
            model_api_key="configured-key",
            model_base_url="https://openrouter.ai/api/v1",
            model_request_timeout_seconds=5,
        ),
    )
    monkeypatch.setattr(model_provider_smoke, "provider_by_id", lambda provider_id: provider)

    async def fake_dynamic_model_ids_for_provider(**kwargs) -> set[str]:
        return {"gemma-4-31b-it:free"}

    async def fake_verify_model_provider(**kwargs) -> SimpleNamespace:
        return SimpleNamespace(
            ok=True,
            checked_at="2026-06-04T00:00:00+00:00",
            latency_ms=42,
            detail="Provider responded and selected model was present in the model list.",
        )

    monkeypatch.setattr(model_provider_smoke, "dynamic_model_ids_for_provider", fake_dynamic_model_ids_for_provider)
    monkeypatch.setattr(model_provider_smoke, "verify_model_provider", fake_verify_model_provider)

    smoke = model_provider_smoke.asyncio.run(model_provider_smoke.capture_model_provider_smoke())

    assert smoke.ok is True
    assert smoke.status == "passed"
    assert smoke.verified_at == "2026-06-04T00:00:00+00:00"
    assert store.saved["MODEL_PROVIDER_VERIFIED_MODEL"] == "openrouter:gemma-4-31b-it:free"


def test_model_provider_smoke_writes_redacted_artifacts(tmp_path: Path) -> None:
    smoke = model_provider_smoke.ModelProviderSmoke(
        generated_at="2026-06-04T00:00:00+00:00",
        ok=False,
        status="blocked",
        provider="openrouter",
        model="gemma-4-31b-it:free",
        api_key_configured=False,
        model_available=False,
        store_exists=False,
        store_permissions_ok=True,
        key_permissions_ok=True,
        verified_at=None,
        latency_ms=None,
        detail="MODEL_API_KEY is not configured in the effective runtime settings.",
    )
    json_out = tmp_path / "model-provider-smoke.json"
    md_out = tmp_path / "model-provider-smoke.md"

    model_provider_smoke.write_outputs(smoke=smoke, json_out=json_out, md_out=md_out)

    assert "gemma-4-31b-it:free" in md_out.read_text(encoding="utf-8")
    artifact = json_out.read_text(encoding="utf-8")
    assert "MODEL_API_KEY" in artifact
    assert "configured-key" not in artifact
