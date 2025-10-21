"""Auth API routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..infrastructure.database import User
from .dependencies import get_current_user
from .models import UserRead

router = APIRouter()


@router.get("/me", response_model=UserRead)
async def read_current_user(user: User = Depends(get_current_user)) -> UserRead:
    """Return details about the currently authenticated user."""

    return UserRead.model_validate(user)


__all__ = ["router"]
