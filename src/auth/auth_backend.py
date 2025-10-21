"""Authentication backend configuration for fastapi-users."""
from __future__ import annotations

from fastapi_users.authentication import AuthenticationBackend, BearerTransport, JWTStrategy

from ..config import Settings


def get_jwt_strategy(settings: Settings) -> JWTStrategy:
    """Return a JWT strategy configured from the application settings."""

    lifetime_seconds = settings.fastapi.access_token_expire_minutes * 60
    return JWTStrategy(secret=settings.fastapi.secret_key, lifetime_seconds=lifetime_seconds)


def get_auth_backend(settings: Settings) -> AuthenticationBackend:
    """Create the FastAPI Users authentication backend."""

    bearer_transport = BearerTransport(tokenUrl="/auth/jwt/login")
    return AuthenticationBackend(name="jwt", transport=bearer_transport, get_strategy=lambda: get_jwt_strategy(settings))


__all__ = ["get_auth_backend", "get_jwt_strategy"]
