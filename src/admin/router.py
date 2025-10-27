"""Admin API routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from .dependencies import admin_required, get_admin_service
from .schemas import (
    CollectionAdminResponse,
    CollectionCreate,
    CollectionRolesUpdate,
    FeatureFlagUpdate,
    GraphRAGCommandResponse,
    GraphRAGIndexRequest,
    GraphRAGPromptTuneRequest,
    RoleAssignment,
    RoleCreate,
    RoleResponse,
    UserAdminResponse,
    UserRoleUpdate,
    UserStatusUpdate,
)
from .service import AdminService

router = APIRouter(dependencies=[Depends(admin_required())])


@router.get("/users", response_model=list[UserAdminResponse])
async def list_users(service: AdminService = Depends(get_admin_service)) -> list[UserAdminResponse]:
    users = await service.list_users()
    return [
        UserAdminResponse(
            id=user.id,
            email=user.email,
            roles=[role.name for role in user.roles],
            is_active=user.is_active,
        )
        for user in users
    ]


@router.get("/roles", response_model=list[RoleResponse])
async def list_roles(service: AdminService = Depends(get_admin_service)) -> list[RoleResponse]:
    return await service.list_roles()


@router.post("/roles", status_code=201)
async def create_role(payload: RoleCreate, service: AdminService = Depends(get_admin_service)) -> dict[str, str]:
    role = await service.create_role(payload)
    return {"id": role.id, "name": role.name}


@router.post("/roles/assign", response_model=UserAdminResponse)
async def assign_role(payload: RoleAssignment, service: AdminService = Depends(get_admin_service)) -> UserAdminResponse:
    user = await service.assign_role(payload)
    return UserAdminResponse(
        id=user.id,
        email=user.email,
        roles=[role.name for role in user.roles],
        is_active=user.is_active,
    )


@router.put("/users/{user_id}/roles", response_model=UserAdminResponse)
async def replace_user_roles(
    user_id: str,
    payload: UserRoleUpdate,
    service: AdminService = Depends(get_admin_service),
) -> UserAdminResponse:
    user = await service.update_user_roles(user_id, payload)
    return UserAdminResponse(
        id=user.id,
        email=user.email,
        roles=[role.name for role in user.roles],
        is_active=user.is_active,
    )


@router.patch("/users/{user_id}/status", response_model=UserAdminResponse)
async def update_user_status(
    user_id: str,
    payload: UserStatusUpdate,
    service: AdminService = Depends(get_admin_service),
) -> UserAdminResponse:
    user = await service.update_user_status(user_id, payload.is_active)
    return UserAdminResponse(
        id=user.id,
        email=user.email,
        roles=[role.name for role in user.roles],
        is_active=user.is_active,
    )


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(user_id: str, service: AdminService = Depends(get_admin_service)) -> Response:
    await service.delete_user(user_id)
    return Response(status_code=204)


@router.post("/feature-flags/graphrag", response_model=UserAdminResponse)
async def update_graphrag_flag(
    payload: FeatureFlagUpdate,
    service: AdminService = Depends(get_admin_service),
) -> UserAdminResponse:
    user = await service.update_feature_flags(payload)
    return UserAdminResponse(
        id=user.id,
        email=user.email,
        roles=[role.name for role in user.roles],
        is_active=user.is_active,
    )


@router.post("/graphrag/prompt-tune", response_model=GraphRAGCommandResponse)
async def trigger_graphrag_prompt_tune(
    payload: GraphRAGPromptTuneRequest,
    service: AdminService = Depends(get_admin_service),
) -> GraphRAGCommandResponse:
    return await service.run_graphrag_prompt_tune(payload)


@router.post("/graphrag/index", response_model=GraphRAGCommandResponse)
async def trigger_graphrag_index(
    payload: GraphRAGIndexRequest,
    service: AdminService = Depends(get_admin_service),
) -> GraphRAGCommandResponse:
    return await service.run_graphrag_index(payload)


@router.get("/collections", response_model=list[CollectionAdminResponse])
async def list_collections(service: AdminService = Depends(get_admin_service)) -> list[CollectionAdminResponse]:
    return await service.list_collections()


@router.post("/collections", response_model=CollectionAdminResponse, status_code=201)
async def create_collection(
    payload: CollectionCreate,
    service: AdminService = Depends(get_admin_service),
) -> CollectionAdminResponse:
    return await service.create_collection(payload)


@router.put("/collections/{collection_id}/roles", response_model=CollectionAdminResponse)
async def update_collection_roles(
    collection_id: str,
    payload: CollectionRolesUpdate,
    service: AdminService = Depends(get_admin_service),
) -> CollectionAdminResponse:
    return await service.update_collection_roles(collection_id, payload)


@router.delete("/collections/{collection_id}", status_code=204)
async def delete_collection(
    collection_id: str, service: AdminService = Depends(get_admin_service)
) -> Response:
    await service.delete_collection(collection_id)
    return Response(status_code=204)


__all__ = ["router"]
