"""Authentication dependencies."""
from __future__ import annotations

from typing import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from ..dependencies import get_db_session, get_settings
from ..infrastructure.repositories.user_repo import UserRepository
from .constants import ACCESS_TOKEN_TYPE, OAUTH2_TOKEN_URL
from .service import AuthService


oauth2_scheme = OAuth2PasswordBearer(tokenUrl=OAUTH2_TOKEN_URL)


async def get_auth_service(session: AsyncSession = Depends(get_db_session)) -> AuthService:
    settings = get_settings()
    repo = UserRepository(session)
    return AuthService(repo, settings)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    auth_service: AuthService = Depends(get_auth_service),
) -> tuple[str, list[str]]:
    user_id = auth_service.validate_token(token, expected_type=ACCESS_TOKEN_TYPE)
    user = await auth_service.user_repo.get(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user.id, [role.name for role in user.roles]


def require_roles(*allowed_roles: str) -> Callable[[tuple[str, list[str]]], tuple[str, list[str]]]:
    async def dependency(user_info: tuple[str, list[str]] = Depends(get_current_user)) -> tuple[str, list[str]]:
        if allowed_roles and not set(user_info[1]).intersection(allowed_roles):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user_info

    return dependency


__all__ = ["get_auth_service", "get_current_user", "require_roles", "oauth2_scheme"]
