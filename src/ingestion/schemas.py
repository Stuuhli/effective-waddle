"""Schemas for ingestion endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from ..infrastructure.database import IngestionStatus


class IngestionJobCreate(BaseModel):
    source: str = Field(..., description="Path or URI to ingest")
    collection_name: str


class IngestionJobResponse(BaseModel):
    id: str
    status: IngestionStatus
    source: str
    collection_name: str
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime


class CollectionResponse(BaseModel):
    name: str
    document_count: int


__all__ = ["IngestionJobCreate", "IngestionJobResponse", "CollectionResponse"]
