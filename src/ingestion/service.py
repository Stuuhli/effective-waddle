"""Ingestion orchestration service."""
from __future__ import annotations

from fastapi import HTTPException, status

from ..infrastructure.database import IngestionJob, IngestionStatus
from ..infrastructure.repositories.document_repo import DocumentRepository
from .schemas import IngestionJobCreate


class IngestionService:
    """Manage ingestion job lifecycle."""

    def __init__(self, document_repo: DocumentRepository) -> None:
        self.document_repo = document_repo

    async def create_job(self, user_id: str | None, payload: IngestionJobCreate) -> IngestionJob:
        if not payload.source:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Source is required")
        job = await self.document_repo.create_ingestion_job(
            user_id=user_id,
            source=payload.source,
            collection_name=payload.collection_name,
        )
        await self.document_repo.commit()
        return job

    async def get_job(self, job_id: str) -> IngestionJob:
        job = await self.document_repo.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        return job

    async def list_collections(self) -> list[dict[str, object]]:
        documents = await self.document_repo.list()
        counts: dict[str, int] = {}
        for doc in documents:
            key = (doc.ingestion_job.collection_name if doc.ingestion_job else "default")
            counts[key] = counts.get(key, 0) + 1
        return [{"name": name, "document_count": count} for name, count in counts.items()]

    async def update_status(self, job: IngestionJob, status_value: IngestionStatus, error_message: str | None = None) -> IngestionJob:
        updated = await self.document_repo.update_job_status(job, status=status_value, error_message=error_message)
        await self.document_repo.commit()
        return updated


__all__ = ["IngestionService"]
