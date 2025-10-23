"""Service layer for admin endpoints."""
from __future__ import annotations

from fastapi import HTTPException, status

from ..auth.constants import GRAPH_RAG_ROLE_NAME, RAG_ROLE_NAME
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
        return [RoleResponse(id=role.id, name=role.name, description=role.description) for role in roles]

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

    async def update_user_roles(self, user_id: str, payload: UserRoleUpdate):
        user = await self.user_repo.get(user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        roles = []
        for name in payload.role_names:
            role = await self.user_repo.ensure_role(name)
            roles.append(role)
        await self.user_repo.set_user_roles(user, roles)
        await self.user_repo.session.refresh(user)
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

    async def list_collections(self) -> list[CollectionAdminResponse]:
        collections = await self.document_repo.list_all_collections()
        counts = await self.document_repo.collection_document_counts([collection.id for collection in collections])
        return [
            CollectionAdminResponse(
                id=collection.id,
                name=collection.name,
                description=collection.description,
                roles=[role.name for role in collection.roles],
                document_count=counts.get(collection.id, 0),
            )
            for collection in collections
        ]

    async def create_collection(self, payload: CollectionCreate) -> CollectionAdminResponse:
        existing = await self.document_repo.get_collection_by_name(payload.name)
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Collection already exists")

        collection = await self.document_repo.create_collection(payload.name, payload.description)
        roles = []
        for name in payload.role_names:
            role = await self.user_repo.ensure_role(name)
            roles.append(role)
        if roles:
            await self.document_repo.set_collection_roles(collection, roles)
        await self.document_repo.commit()
        await self.document_repo.session.refresh(collection)
        return CollectionAdminResponse(
            id=collection.id,
            name=collection.name,
            description=collection.description,
            roles=[role.name for role in collection.roles],
            document_count=0,
        )

    async def update_collection_roles(self, collection_id: str, payload: CollectionRolesUpdate) -> CollectionAdminResponse:
        collection = await self.document_repo.get_collection(collection_id)
        if collection is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
        roles = []
        for name in payload.role_names:
            role = await self.user_repo.ensure_role(name)
            roles.append(role)
        await self.document_repo.set_collection_roles(collection, roles)
        await self.document_repo.commit()
        await self.document_repo.session.refresh(collection)
        counts = await self.document_repo.collection_document_counts([collection.id])
        return CollectionAdminResponse(
            id=collection.id,
            name=collection.name,
            description=collection.description,
            roles=[role.name for role in collection.roles],
            document_count=counts.get(collection.id, 0),
        )


__all__ = ["AdminService"]
