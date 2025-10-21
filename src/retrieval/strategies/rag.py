"""Vector-store backed retrieval strategy."""
from __future__ import annotations

from collections.abc import AsyncGenerator

from ...infrastructure.llm.base import LLMClient
from ...infrastructure.vectorstore.base import VectorStoreClient
from .base import RetrievalContext, RetrievalStrategy


class RAGStrategy(RetrievalStrategy):
    """Simple retrieval augmented generation strategy."""

    def __init__(self, vector_store: VectorStoreClient, llm: LLMClient) -> None:
        self.vector_store = vector_store
        self.llm = llm

    async def run(self, context: RetrievalContext) -> AsyncGenerator[str, None]:
        docs = await self.vector_store.similarity_search(context.query)
        async for chunk in self.llm.generate(context.query, context=docs):
            yield chunk


__all__ = ["RAGStrategy"]
