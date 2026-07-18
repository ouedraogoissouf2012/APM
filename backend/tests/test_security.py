import pytest

from app.core import security


def test_password_hash_roundtrip():
    hashed = security.hash_password("s3cret!pass")
    assert hashed != "s3cret!pass"
    assert security.verify_password("s3cret!pass", hashed) is True
    assert security.verify_password("wrong", hashed) is False


def test_jwt_roundtrip():
    token = security.create_access_token(subject="42")
    assert security.decode_access_token(token) == "42"


def test_jwt_rejects_tampered_token():
    token = security.create_access_token(subject="42")
    with pytest.raises(security.InvalidTokenError):
        security.decode_access_token(token + "x")
