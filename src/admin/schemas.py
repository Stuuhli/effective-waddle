"""Schemas for admin operations."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class RoleCreate(BaseModel):
    name: str
    description: Optional[str] = None


class RoleAssignment(BaseModel):
    user_id: str
    role_name: str


class UserAdminResponse(BaseModel):
    id: str
    email: str
    roles: list[str]
    is_active: bool


class FeatureFlagUpdate(BaseModel):
    user_id: str
    enable_graphrag: bool


__all__ = ["RoleCreate", "RoleAssignment", "UserAdminResponse", "FeatureFlagUpdate"]
