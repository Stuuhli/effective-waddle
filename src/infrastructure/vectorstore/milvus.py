"""Milvus client placeholder implementation."""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Mapping

from ...config import Settings
from .base import VectorStoreClient


class MilvusVectorStore(VectorStoreClient):
    """Simple in-memory fallback for Milvus queries."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._cache: list[dict[str, Any]] = []

    async def similarity_search(self, query: str, *, k: int = 5) -> Sequence[Mapping[str, Any]]:
        # Placeholder: return stored cache or echo query.
        if self._cache:
            return self._cache[:k]
        return [{"content": f"Relevant context for: {query}", "metadata": {}}]

    def seed(self, chunks: Sequence[Any]) -> None:
        formatted: list[dict[str, Any]] = []
        for chunk in chunks:
            if isinstance(chunk, Mapping):
                metadata = chunk.get("metadata") or {}
                formatted.append({"content": str(chunk.get("content", "")), "metadata": dict(metadata)})
            else:
                formatted.append({"content": str(chunk), "metadata": {}})
        self._cache = formatted


__all__ = ["MilvusVectorStore"]
