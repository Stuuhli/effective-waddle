"""Retrieval specific exceptions."""
from __future__ import annotations

from ..exceptions import ServiceError


class RetrievalError(ServiceError):
    """Base class for retrieval failures."""


class ConversationNotFoundError(RetrievalError):
    """Raised when a chat session cannot be found."""


__all__ = ["RetrievalError", "ConversationNotFoundError"]
