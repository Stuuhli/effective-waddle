"""Pydantic schemas for FastAPI Users integration."""
from __future__ import annotations

from typing import Any, Optional

from fastapi_users import schemas
from pydantic import ConfigDict, EmailStr, Field, model_validator

from ..infrastructure.database import Role, User


class UserRead(schemas.BaseUser[str]):
    """Representation returned by the authentication endpoints."""

    full_name: Optional[str] = None
    roles: list[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def _extract_roles(cls, data: Any) -> Any:
        if isinstance(data, User):
            return {
                "id": data.id,
                "email": data.email,
                "is_active": data.is_active,
                "is_superuser": getattr(data, "is_superuser", False),
                "is_verified": getattr(data, "is_verified", False),
                "full_name": data.full_name,
                "roles": [role.name for role in data.roles],
            }
        if isinstance(data, dict) and "roles" in data:
            roles = data.get("roles")
            if roles and not all(isinstance(role, str) for role in roles):
                data = dict(data)
                data["roles"] = [role.name for role in roles if isinstance(role, Role)]
        return data


class UserCreate(schemas.BaseUserCreate):
    """Schema used when registering a new user."""

    email: EmailStr
    full_name: Optional[str] = None


class UserUpdate(schemas.BaseUserUpdate):
    """Schema used for partial updates of existing users."""

    full_name: Optional[str] = None


__all__ = ["UserRead", "UserCreate", "UserUpdate", "User", "Role"]
