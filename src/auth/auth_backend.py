"""Authentication backend configuration for fastapi-users."""
from __future__ import annotations

from typing import Optional

from fastapi_users.authentication import AuthenticationBackend, BearerTransport, JWTStrategy
from fastapi_users.manager import BaseUserManager

from ..config import Settings
from . import token_registry


class SingleSessionJWTStrategy(JWTStrategy):
    """JWT strategy that ensures only one active token per user."""

    async def write_token(self, user) -> str:  # type: ignore[override]
        token = await super().write_token(user)
        await token_registry.register(str(user.id), token)
        return token

    async def read_token(self, token: str, user_manager: BaseUserManager) -> Optional[object]:  # type: ignore[override]
        user = await super().read_token(token, user_manager)
        if user is None:
            return None
        if not await token_registry.validate(str(user.id), token):
            return None
        return user


def get_jwt_strategy(settings: Settings) -> JWTStrategy:
    """Return a JWT strategy configured from the application settings."""

    lifetime_seconds = settings.fastapi.access_token_expire_minutes * 60
    return SingleSessionJWTStrategy(secret=settings.fastapi.secret_key, lifetime_seconds=lifetime_seconds)


def get_auth_backend(settings: Settings) -> AuthenticationBackend:
    """Create the FastAPI Users authentication backend."""

    bearer_transport = BearerTransport(tokenUrl="/auth/jwt/login")
    return AuthenticationBackend(name="jwt", transport=bearer_transport, get_strategy=lambda: get_jwt_strategy(settings))


__all__ = ["get_auth_backend", "get_jwt_strategy"]
