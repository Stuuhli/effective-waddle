"""Admin API routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from .dependencies import admin_required, get_admin_service
from .schemas import FeatureFlagUpdate, RoleAssignment, RoleCreate, UserAdminResponse
from .service import AdminService

router = APIRouter(dependencies=[Depends(admin_required())])


@router.get("/users", response_model=list[UserAdminResponse])
async def list_users(service: AdminService = Depends(get_admin_service)) -> list[UserAdminResponse]:
    users = await service.list_users()
    return [UserAdminResponse(id=user.id, email=user.email, roles=[role.name for role in user.roles], is_active=user.is_active) for user in users]


@router.post("/roles", status_code=201)
async def create_role(payload: RoleCreate, service: AdminService = Depends(get_admin_service)) -> dict[str, str]:
    role = await service.create_role(payload)
    return {"id": role.id, "name": role.name}


@router.post("/roles/assign", response_model=UserAdminResponse)
async def assign_role(payload: RoleAssignment, service: AdminService = Depends(get_admin_service)) -> UserAdminResponse:
    user = await service.assign_role(payload)
    return UserAdminResponse(id=user.id, email=user.email, roles=[role.name for role in user.roles], is_active=user.is_active)


@router.post("/feature-flags/graphrag", response_model=UserAdminResponse)
async def update_graphrag_flag(
    payload: FeatureFlagUpdate,
    service: AdminService = Depends(get_admin_service),
) -> UserAdminResponse:
    user = await service.update_feature_flags(payload)
    return UserAdminResponse(id=user.id, email=user.email, roles=[role.name for role in user.roles], is_active=user.is_active)


__all__ = ["router"]
