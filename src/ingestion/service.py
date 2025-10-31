"""Ingestion orchestration service."""
from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from fastapi import HTTPException, status

from ..config import Settings, load_settings
from ..infrastructure.database import (
    Collection,
    Document,
    IngestionEvent,
    IngestionEventStatus,
    IngestionJob,
    IngestionStatus,
    IngestionStep,
    Role,
)
from ..infrastructure.repositories.document_repo import DocumentRepository
from .schemas import IngestionJobCreate

LOGGER = logging.getLogger(__name__)


class IngestionService:
    """Manage ingestion job lifecycle."""

    def __init__(self, document_repo: DocumentRepository, settings: Settings | None = None) -> None:
        self.document_repo = document_repo
        self._settings = settings or load_settings()

    @property
    def settings(self) -> Settings:
        return self._settings

    async def _resolve_collection(self, name: str, roles: list[Role]) -> Collection:
        collection = await self.document_repo.get_collection_by_name(name)
        if collection is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
        allowed_collections = await self.document_repo.list_collections_for_roles(roles)
        if collection not in allowed_collections:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Collection not accessible")
        return collection

    async def create_job(self, user_id: str | None, payload: IngestionJobCreate, roles: list[Role]) -> IngestionJob:
        if not payload.source:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Source is required")
        collection = await self._resolve_collection(payload.collection_name, roles)
        chunk_size = payload.chunk_size or self.settings.chunking.default_size
        chunk_overlap = payload.chunk_overlap or self.settings.chunking.default_overlap
        if chunk_size <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Chunk size must be positive")
        if chunk_overlap < 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Chunk overlap cannot be negative")
        if chunk_overlap >= chunk_size:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Chunk overlap must be smaller than chunk size",
            )
        job = await self.document_repo.create_ingestion_job(
            user_id=user_id,
            source=payload.source,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            parameters=payload.metadata,
            collection=collection,
        )
        await self.document_repo.commit()
        return job

    async def get_job(self, job_id: str) -> IngestionJob:
        job = await self.document_repo.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        return job

    async def get_document(self, document_id: str, roles: list[Role]) -> Document:
        document = await self.document_repo.get_document(document_id)
        if document is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

        ingestion_job = document.ingestion_job
        if ingestion_job and ingestion_job.collection:
            allowed_collections = await self.document_repo.list_collections_for_roles(roles)
            allowed_ids = {collection.id for collection in allowed_collections}
            if ingestion_job.collection.id not in allowed_ids:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Collection not accessible")
        return document

    async def list_collections(self, roles: list[Role]) -> list[Collection]:
        return await self.document_repo.list_collections_for_roles(roles)

    async def collection_summaries(self, roles: list[Role]) -> list[dict[str, object]]:
        collections = await self.list_collections(roles)
        counts = await self.document_repo.collection_document_counts([collection.id for collection in collections])
        return [
            {
                "id": collection.id,
                "name": collection.name,
                "description": collection.description,
                "document_count": counts.get(collection.id, 0),
                "default_chunk_size": self.settings.chunking.default_size,
                "default_chunk_overlap": self.settings.chunking.default_overlap,
            }
            for collection in collections
        ]

    async def update_status(self, job: IngestionJob, status_value: IngestionStatus, error_message: str | None = None) -> IngestionJob:
        updated = await self.document_repo.update_job_status(job, status=status_value, error_message=error_message)
        await self.document_repo.commit()
        return updated

    async def list_job_events(self, job_id: str) -> list[IngestionEvent]:
        return await self.document_repo.list_job_events(job_id)

    async def list_jobs_for_user(self, user_id: str | None, limit: int = 20) -> list[IngestionJob]:
        return await self.document_repo.list_jobs_for_user(user_id, limit=limit)

    async def get_event_for_step(self, job_id: str, step: IngestionStep) -> IngestionEvent | None:
        return await self.document_repo.get_event_for_step(job_id, step)

    async def create_event(
        self,
        *,
        job: IngestionJob,
        step: IngestionStep,
        status_value: IngestionEventStatus,
        document_id: str | None = None,
        document_title: str | None = None,
        document_path: str | None = None,
        detail: dict[str, object] | None = None,
    ) -> IngestionEvent:
        event = await self.document_repo.create_event(
            job_id=job.id,
            step=step,
            status=status_value,
            document_id=document_id,
            document_title=document_title,
            document_path=document_path,
            detail=detail,
        )
        await self.document_repo.commit()
        return event

    async def update_event(
        self,
        event: IngestionEvent,
        *,
        status_value: IngestionEventStatus,
        detail: dict[str, object] | None = None,
        document_id: str | None = None,
        document_title: str | None = None,
    ) -> IngestionEvent:
        updated = await self.document_repo.update_event_status(
            event,
            status=status_value,
            detail=detail,
            document_id=document_id,
            document_title=document_title,
        )
        await self.document_repo.commit()
        return updated

    async def delete_job(self, job_id: str, *, roles: list[Role], is_superuser: bool = False) -> None:
        job = await self.document_repo.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

        if not is_superuser:
            allowed_collections = await self.document_repo.list_collections_for_roles(roles)
            allowed_ids = {collection.id for collection in allowed_collections}
            if job.collection_id not in allowed_ids:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Collection not accessible")

        cleanup_paths, index_keys = self._collect_artifacts(job)

        await self.document_repo.delete_job(job)
        await self.document_repo.commit()

        self._prune_docling_index(index_keys)
        self._cleanup_files(cleanup_paths)

    def _collect_artifacts(self, job: IngestionJob) -> tuple[set[Path], set[str]]:
        storage_settings = self.settings.storage
        docling_root = Path(storage_settings.docling_output_dir)
        cleanup_paths: set[Path] = set()
        index_keys: set[str] = set()

        def add_cleanup_path(value: object) -> None:
            if not isinstance(value, str) or not value.strip():
                return
            try:
                candidate = Path(value).expanduser()
            except (TypeError, ValueError):
                return
            cleanup_paths.add(candidate)

        def add_index_source(value: object) -> None:
            if not isinstance(value, str) or not value.strip():
                return
            index_keys.add(value)
            add_cleanup_path(value)

        add_index_source(job.source)

        for event in job.events or []:
            add_cleanup_path(event.document_path)

        for document in job.documents or []:
            add_index_source(document.source_path)
            metadata = document.metadata_json or {}
            source_meta = metadata.get("source_path")
            add_index_source(source_meta)

            docling_output = metadata.get("docling_output")
            if isinstance(docling_output, str):
                add_cleanup_path(docling_output)
                try:
                    cleanup_paths.add(Path(docling_output).expanduser().parent)
                except (TypeError, ValueError):
                    pass

            image_dir = metadata.get("image_dir")
            add_cleanup_path(image_dir)

            docling_hash = metadata.get("docling_hash")
            if isinstance(docling_hash, str) and docling_hash:
                cleanup_paths.add(docling_root / docling_hash)

        return cleanup_paths, index_keys

    def _cleanup_files(self, paths: set[Path]) -> None:
        if not paths:
            return

        storage_settings = self.settings.storage
        allowed_roots = [
            Path(storage_settings.upload_dir).resolve(),
            Path(storage_settings.docling_output_dir).resolve(),
        ]

        for path in paths:
            try:
                resolved = path.expanduser().resolve(strict=False)
            except (OSError, RuntimeError):
                continue

            if not any(root in resolved.parents or resolved == root for root in allowed_roots):
                continue

            if resolved in allowed_roots:
                # Never remove the root storage directories themselves.
                continue

            if resolved.is_dir():
                try:
                    shutil.rmtree(resolved, ignore_errors=False)
                except FileNotFoundError:
                    continue
                except OSError as error:
                    LOGGER.warning("Failed to remove directory %s: %s", resolved, error)
            else:
                try:
                    resolved.unlink(missing_ok=True)
                except OSError as error:
                    LOGGER.warning("Failed to remove file %s: %s", resolved, error)

    def _prune_docling_index(self, sources: set[str]) -> None:
        if not sources:
            return

        index_path = Path(self.settings.storage.docling_hash_index)
        if not index_path.exists():
            return

        try:
            mapping = json.loads(index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            LOGGER.warning("Docling hash index %s is corrupted; skipping cleanup.", index_path)
            return

        normalized: set[str] = set()
        for entry in sources:
            if not entry:
                continue
            normalized.add(str(entry))
            try:
                normalized.add(str(Path(entry).expanduser().resolve()))
            except (OSError, ValueError):
                continue

        changed = False
        for key in list(mapping.keys()):
            try:
                reference = {key, str(Path(key).expanduser().resolve())}
            except (OSError, ValueError):
                reference = {key}
            if reference & normalized:
                mapping.pop(key, None)
                changed = True

        if not changed:
            return

        if mapping:
            index_path.write_text(json.dumps(mapping, indent=2, ensure_ascii=False), encoding="utf-8")
        else:
            try:
                index_path.unlink()
            except OSError as error:
                LOGGER.warning("Failed to remove empty Docling hash index %s: %s", index_path, error)


__all__ = ["IngestionService"]
