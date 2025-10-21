"""Authentication dependencies."""
from __future__ import annotations

from functools import update_wrapper
import inspect
from typing import Any, Awaitable, Callable, Optional

from fastapi import Depends, HTTPException, status
from fastapi_users import FastAPIUsers
from fastapi_users.authentication import AuthenticationBackend

from ..config import Settings
from ..dependencies import get_settings
from ..infrastructure.database import User
from .auth_backend import get_auth_backend
from .user_manager import get_user_manager


class _ConfigurableDependency:
    """Wrapper that allows late binding of FastAPI dependency callables."""

    def __init__(self, name: str) -> None:
        self._name = name
        self._dependency: Optional[Callable[..., Awaitable[Any]]] = None
        self.__doc__ = f"Dynamic dependency placeholder for {name}."

    def configure(self, dependency: Callable[..., Awaitable[Any]]) -> None:
        self._dependency = dependency
        update_wrapper(self, dependency)
        self.__signature__ = inspect.signature(dependency)

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        if self._dependency is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Authentication dependency '{self._name}' is not configured.",
            )
        return await self._dependency(*args, **kwargs)


_fastapi_users: FastAPIUsers[User, str] | None = None
_auth_backend: AuthenticationBackend | None = None
current_active_user = _ConfigurableDependency("current_active_user")


def configure_auth(settings: Settings) -> FastAPIUsers[User, str]:
    """Initialise FastAPI Users integration with the provided settings."""

    global _fastapi_users, _auth_backend
    backend = get_auth_backend(settings)
    users = FastAPIUsers[User, str](get_user_manager, [backend])
    current_active_user.configure(users.current_user(active=True))
    _fastapi_users = users
    _auth_backend = backend
    return users


def get_fastapi_users() -> FastAPIUsers[User, str]:
    """Return the configured FastAPI Users instance."""

    global _fastapi_users
    if _fastapi_users is None:
        configure_auth(get_settings())
    assert _fastapi_users is not None
    return _fastapi_users


def get_auth_backend_instance() -> AuthenticationBackend:
    """Return the configured authentication backend."""

    global _auth_backend
    if _auth_backend is None:
        configure_auth(get_settings())
    assert _auth_backend is not None
    return _auth_backend


async def get_current_user(user: User = Depends(current_active_user)) -> User:
    """Dependency returning the currently authenticated user."""

    return user


def require_roles(*allowed_roles: str) -> Callable[[User], User]:
    """Ensure that the current user possesses one of the provided roles."""

    async def dependency(user: User = Depends(current_active_user)) -> User:
        user_roles = {role.name for role in user.roles}
        if allowed_roles and not user_roles.intersection(allowed_roles):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user

    return dependency


# Configure the dependency graph with default settings so that router modules can import it.
configure_auth(get_settings())


__all__ = [
    "configure_auth",
    "current_active_user",
    "get_auth_backend_instance",
    "get_current_user",
    "get_fastapi_users",
    "require_roles",
]
