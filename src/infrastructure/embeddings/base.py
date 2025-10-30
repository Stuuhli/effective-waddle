"""Embedding client abstractions."""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from collections.abc import Sequence

from .constants import DEFAULT_OLLAMA_EMBEDDING_MODEL, embedding_dimension_for_model


def _resolve_embedding_dimension() -> int:
    """Determine the embedding dimension based on the configured model."""

    override = os.getenv("EMBEDDING_DIMENSION")
    if override:
        try:
            value = int(override)
            if value > 0:
                return value
        except ValueError:
            pass
    model_env = (
        os.getenv("LLM__EMBEDDING_MODEL")
        or os.getenv("LLM_EMBEDDING_MODEL")
        or os.getenv("EMBEDDING_MODEL")
    )
    model_name = model_env or DEFAULT_OLLAMA_EMBEDDING_MODEL
    return embedding_dimension_for_model(model_name)


# Central place to configure the expected embedding dimensionality that the
# pgvector column is created with. Downstream embedders normalise their output to
# this length to guarantee compatibility with persistence and similarity search.
EMBEDDING_DIMENSION = _resolve_embedding_dimension()


class EmbeddingClient(ABC):
    """Interface for text embedding providers."""

    model_name: str

    @abstractmethod
    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Return embeddings for the provided texts."""


__all__ = ["EmbeddingClient", "EMBEDDING_DIMENSION"]
