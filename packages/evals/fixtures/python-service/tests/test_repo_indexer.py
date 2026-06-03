from app.services.repo_indexer import should_index


def test_env_file_is_skipped() -> None:
    assert should_index(".env") is False

