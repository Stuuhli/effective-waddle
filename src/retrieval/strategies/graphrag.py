"""GraphRAG based retrieval strategy."""
from __future__ import annotations

from collections.abc import AsyncGenerator

from ...infrastructure.vectorstore.graphrag_engine import GraphRAGQueryEngine
from .base import RetrievalContext, RetrievalStrategy


class GraphRAGStrategy(RetrievalStrategy):
    """Strategy delegating to the GraphRAG query engine."""

    def __init__(self, engine: GraphRAGQueryEngine) -> None:
        self.engine = engine

    async def run(self, context: RetrievalContext) -> AsyncGenerator[str, None]:
        result = await self.engine.query(context.query, method=context.mode)
        yield result.text


__all__ = ["GraphRAGStrategy"]
