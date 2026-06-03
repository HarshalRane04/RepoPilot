from app.services.github_permissions import map_github_role


def test_write_maps_to_developer() -> None:
    assert map_github_role("write") == "developer"

