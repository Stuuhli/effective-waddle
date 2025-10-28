"""Schemas for admin operations."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, EmailStr, Field

from ..infrastructure.database import RoleCategory


PasswordField = Field(min_length=8, description="Password must be at least 8 characters long.")


class RoleCreate(BaseModel):
    name: str
    description: Optional[str] = None


class RoleAssignment(BaseModel):
    user_id: str
    role_name: str


class UserCreate(BaseModel):
    email: EmailStr
    password: str = PasswordField


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=8)


class UserAdminResponse(BaseModel):
    id: str
    email: str
    roles: list[str]
    is_active: bool


class FeatureFlagUpdate(BaseModel):
    user_id: str
    enable_graphrag: bool


class RoleResponse(BaseModel):
    id: str
    name: str
    description: str | None = None
    category: RoleCategory


class UserRoleUpdate(BaseModel):
    role_names: list[str]


class UserStatusUpdate(BaseModel):
    is_active: bool


class CollectionCreate(BaseModel):
    name: str
    description: str | None = None
    role_names: list[str] = []


class CollectionRolesUpdate(BaseModel):
    role_names: list[str]


class CollectionAdminResponse(BaseModel):
    id: str
    name: str
    description: str | None = None
    roles: list[str]
    document_count: int


class GraphRAGCommandBase(BaseModel):
    root: Path | None = None
    config: Path | None = None
    verbose: bool | None = None


class GraphRAGPromptTuneRequest(GraphRAGCommandBase):
    domain: str | None = None
    limit: int | None = None


class GraphRAGIndexRequest(GraphRAGCommandBase):
    reset: bool | None = None


class GraphRAGCommandResponse(BaseModel):
    command: str
    exit_code: int
    stdout: str
    stderr: str
    success: bool


__all__ = [
    "RoleCreate",
    "RoleAssignment",
    "UserCreate",
    "UserUpdate",
    "UserAdminResponse",
    "FeatureFlagUpdate",
    "RoleResponse",
    "UserRoleUpdate",
    "UserStatusUpdate",
    "CollectionCreate",
    "CollectionRolesUpdate",
    "CollectionAdminResponse",
    "GraphRAGPromptTuneRequest",
    "GraphRAGIndexRequest",
    "GraphRAGCommandResponse",
]
