"""Schemas for ingestion endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from ..infrastructure.database import IngestionEventStatus, IngestionStatus, IngestionStep


class IngestionJobCreate(BaseModel):
    source: str = Field(..., description="Path or URI to ingest")
    collection_name: str
    chunk_size: int | None = Field(
        None,
        ge=50,
        le=5000,
        description="Preferred chunk size. Falls back to system default when omitted.",
    )
    chunk_overlap: int | None = Field(
        None,
        ge=0,
        le=2500,
        description="Preferred chunk overlap. Falls back to system default when omitted.",
    )
    metadata: dict[str, object] | None = Field(
        default=None,
        description="Arbitrary metadata to persist alongside ingested documents.",
    )


class IngestionEventResponse(BaseModel):
    id: str
    step: IngestionStep
    status: IngestionEventStatus
    document_id: Optional[str]
    document_title: Optional[str]
    document_path: Optional[str]
    detail: Optional[dict[str, object]]
    created_at: datetime
    updated_at: datetime


class IngestionJobResponse(BaseModel):
    id: str
    status: IngestionStatus
    source: str
    collection_name: str
    error_message: Optional[str]
    chunk_size: int
    chunk_overlap: int
    metadata: Optional[dict[str, object]]
    created_at: datetime
    updated_at: datetime
    events: list[IngestionEventResponse] = Field(default_factory=list)


class CollectionResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    document_count: int
    default_chunk_size: int
    default_chunk_overlap: int


class JobSummaryResponse(BaseModel):
    id: str
    source: str
    status: IngestionStatus
    collection_name: str
    updated_at: datetime


__all__ = [
    "IngestionJobCreate",
    "IngestionJobResponse",
    "CollectionResponse",
    "IngestionEventResponse",
    "JobSummaryResponse",
]
