"""Milvus client placeholder implementation."""
from __future__ import annotations

from collections.abc import Sequence

from ...config import Settings
from .base import VectorStoreClient


class MilvusVectorStore(VectorStoreClient):
    """Simple in-memory fallback for Milvus queries."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._cache: list[str] = []

    async def similarity_search(self, query: str, *, k: int = 5) -> Sequence[str]:
        # Placeholder: return stored cache or echo query.
        return self._cache[:k] if self._cache else [f"Relevant context for: {query}"]

    def seed(self, chunks: Sequence[str]) -> None:
        self._cache = list(chunks)


__all__ = ["MilvusVectorStore"]
