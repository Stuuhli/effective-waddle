"""Auth API routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..dependencies import get_db_session, get_settings
from ..infrastructure.database import User
from ..infrastructure.repositories.user_repo import UserRepository
from .dependencies import get_current_user
from .models import UserRead
from .schemas import RefreshRequest, TokenResponse
from .service import AuthService

router = APIRouter()


@router.get("/me", response_model=UserRead)
async def read_current_user(user: User = Depends(get_current_user)) -> UserRead:
    """Return details about the currently authenticated user."""

    return UserRead.model_validate(user)


@router.post("/jwt/refresh", response_model=TokenResponse)
async def refresh_access_token(
    payload: RefreshRequest,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    """Refresh the access token using a valid refresh token."""

    service = AuthService(UserRepository(session), settings)
    return await service.refresh_tokens(payload.refresh_token)


__all__ = ["router"]
