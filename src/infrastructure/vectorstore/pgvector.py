"""Vector store backed by PostgreSQL using pgvector."""
from __future__ import annotations

import logging
from collections.abc import Sequence
from time import perf_counter
from typing import Any, Mapping

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..embeddings.base import EmbeddingClient
from ..database import Chunk, Document
from .base import VectorStoreClient

LOGGER = logging.getLogger(__name__)


class PGVectorStore(VectorStoreClient):
    """Execute similarity search queries against pgvector backed embeddings."""

    def __init__(self, session: AsyncSession, embedder: EmbeddingClient) -> None:
        self.session = session
        self.embedder = embedder

    async def similarity_search(self, query: str, *, k: int = 5) -> Sequence[Mapping[str, Any]]:
        overall_start = perf_counter()
        embed_start = overall_start
        query_vector = (await self.embedder.embed([query]))[0]
        embed_time = perf_counter() - embed_start
        distance = Chunk.embedding.cosine_distance(query_vector).label("distance")
        sql_start = perf_counter()
        stmt = (
            select(
                Chunk.id,
                Chunk.document_id,
                Chunk.content,
                Chunk.metadata_json,
                Document.title,
                Document.metadata_json,
                distance,
            )
            .join(Document, Document.id == Chunk.document_id)
            .where(Chunk.embedding.isnot(None))
            .order_by(distance)
            .limit(k)
        )
        result = await self.session.execute(stmt)
        rows = result.all()
        sql_time = perf_counter() - sql_start
        documents: list[Mapping[str, Any]] = []
        for (
            chunk_id,
            document_id,
            content,
            chunk_metadata,
            document_title,
            document_metadata,
            distance_value,
        ) in rows:
            score: float | None = None
            if distance_value is not None:
                try:
                    score = max(0.0, 1.0 - float(distance_value))
                except (TypeError, ValueError):
                    score = None
            documents.append(
                {
                    "chunk_id": chunk_id,
                    "document_id": document_id,
                    "content": content,
                    "metadata": chunk_metadata or {},
                    "document_title": document_title,
                    "document_metadata": document_metadata or {},
                    "score": score,
                }
            )
        total_time = perf_counter() - overall_start
        LOGGER.info(
            "PGVectorStore search | embed_model=%s k=%s results=%d embed_time=%.3fs sql_time=%.3fs total_time=%.3fs",
            getattr(self.embedder, "model_name", None),
            k,
            len(documents),
            embed_time,
            sql_time,
            total_time,
        )
        return documents


__all__ = ["PGVectorStore"]
