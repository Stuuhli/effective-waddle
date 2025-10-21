"""Deterministic local embedding generator used for development and testing."""
from __future__ import annotations

import asyncio
import hashlib
import math
import random
from collections.abc import Sequence

from .base import EMBEDDING_DIMENSION, EmbeddingClient


class LocalEmbeddingClient(EmbeddingClient):
    """Generate deterministic pseudo-embeddings for text."""

    def __init__(self, *, dimension: int = EMBEDDING_DIMENSION) -> None:
        self.dimension = dimension
        self.model_name = "local-deterministic-embedding"

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._embed_sync, texts)

    def _embed_sync(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed_single(text) for text in texts]

    def _embed_single(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        seed = int.from_bytes(digest[:8], "big", signed=False)
        rng = random.Random(seed)
        vector = [rng.uniform(-1.0, 1.0) for _ in range(self.dimension)]
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return [0.0 for _ in range(self.dimension)]
        return [value / norm for value in vector]


__all__ = ["LocalEmbeddingClient"]
