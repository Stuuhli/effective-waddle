"""Service layer for admin endpoints."""
from __future__ import annotations

from fastapi import HTTPException, status

from ..auth.constants import GRAPH_RAG_ROLE_NAME, PERMISSION_ROLE_NAMES, RAG_ROLE_NAME
from ..infrastructure.database import RoleCategory
from ..infrastructure.repositories.document_repo import DocumentRepository
from ..infrastructure.repositories.user_repo import UserRepository
from .schemas import (
    CollectionAdminResponse,
    CollectionCreate,
    CollectionRolesUpdate,
    FeatureFlagUpdate,
    RoleAssignment,
    RoleCreate,
    RoleResponse,
    UserRoleUpdate,
)


class AdminService:
    """Provide administrative utilities."""

    def __init__(self, user_repo: UserRepository, document_repo: DocumentRepository) -> None:
        self.user_repo = user_repo
        self.document_repo = document_repo

    async def list_users(self):
        users = await self.user_repo.list()
        return users

    async def list_roles(self):
        roles = await self.user_repo.list_roles()
        return [
            RoleResponse(
                id=role.id,
                name=role.name,
                description=role.description,
                category=role.category,
            )
            for role in roles
        ]

    async def create_role(self, payload: RoleCreate):
        role = await self.user_repo.ensure_role(
            payload.name, payload.description, category=RoleCategory.workspace
        )
        await self.user_repo.commit()
        return role

    async def _resolve_roles(
        self,
        names: list[str],
        *,
        workspace_only: bool = False,
    ) -> list:
        resolved = []
        for name in names:
            category = (
                RoleCategory.permission
                if name in PERMISSION_ROLE_NAMES
                else RoleCategory.workspace
            )
            if workspace_only and category is not RoleCategory.workspace:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Only workspace roles can be used for collections.",
                )
            role = await self.user_repo.ensure_role(name, category=category)
            if workspace_only and role.category is not RoleCategory.workspace:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Only workspace roles can be used for collections.",
                )
            resolved.append(role)
        return resolved

    async def assign_role(self, payload: RoleAssignment):
        user = await self.user_repo.get(payload.user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        category = (
            RoleCategory.permission
            if payload.role_name in PERMISSION_ROLE_NAMES
            else RoleCategory.workspace
        )
        role = await self.user_repo.ensure_role(payload.role_name, category=category)
        await self.user_repo.assign_role(user, role)
        return user

    async def update_user_roles(self, user_id: str, payload: UserRoleUpdate):
        user = await self.user_repo.get(user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        roles = await self._resolve_roles(list(payload.role_names))
        await self.user_repo.set_user_roles(user, roles)
        await self.user_repo.session.refresh(user)
        return user

    async def update_feature_flags(self, payload: FeatureFlagUpdate):
        user = await self.user_repo.get(payload.user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        if payload.enable_graphrag:
            role = await self.user_repo.ensure_role(
                GRAPH_RAG_ROLE_NAME, "GraphRAG access", category=RoleCategory.permission
            )
        else:
            role = await self.user_repo.ensure_role(
                RAG_ROLE_NAME, "Core RAG access", category=RoleCategory.permission
            )
        await self.user_repo.assign_role(user, role)
        return user

    async def list_collections(self) -> list[CollectionAdminResponse]:
        collections = await self.document_repo.list_all_collections()
        counts = await self.document_repo.collection_document_counts([collection.id for collection in collections])
        return [
            CollectionAdminResponse(
                id=collection.id,
                name=collection.name,
                description=collection.description,
                roles=[
                    role.name
                    for role in collection.roles
                    if role.category is RoleCategory.workspace
                ],
                document_count=counts.get(collection.id, 0),
            )
            for collection in collections
        ]

    async def create_collection(self, payload: CollectionCreate) -> CollectionAdminResponse:
        existing = await self.document_repo.get_collection_by_name(payload.name)
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Collection already exists")

        collection = await self.document_repo.create_collection(payload.name, payload.description)
        roles = await self._resolve_roles(list(payload.role_names), workspace_only=True)
        if roles:
            await self.document_repo.set_collection_roles(collection, roles)
        await self.document_repo.commit()
        await self.document_repo.session.refresh(collection)
        return CollectionAdminResponse(
            id=collection.id,
            name=collection.name,
            description=collection.description,
            roles=[role.name for role in collection.roles if role.category is RoleCategory.workspace],
            document_count=0,
        )

    async def update_collection_roles(self, collection_id: str, payload: CollectionRolesUpdate) -> CollectionAdminResponse:
        collection = await self.document_repo.get_collection(collection_id)
        if collection is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
        roles = await self._resolve_roles(list(payload.role_names), workspace_only=True)
        await self.document_repo.set_collection_roles(collection, roles)
        await self.document_repo.commit()
        await self.document_repo.session.refresh(collection)
        counts = await self.document_repo.collection_document_counts([collection.id])
        return CollectionAdminResponse(
            id=collection.id,
            name=collection.name,
            description=collection.description,
            roles=[role.name for role in collection.roles if role.category is RoleCategory.workspace],
            document_count=counts.get(collection.id, 0),
        )

    async def update_user_status(self, user_id: str, is_active: bool):
        user = await self.user_repo.get(user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        user.is_active = is_active
        await self.user_repo.session.flush()
        await self.user_repo.commit()
        await self.user_repo.session.refresh(user)
        return user

    async def delete_user(self, user_id: str) -> None:
        user = await self.user_repo.get(user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        await self.user_repo.delete(user)
        await self.user_repo.commit()

    async def delete_collection(self, collection_id: str) -> None:
        collection = await self.document_repo.get_collection(collection_id)
        if collection is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
        await self.document_repo.delete(collection)
        await self.document_repo.commit()


__all__ = ["AdminService"]
