"""Document repository implementation."""
from __future__ import annotations

from collections.abc import Sequence
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import Chunk, Document, IngestionJob, IngestionStatus
from .base import AsyncRepository


class DocumentRepository(AsyncRepository[Document]):
    """CRUD operations for documents and chunks."""

    model = Document

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def create_document(
        self,
        *,
        title: str,
        source_path: str,
        collection_name: str,
        metadata: dict[str, object] | None = None,
        job: IngestionJob | None = None,
    ) -> Document:
        document = Document(
            title=title,
            source_path=source_path,
            ingestion_job_id=job.id if job else None,
            metadata_json={**(metadata or {}), "collection_name": collection_name},
        )
        await self.add(document)
        await self.commit()
        await self.session.refresh(document)
        return document

    async def add_chunk(
        self,
        *,
        document_id: str,
        content: str,
        vector_id: str | None = None,
        embedding_model: str | None = None,
        embedding: Sequence[float] | None = None,
    ) -> Chunk:
        chunk = Chunk(
            document_id=document_id,
            content=content,
            vector_id=vector_id,
            embedding_model=embedding_model,
            embedding=list(embedding) if embedding is not None else None,
        )
        self.session.add(chunk)
        await self.session.flush()
        await self.session.refresh(chunk)
        return chunk

    async def list_documents_by_collection(self, collection_name: str) -> list[Document]:
        stmt = select(Document).join(IngestionJob, isouter=True).where(IngestionJob.collection_name == collection_name)
        result = await self.session.execute(stmt)
        return list(result.scalars())

    async def list_ingestion_jobs(self) -> list[IngestionJob]:
        result = await self.session.execute(select(IngestionJob))
        return list(result.scalars())

    async def create_ingestion_job(
        self, *, user_id: str | None, source: str, collection_name: str
    ) -> IngestionJob:
        job = IngestionJob(user_id=user_id, source=source, collection_name=collection_name)
        self.session.add(job)
        await self.session.flush()
        await self.session.refresh(job)
        return job

    async def update_job_status(
        self,
        job: IngestionJob,
        *,
        status: IngestionStatus,
        error_message: str | None = None,
    ) -> IngestionJob:
        job.status = status
        job.error_message = error_message
        await self.session.flush()
        await self.session.refresh(job)
        return job

    async def get_job(self, job_id: str) -> Optional[IngestionJob]:
        result = await self.session.execute(select(IngestionJob).where(IngestionJob.id == job_id))
        return result.scalar_one_or_none()


__all__ = ["DocumentRepository"]
