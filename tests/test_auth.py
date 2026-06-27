"""
tests/test_auth.py
Unit tests for password hashing, JWT issuance/verification, and RBAC
permission checks. User registration/authentication against the database
is exercised in an isolated temp DuckDB file.
"""

import os
import tempfile

import pytest


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    """Run each test against a fresh temp DuckDB file and a fixed JWT secret."""
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test.db")
    monkeypatch.setenv("STOCHASTIX_DB", db_path)
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("DB_BACKEND", "duckdb")

    # Reset DuckDB module-level connection singleton between tests
    import pipeline.database as dbmod
    dbmod._conn = None

    yield


class TestPasswordHashing:
    def test_hash_and_verify_roundtrip(self):
        from auth.security import hash_password, verify_password
        h = hash_password("correct-password")
        assert verify_password("correct-password", h) is True
        assert verify_password("wrong-password", h) is False

    def test_hashes_are_salted(self):
        from auth.security import hash_password
        h1 = hash_password("same-password")
        h2 = hash_password("same-password")
        assert h1 != h2


class TestJWT:
    def test_create_and_decode_token(self):
        from auth.security import create_access_token, decode_access_token
        token = create_access_token("alice", "analyst", expires_minutes=5)
        payload = decode_access_token(token)
        assert payload["sub"] == "alice"
        assert payload["role"] == "analyst"

    def test_invalid_token_returns_none(self):
        from auth.security import decode_access_token
        assert decode_access_token("not-a-real-token") is None

    def test_expired_token_returns_none(self):
        from auth.security import create_access_token, decode_access_token
        token = create_access_token("bob", "viewer", expires_minutes=-1)
        assert decode_access_token(token) is None


class TestRBAC:
    def test_role_hierarchy(self):
        from auth.security import has_permission
        assert has_permission("admin", "viewer") is True
        assert has_permission("admin", "analyst") is True
        assert has_permission("admin", "admin") is True
        assert has_permission("viewer", "analyst") is False
        assert has_permission("analyst", "admin") is False
        assert has_permission("analyst", "viewer") is True


class TestUserRegistrationAndAuth:
    def test_register_and_authenticate(self):
        from pipeline.database import init_db
        from auth.security import register_user, authenticate_user

        init_db()

        ok, msg = register_user("carol", "carol@example.com", "s3cret!", role="analyst")
        assert ok, msg

        user = authenticate_user("carol", "s3cret!")
        assert user is not None
        assert user["username"] == "carol"
        assert user["role"] == "analyst"

        assert authenticate_user("carol", "wrong-password") is None
        assert authenticate_user("nonexistent", "anything") is None

    def test_duplicate_registration_fails(self):
        from pipeline.database import init_db
        from auth.security import register_user

        init_db()
        ok1, _ = register_user("dave", "dave@example.com", "pw12345", role="viewer")
        ok2, msg2 = register_user("dave", "dave2@example.com", "pw12345", role="viewer")
        assert ok1 is True
        assert ok2 is False
        assert "already registered" in msg2

    def test_invalid_role_rejected(self):
        from pipeline.database import init_db
        from auth.security import register_user

        init_db()
        ok, msg = register_user("erin", "erin@example.com", "pw12345", role="superuser")
        assert ok is False
        assert "Invalid role" in msg
