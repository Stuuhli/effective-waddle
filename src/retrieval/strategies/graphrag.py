"""GraphRAG based retrieval strategy."""
from __future__ import annotations

from collections.abc import AsyncGenerator

from ...infrastructure.vectorstore.graphrag_engine import GraphRAGQueryEngine
from ..stream import StreamEvent
from .base import RetrievalContext, RetrievalStrategy


class GraphRAGStrategy(RetrievalStrategy):
    """Strategy delegating to the GraphRAG query engine."""

    def __init__(self, engine: GraphRAGQueryEngine) -> None:
        self.engine = engine

    async def run(self, context: RetrievalContext) -> AsyncGenerator[StreamEvent, None]:
        yield StreamEvent.status(stage="retrieving", message="Querying knowledge graph…")
        result = await self.engine.query(context.query, method=context.mode)
        context_payload = [
            {
                "label": "[G1]",
                "chunk_id": None,
                "document_id": None,
                "snippet": f"GraphRAG context prepared using '{result.method}' mode.",
                "score": None,
                "metadata": {"graph_context": result.context},
                "document_title": f"GraphRAG ({result.method})",
                "document_metadata": {},
            }
        ]
        yield StreamEvent.context(chunks=context_payload)
        yield StreamEvent.status(stage="generating", message="Generating response…")
        if result.text:
            yield StreamEvent.token(text=result.text)
        yield StreamEvent.status(stage="complete", message="Response ready.")
        yield StreamEvent.done()


__all__ = ["GraphRAGStrategy"]
