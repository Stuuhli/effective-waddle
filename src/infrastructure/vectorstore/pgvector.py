"""Vector store backed by PostgreSQL using pgvector."""
from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..embeddings.base import EmbeddingClient
from ..database import Chunk
from .base import VectorStoreClient


class PGVectorStore(VectorStoreClient):
    """Execute similarity search queries against pgvector backed embeddings."""

    def __init__(self, session: AsyncSession, embedder: EmbeddingClient) -> None:
        self.session = session
        self.embedder = embedder

    async def similarity_search(self, query: str, *, k: int = 5) -> Sequence[str]:
        query_vector = (await self.embedder.embed([query]))[0]
        stmt = (
            select(Chunk.content)
            .where(Chunk.embedding.isnot(None))
            .order_by(Chunk.embedding.cosine_distance(query_vector))
            .limit(k)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars())


__all__ = ["PGVectorStore"]
