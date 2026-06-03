from app.api.routes.settings import readiness_mode


def test_readiness_modes_are_explicit() -> None:
    result = readiness_mode(github_verified=False, model_verified=False)
    assert result["github_mode"] == "credentials_unverified"
    assert result["model_mode"] == "mock_model"

