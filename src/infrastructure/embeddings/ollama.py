"""Embedding client backed by the Ollama embeddings API."""
from __future__ import annotations

import logging
from collections.abc import Sequence

from .base import EMBEDDING_DIMENSION, EmbeddingClient

LOGGER = logging.getLogger(__name__)


def _normalise_dimension(vector: Sequence[float], dimension: int) -> list[float]:
    """Resize embeddings to match the configured pgvector dimension."""

    values = list(vector)
    current = len(values)
    if current == dimension:
        return values
    if current > dimension:
        LOGGER.debug("Truncating embedding from %s to %s dimensions", current, dimension)
        return values[:dimension]
    LOGGER.debug("Padding embedding from %s to %s dimensions", current, dimension)
    return values + [0.0] * (dimension - current)


class OllamaEmbeddingClient(EmbeddingClient):
    """Generate embeddings via an Ollama server."""

    def __init__(
        self,
        *,
        host: str,
        model_name: str,
        request_timeout: int,
        dimension: int = EMBEDDING_DIMENSION,
    ) -> None:
        self._host = host
        self.model_name = model_name
        self._timeout = request_timeout
        self._dimension = dimension
        self._client: "AsyncClient | None" = None

    async def _ensure_client(self) -> "AsyncClient":
        if self._client is not None:
            return self._client
        try:
            from ollama import AsyncClient
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("The 'ollama' package is required to use Ollama embeddings") from exc
        self._client = AsyncClient(host=self._host, timeout=self._timeout)
        return self._client

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        client = await self._ensure_client()
        embeddings: list[list[float]] = []
        for text in texts:
            response = await client.embeddings(model=self.model_name, prompt=text)
            vector = response.get("embedding")
            if not isinstance(vector, Sequence):
                raise RuntimeError("Unexpected response format from Ollama embeddings endpoint")
            embeddings.append(_normalise_dimension(vector, self._dimension))
        return embeddings


__all__ = ["OllamaEmbeddingClient"]
