"""Dependencies for ingestion module."""
from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import load_settings
from ..dependencies import get_db_session
from ..infrastructure.repositories.document_repo import DocumentRepository
from .service import IngestionService


async def get_ingestion_service(session: AsyncSession = Depends(get_db_session)) -> IngestionService:
    repo = DocumentRepository(session)
    return IngestionService(repo, settings=load_settings())


__all__ = ["get_ingestion_service"]
