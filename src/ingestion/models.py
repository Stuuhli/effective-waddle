"""Ingestion models."""
from __future__ import annotations

from ..infrastructure.database import Chunk, Document, IngestionJob, IngestionStatus

__all__ = ["IngestionJob", "Document", "Chunk", "IngestionStatus"]
