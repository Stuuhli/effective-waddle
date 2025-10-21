"""Embedding client abstractions."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence


# Central place to configure the expected embedding dimensionality that the
# pgvector column is created with. Downstream embedders normalise their output to
# this length to guarantee compatibility with persistence and similarity search.
EMBEDDING_DIMENSION = 1536


class EmbeddingClient(ABC):
    """Interface for text embedding providers."""

    model_name: str

    @abstractmethod
    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Return embeddings for the provided texts."""


__all__ = ["EmbeddingClient", "EMBEDDING_DIMENSION"]
