"""Admin dependencies."""
from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import require_roles
from ..dependencies import get_db_session
from ..infrastructure.repositories.document_repo import DocumentRepository
from ..infrastructure.repositories.user_repo import UserRepository
from .service import AdminService


async def get_admin_service(session: AsyncSession = Depends(get_db_session)) -> AdminService:
    user_repo = UserRepository(session)
    document_repo = DocumentRepository(session)
    return AdminService(user_repo, document_repo)


def admin_required():
    return require_roles("admin")


__all__ = ["get_admin_service", "admin_required"]
