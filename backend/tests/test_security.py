import time

import pytest

from app.core.security import (
    InvalidTokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip():
    hashed = hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert verify_password("correct horse battery staple", hashed)
    assert not verify_password("wrong password", hashed)


def test_access_token_roundtrip():
    token = create_access_token("user-123")
    payload = decode_token(token, expected_type="access")
    assert payload["sub"] == "user-123"
    assert payload["type"] == "access"


def test_refresh_token_rejected_as_access_token():
    token = create_refresh_token("user-123")
    with pytest.raises(InvalidTokenError):
        decode_token(token, expected_type="access")


def test_garbage_token_raises():
    with pytest.raises(InvalidTokenError):
        decode_token("not-a-real-jwt", expected_type="access")
