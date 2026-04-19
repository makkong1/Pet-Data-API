import hashlib
import pytest
from fastapi import HTTPException
from app.core.auth import hash_key, verify_key, require_api_key, require_admin_key


def test_hash_key_is_sha256():
    key = "testkey"
    expected = hashlib.sha256(key.encode()).hexdigest()
    assert hash_key(key) == expected


def test_verify_key_correct():
    key = "mykey"
    hashed = hash_key(key)
    assert verify_key(key, hashed) is True


def test_verify_key_wrong():
    assert verify_key("wrong", hash_key("correct")) is False
