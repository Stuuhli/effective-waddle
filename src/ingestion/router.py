"""Ingestion endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..auth.dependencies import get_current_user
from .dependencies import get_ingestion_service
from .schemas import CollectionResponse, IngestionJobCreate, IngestionJobResponse
from .service import IngestionService

router = APIRouter()


@router.post("/jobs", response_model=IngestionJobResponse, status_code=201)
async def create_job(
    payload: IngestionJobCreate,
    user_info: tuple[str, list[str]] = Depends(get_current_user),
    service: IngestionService = Depends(get_ingestion_service),
) -> IngestionJobResponse:
    job = await service.create_job(user_info[0], payload)
    return IngestionJobResponse(
        id=job.id,
        status=job.status,
        source=job.source,
        collection_name=job.collection_name,
        error_message=job.error_message,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.get("/jobs/{job_id}", response_model=IngestionJobResponse)
async def get_job(
    job_id: str,
    user_info: tuple[str, list[str]] = Depends(get_current_user),
    service: IngestionService = Depends(get_ingestion_service),
) -> IngestionJobResponse:
    job = await service.get_job(job_id)
    return IngestionJobResponse(
        id=job.id,
        status=job.status,
        source=job.source,
        collection_name=job.collection_name,
        error_message=job.error_message,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.get("/collections", response_model=list[CollectionResponse])
async def list_collections(
    user_info: tuple[str, list[str]] = Depends(get_current_user),
    service: IngestionService = Depends(get_ingestion_service),
) -> list[CollectionResponse]:
    collections = await service.list_collections()
    return [CollectionResponse(name=item["name"], document_count=item["document_count"]) for item in collections]


__all__ = ["router"]
