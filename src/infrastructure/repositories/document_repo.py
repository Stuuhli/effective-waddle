"""Document repository implementation."""
from __future__ import annotations

from collections.abc import Sequence
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database import (
    Chunk,
    Collection,
    Document,
    IngestionEvent,
    IngestionEventStatus,
    IngestionJob,
    IngestionStatus,
    IngestionStep,
    Role,
)
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
            metadata_json=self._build_document_metadata(metadata, collection_name, job),
        )
        await self.add(document)
        await self.commit()
        await self.session.refresh(document)
        return document

    @staticmethod
    def _build_document_metadata(
        metadata: dict[str, object] | None,
        collection_name: str,
        job: IngestionJob | None,
    ) -> dict[str, object]:
        combined: dict[str, object] = {**(metadata or {})}
        combined["collection_name"] = collection_name
        if job is not None:
            combined.setdefault("chunk_size", job.chunk_size)
            combined.setdefault("chunk_overlap", job.chunk_overlap)
            if job.parameters:
                combined.setdefault("ingestion_parameters", job.parameters)
        return combined

    async def add_chunk(
        self,
        *,
        document_id: str,
        content: str,
        vector_id: str | None = None,
        embedding_model: str | None = None,
        embedding: Sequence[float] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> Chunk:
        chunk = Chunk(
            document_id=document_id,
            content=content,
            vector_id=vector_id,
            embedding_model=embedding_model,
            embedding=list(embedding) if embedding is not None else None,
            metadata_json=metadata,
        )
        self.session.add(chunk)
        await self.session.flush()
        await self.session.refresh(chunk)
        return chunk

    async def list_documents_by_collection(self, collection_name: str) -> list[Document]:
        stmt = (
            select(Document)
            .join(IngestionJob, isouter=True)
            .join(Collection, IngestionJob.collection)
            .where(Collection.name == collection_name)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars())

    async def list_ingestion_jobs(self) -> list[IngestionJob]:
        result = await self.session.execute(select(IngestionJob))
        return list(result.scalars())

    async def create_ingestion_job(
        self,
        *,
        user_id: str | None,
        source: str,
        chunk_size: int,
        chunk_overlap: int,
        parameters: dict[str, object] | None = None,
        collection: Collection,
    ) -> IngestionJob:
        normalised_parameters = None
        if parameters:
            normalised_parameters = {
                str(key): value for key, value in parameters.items() if not str(key).startswith("_")
            }
        job = IngestionJob(
            user_id=user_id,
            source=source,
            collection_id=collection.id,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            parameters=normalised_parameters,
        )
        self.session.add(job)
        await self.session.flush()
        await self.session.refresh(job)
        await self.session.refresh(job, attribute_names=["collection"])
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
        stmt = (
            select(IngestionJob)
            .options(
                selectinload(IngestionJob.collection),
                selectinload(IngestionJob.events),
                selectinload(IngestionJob.documents),
            )
            .where(IngestionJob.id == job_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def ensure_collection(self, name: str, description: str | None = None) -> Collection:
        stmt = select(Collection).where(Collection.name == name)
        result = await self.session.execute(stmt)
        collection = result.scalar_one_or_none()
        if collection:
            return collection
        collection = Collection(name=name, description=description)
        self.session.add(collection)
        await self.session.flush()
        await self.session.refresh(collection)
        return collection

    async def assign_collection_to_role(self, collection: Collection, role: Role) -> None:
        if role in collection.roles:
            return
        collection.roles.append(role)
        await self.session.flush()

    async def get_collection_by_name(self, name: str) -> Optional[Collection]:
        result = await self.session.execute(select(Collection).where(Collection.name == name))
        return result.scalar_one_or_none()

    async def list_collections_for_roles(self, roles: list[Role]) -> list[Collection]:
        if not roles:
            return []
        role_ids = [role.id for role in roles]
        stmt = (
            select(Collection)
            .join(Collection.roles)
            .where(Role.id.in_(role_ids))
            .distinct()
            .order_by(Collection.name)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars())

    async def list_job_events(self, job_id: str) -> list[IngestionEvent]:
        stmt = (
            select(IngestionEvent)
            .where(IngestionEvent.job_id == job_id)
            .order_by(IngestionEvent.created_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars())

    async def get_document(self, document_id: str) -> Document | None:
        stmt = (
            select(Document)
            .options(
                selectinload(Document.ingestion_job).selectinload(IngestionJob.collection),
                selectinload(Document.chunks),
            )
            .where(Document.id == document_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_event_for_step(self, job_id: str, step: IngestionStep) -> Optional[IngestionEvent]:
        stmt = (
            select(IngestionEvent)
            .where(IngestionEvent.job_id == job_id, IngestionEvent.step == step)
            .order_by(IngestionEvent.created_at)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def create_event(
        self,
        *,
        job_id: str,
        step: IngestionStep,
        status: IngestionEventStatus,
        document_id: str | None = None,
        document_title: str | None = None,
        document_path: str | None = None,
        detail: dict[str, object] | None = None,
    ) -> IngestionEvent:
        event = IngestionEvent(
            job_id=job_id,
            document_id=document_id,
            document_title=document_title,
            document_path=document_path,
            step=step,
            status=status,
            detail=detail,
        )
        self.session.add(event)
        await self.session.flush()
        await self.session.refresh(event)
        return event

    async def update_event_status(
        self,
        event: IngestionEvent,
        *,
        status: IngestionEventStatus,
        detail: dict[str, object] | None = None,
        document_id: str | None = None,
        document_title: str | None = None,
    ) -> IngestionEvent:
        event.status = status
        if detail is not None:
            event.detail = detail
        if document_id is not None:
            event.document_id = document_id
        if document_title is not None:
            event.document_title = document_title
        await self.session.flush()
        await self.session.refresh(event)
        return event

    async def list_jobs_for_user(self, user_id: str | None, limit: int = 20) -> list[IngestionJob]:
        stmt = (
            select(IngestionJob)
            .options(selectinload(IngestionJob.collection))
            .order_by(IngestionJob.updated_at.desc())
            .limit(limit)
        )
        if user_id is not None:
            stmt = stmt.where(IngestionJob.user_id == user_id)
        result = await self.session.execute(stmt)
        return list(result.scalars())

    async def collection_document_counts(self, collection_ids: list[str]) -> dict[str, int]:
        if not collection_ids:
            return {}
        stmt = (
            select(IngestionJob.collection_id, func.count(Document.id))
            .join(Document, isouter=True)
            .where(IngestionJob.collection_id.in_(collection_ids))
            .group_by(IngestionJob.collection_id)
        )
        result = await self.session.execute(stmt)
        return {row[0]: row[1] for row in result}


__all__ = ["DocumentRepository"]
