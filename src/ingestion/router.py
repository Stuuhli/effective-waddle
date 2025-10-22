"""Ingestion endpoints."""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from ..auth.dependencies import get_current_user
from ..infrastructure.database import (
    IngestionEvent,
    IngestionEventStatus,
    IngestionJob,
    IngestionStep,
    User,
)
from .dependencies import get_ingestion_service
from .schemas import (
    CollectionResponse,
    IngestionEventResponse,
    IngestionJobCreate,
    IngestionJobResponse,
    JobSummaryResponse,
)
from .service import IngestionService

router = APIRouter()


def _event_to_response(event: IngestionEvent) -> IngestionEventResponse:
    return IngestionEventResponse(
        id=event.id,
        step=event.step,
        status=event.status,
        document_id=event.document_id,
        document_title=event.document_title,
        document_path=event.document_path,
        detail=event.detail,
        created_at=event.created_at,
        updated_at=event.updated_at,
    )


def _job_display_source(job: IngestionJob) -> str:
    parameters = job.parameters or {}
    if isinstance(parameters, dict):
        original = parameters.get("original_filename")
        if isinstance(original, str) and original.strip():
            return original.strip()
    return job.source


def _job_to_response(job: IngestionJob, events: list[IngestionEvent]) -> IngestionJobResponse:
    return IngestionJobResponse(
        id=job.id,
        status=job.status,
        source=_job_display_source(job),
        collection_name=job.collection.name if job.collection else "unknown",
        error_message=job.error_message,
        chunk_size=job.chunk_size,
        chunk_overlap=job.chunk_overlap,
        metadata=job.parameters,
        created_at=job.created_at,
        updated_at=job.updated_at,
        events=[_event_to_response(event) for event in events],
    )


async def _store_upload(file: UploadFile, base_dir: Path) -> Path:
    base_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "document").suffix or ".pdf"
    safe_name = f"{uuid.uuid4()}{suffix}"
    target = base_dir / safe_name
    content = await file.read()
    target.write_bytes(content)
    return target


@router.post("/jobs", response_model=IngestionJobResponse, status_code=201)
async def create_job(
    payload: IngestionJobCreate,
    user: User = Depends(get_current_user),
    service: IngestionService = Depends(get_ingestion_service),
) -> IngestionJobResponse:
    job = await service.create_job(user.id, payload, user.roles)
    events = await service.list_job_events(job.id)
    return _job_to_response(job, events)


@router.post("/jobs/upload", response_model=list[IngestionJobResponse], status_code=201)
async def upload_jobs(
    files: list[UploadFile] = File(...),
    collection: str = Form(...),
    chunk_size: int | None = Form(default=None),
    chunk_overlap: int | None = Form(default=None),
    metadata: str | None = Form(default=None),
    user: User = Depends(get_current_user),
    service: IngestionService = Depends(get_ingestion_service),
) -> list[IngestionJobResponse]:
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No files uploaded")
    try:
        metadata_payload: dict[str, Any] | None = json.loads(metadata) if metadata else None
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive parsing
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid metadata JSON") from exc

    settings = service.settings
    responses: list[IngestionJobResponse] = []
    for upload in files:
        stored_path = await _store_upload(upload, settings.storage.upload_dir)
        payload = IngestionJobCreate(
            source=str(stored_path),
            collection_name=collection,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            metadata={**(metadata_payload or {}), "original_filename": upload.filename},
        )
        job = await service.create_job(user.id, payload, user.roles)
        for step in (
            IngestionStep.docling_parse,
            IngestionStep.chunk_assembly,
            IngestionStep.embedding_indexing,
            IngestionStep.citation_enrichment,
        ):
            await service.create_event(
                job=job,
                step=step,
                status_value=IngestionEventStatus.pending,
                document_path=str(stored_path),
            )
        events = await service.list_job_events(job.id)
        responses.append(_job_to_response(job, events))
    return responses


@router.get("/jobs/{job_id}", response_model=IngestionJobResponse)
async def get_job(
    job_id: str,
    user: User = Depends(get_current_user),
    service: IngestionService = Depends(get_ingestion_service),
) -> IngestionJobResponse:
    job = await service.get_job(job_id)
    events = await service.list_job_events(job.id)
    return _job_to_response(job, events)


@router.get("/jobs", response_model=list[JobSummaryResponse])
async def list_jobs(
    limit: int = 20,
    user: User = Depends(get_current_user),
    service: IngestionService = Depends(get_ingestion_service),
) -> list[JobSummaryResponse]:
    jobs = await service.list_jobs_for_user(None if user.is_superuser else user.id, limit=limit)
    return [
        JobSummaryResponse(
            id=job.id,
            source=_job_display_source(job),
            status=job.status,
            collection_name=job.collection.name if job.collection else "unknown",
            updated_at=job.updated_at,
        )
        for job in jobs
    ]


@router.get("/collections", response_model=list[CollectionResponse])
async def list_collections(
    user: User = Depends(get_current_user),
    service: IngestionService = Depends(get_ingestion_service),
) -> list[CollectionResponse]:
    summaries = await service.collection_summaries(user.roles)
    return [
        CollectionResponse(
            id=item["id"],
            name=item["name"],
            description=item["description"],
            document_count=item["document_count"],
            default_chunk_size=item["default_chunk_size"],
            default_chunk_overlap=item["default_chunk_overlap"],
        )
        for item in summaries
    ]


__all__ = ["router"]
