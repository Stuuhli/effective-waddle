"""Auth API routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from .dependencies import get_auth_service, get_current_user
from .schemas import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse, UserResponse
from .service import AuthService

router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=201)
async def register_user(payload: RegisterRequest, auth_service: AuthService = Depends(get_auth_service)) -> UserResponse:
    user = await auth_service.register_user(payload)
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        roles=[role.name for role in user.roles],
        created_at=user.created_at,
    )


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, auth_service: AuthService = Depends(get_auth_service)) -> TokenResponse:
    user = await auth_service.authenticate_user(payload)
    return auth_service.create_tokens(user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_tokens(
    payload: RefreshRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    return await auth_service.refresh_tokens(payload.refresh_token)


@router.get("/me", response_model=UserResponse)
async def get_me(user_info: tuple[str, list[str]] = Depends(get_current_user), auth_service: AuthService = Depends(get_auth_service)) -> UserResponse:
    user = await auth_service.user_repo.get(user_info[0])
    assert user is not None
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        roles=[role.name for role in user.roles],
        created_at=user.created_at,
    )


__all__ = ["router"]
