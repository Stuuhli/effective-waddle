"""Service layer for admin endpoints."""
from __future__ import annotations

from fastapi import HTTPException, status

from ..auth.constants import GRAPH_RAG_ROLE_NAME, RAG_ROLE_NAME
from ..infrastructure.repositories.user_repo import UserRepository
from .schemas import FeatureFlagUpdate, RoleAssignment, RoleCreate


class AdminService:
    """Provide administrative utilities."""

    def __init__(self, user_repo: UserRepository) -> None:
        self.user_repo = user_repo

    async def list_users(self):
        users = await self.user_repo.list()
        return users

    async def create_role(self, payload: RoleCreate):
        role = await self.user_repo.ensure_role(payload.name, payload.description)
        await self.user_repo.commit()
        return role

    async def assign_role(self, payload: RoleAssignment):
        user = await self.user_repo.get(payload.user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        role = await self.user_repo.ensure_role(payload.role_name)
        await self.user_repo.assign_role(user, role)
        return user

    async def update_feature_flags(self, payload: FeatureFlagUpdate):
        user = await self.user_repo.get(payload.user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        if payload.enable_graphrag:
            role = await self.user_repo.ensure_role(GRAPH_RAG_ROLE_NAME, "GraphRAG access")
        else:
            role = await self.user_repo.ensure_role(RAG_ROLE_NAME, "Core RAG access")
        await self.user_repo.assign_role(user, role)
        return user


__all__ = ["AdminService"]
