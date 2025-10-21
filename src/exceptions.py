"""Shared exception hierarchy for the rag-platform services."""
from __future__ import annotations

from typing import Optional


class PlatformError(Exception):
    """Base exception for domain specific failures."""


class RepositoryError(PlatformError):
    """Raised when data access fails."""

    def __init__(self, message: str, *, cause: Optional[Exception] = None) -> None:
        super().__init__(message)
        self.cause = cause


class NotFoundError(RepositoryError):
    """Raised when an entity could not be located."""


class ServiceError(PlatformError):
    """Raised when a service level operation fails."""


__all__ = ["PlatformError", "RepositoryError", "NotFoundError", "ServiceError"]
