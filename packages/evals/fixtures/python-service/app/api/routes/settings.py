def readiness_mode(*, github_verified: bool, model_verified: bool) -> dict[str, str]:
    return {
        "github_mode": "read_only_verified" if github_verified else "credentials_unverified",
        "model_mode": "live_model_verified" if model_verified else "mock_model",
    }

