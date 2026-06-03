from app.api.routes.repositories import list_repositories


def test_empty_repository_list() -> None:
    assert list_repositories() == []

