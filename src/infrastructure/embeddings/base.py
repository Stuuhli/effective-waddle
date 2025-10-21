"""Embedding client abstractions."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence


class EmbeddingClient(ABC):
    """Interface for text embedding providers."""

    model_name: str

    @abstractmethod
    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Return embeddings for the provided texts."""


__all__ = ["EmbeddingClient"]
