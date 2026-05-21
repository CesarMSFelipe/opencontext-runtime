"""Authentication module for the demo project.

Provides user authentication with password hashing and session management.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any


@dataclass
class User:
    """A user in the system."""

    id: int
    username: str
    email: str
    password_hash: str
    is_active: bool = True
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.created_at is None:
            self.created_at = datetime.now()


class AuthenticationError(Exception):
    """Raised when authentication fails."""

    pass


class UserRepository:
    """Repository for user data access."""

    def __init__(self) -> None:
        self._users: dict[int, User] = {}
        self._username_index: dict[str, int] = {}
        self._next_id = 1

    def find_by_username(self, username: str) -> User | None:
        """Find a user by username."""
        user_id = self._username_index.get(username)
        if user_id is None:
            return None
        return self._users.get(user_id)

    def find_by_id(self, user_id: int) -> User | None:
        """Find a user by ID."""
        return self._users.get(user_id)

    def save(self, user: User) -> User:
        """Save a user to the repository."""
        if user.id == 0:
            user.id = self._next_id
            self._next_id += 1
        self._users[user.id] = user
        self._username_index[user.username] = user.id
        return user


class PasswordHasher:
    """Simple password hasher for demo purposes."""

    @staticmethod
    def hash(password: str) -> str:
        """Hash a password."""
        # In production, use bcrypt or argon2
        import hashlib

        return hashlib.sha256(password.encode()).hexdigest()

    @staticmethod
    def verify(password: str, hash_value: str) -> bool:
        """Verify a password against a hash."""
        return PasswordHasher.hash(password) == hash_value


class SessionManager:
    """Manages user sessions."""

    def __init__(self, token_ttl: int = 3600) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}
        self._token_ttl = token_ttl

    def create_session(self, user_id: int) -> str:
        """Create a new session for a user."""
        import secrets

        token = secrets.token_urlsafe(32)
        self._sessions[token] = {
            "user_id": user_id,
            "created_at": datetime.now(),
            "expires_at": datetime.now() + timedelta(seconds=self._token_ttl),
        }
        return token

    def validate_token(self, token: str) -> int | None:
        """Validate a session token and return user_id."""
        session = self._sessions.get(token)
        if session is None:
            return None
        if datetime.now() > session["expires_at"]:
            del self._sessions[token]
            return None
        return session["user_id"]

    def revoke_token(self, token: str) -> bool:
        """Revoke a session token."""
        if token in self._sessions:
            del self._sessions[token]
            return True
        return False


class AuthService:
    """Main authentication service."""

    def __init__(self) -> None:
        self._user_repo = UserRepository()
        self._session_manager = SessionManager()
        self._hasher = PasswordHasher()

    def register(self, username: str, email: str, password: str) -> User:
        """Register a new user."""
        if self._user_repo.find_by_username(username):
            raise AuthenticationError(f"Username '{username}' already exists")

        user = User(
            id=0,
            username=username,
            email=email,
            password_hash=self._hasher.hash(password),
        )
        return self._user_repo.save(user)

    def authenticate(self, username: str, password: str) -> str:
        """Authenticate a user and return a session token."""
        user = self._user_repo.find_by_username(username)
        if user is None:
            raise AuthenticationError("Invalid username or password")

        if not user.is_active:
            raise AuthenticationError("User account is disabled")

        if not self._hasher.verify(password, user.password_hash):
            raise AuthenticationError("Invalid username or password")

        return self._session_manager.create_session(user.id)

    def validate_token(self, token: str) -> User | None:
        """Validate a token and return the user."""
        user_id = self._session_manager.validate_token(token)
        if user_id is None:
            return None
        return self._user_repo.find_by_id(user_id)

    def logout(self, token: str) -> bool:
        """Log out a user by revoking their token."""
        return self._session_manager.revoke_token(token)
