"""Tests for authentication module."""

from __future__ import annotations

import pytest
from auth import AuthenticationError, AuthService


class TestAuthService:
    """Test authentication service."""

    @pytest.fixture
    def auth(self) -> AuthService:
        return AuthService()

    def test_register(self, auth: AuthService) -> None:
        user = auth.register("alice", "alice@example.com", "password123")
        assert user.username == "alice"
        assert user.email == "alice@example.com"
        assert user.is_active is True

    def test_register_duplicate_username(self, auth: AuthService) -> None:
        auth.register("alice", "alice@example.com", "password123")
        with pytest.raises(AuthenticationError, match="already exists"):
            auth.register("alice", "other@example.com", "password456")

    def test_authenticate(self, auth: AuthService) -> None:
        auth.register("alice", "alice@example.com", "password123")
        token = auth.authenticate("alice", "password123")
        assert token is not None
        assert len(token) > 20

    def test_authenticate_wrong_password(self, auth: AuthService) -> None:
        auth.register("alice", "alice@example.com", "password123")
        with pytest.raises(AuthenticationError, match="Invalid"):
            auth.authenticate("alice", "wrongpassword")

    def test_authenticate_unknown_user(self, auth: AuthService) -> None:
        with pytest.raises(AuthenticationError, match="Invalid"):
            auth.authenticate("unknown", "password123")

    def test_validate_token(self, auth: AuthService) -> None:
        auth.register("alice", "alice@example.com", "password123")
        token = auth.authenticate("alice", "password123")
        user = auth.validate_token(token)
        assert user is not None
        assert user.username == "alice"

    def test_validate_invalid_token(self, auth: AuthService) -> None:
        user = auth.validate_token("invalid-token")
        assert user is None

    def test_logout(self, auth: AuthService) -> None:
        auth.register("alice", "alice@example.com", "password123")
        token = auth.authenticate("alice", "password123")
        assert auth.logout(token) is True
        assert auth.validate_token(token) is None

    def test_logout_invalid_token(self, auth: AuthService) -> None:
        assert auth.logout("invalid") is False
