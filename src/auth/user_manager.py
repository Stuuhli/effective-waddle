"""User manager integration for fastapi-users."""
from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Optional

from fastapi import Depends, Request
from fastapi_users import BaseUserManager
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase

from ..config import Settings
from ..dependencies import get_db_session, get_settings
from ..infrastructure.database import User
from ..infrastructure.repositories.user_repo import UserRepository
from .constants import DEFAULT_ROLE_DESCRIPTION, DEFAULT_ROLE_NAME


class UserManager(BaseUserManager[User, str]):
    """Application specific user manager."""

    user_db_model = User

    def __init__(self, user_db: SQLAlchemyUserDatabase[User, str], settings: Settings) -> None:
        super().__init__(user_db)
        self._settings = settings

    @property
    def reset_password_token_secret(self) -> str:
        return self._settings.fastapi.secret_key

    @property
    def verification_token_secret(self) -> str:
        return self._settings.fastapi.secret_key

    async def on_after_register(self, user: User, request: Optional[Request] = None) -> None:  # noqa: ARG002
        """Ensure new users receive the default role."""

        repo = UserRepository(self.user_db.session)
        default_role = await repo.ensure_role(DEFAULT_ROLE_NAME, DEFAULT_ROLE_DESCRIPTION)
        await repo.assign_role(user, default_role)
        await self.user_db.session.refresh(user)


async def get_user_db(session=Depends(get_db_session)) -> AsyncGenerator[SQLAlchemyUserDatabase[User, str], None]:
    """Yield a SQLAlchemy-backed user database."""

    yield SQLAlchemyUserDatabase(session, User)


async def get_user_manager(
    user_db: SQLAlchemyUserDatabase[User, str] = Depends(get_user_db),
    settings: Settings = Depends(get_settings),
) -> AsyncGenerator[UserManager, None]:
    """Yield the configured user manager."""

    yield UserManager(user_db, settings)


__all__ = ["UserManager", "get_user_manager", "get_user_db"]
