"""Abstract interfaces for vector store access."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence


class VectorStoreClient(ABC):
    """Simple vector store abstraction."""

    @abstractmethod
    async def similarity_search(self, query: str, *, k: int = 5) -> Sequence[str]:
        """Return top-k text snippets for the query."""


__all__ = ["VectorStoreClient"]
