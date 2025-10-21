"""Ingestion specific exceptions."""
from __future__ import annotations

from ..exceptions import NotFoundError, ServiceError


class IngestionError(ServiceError):
    """Raised when ingestion fails."""


class IngestionJobNotFoundError(NotFoundError):
    """Raised when an ingestion job cannot be found."""


__all__ = ["IngestionError", "IngestionJobNotFoundError"]
