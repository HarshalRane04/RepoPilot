from app.services.security_envelope import stable_hash


def test_hash_is_stable() -> None:
    assert stable_hash({"b": 2, "a": 1}) == stable_hash({"a": 1, "b": 2})

