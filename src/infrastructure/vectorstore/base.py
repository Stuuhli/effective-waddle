"""Abstract interfaces for vector store access."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any, Mapping


class VectorStoreClient(ABC):
    """Simple vector store abstraction."""

    @abstractmethod
    async def similarity_search(self, query: str, *, k: int = 5) -> Sequence[Mapping[str, Any]]:
        """Return top-k chunks with content and metadata for the query."""


__all__ = ["VectorStoreClient"]
