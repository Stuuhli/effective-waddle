"""Vector-store backed retrieval strategy."""
from __future__ import annotations

import json
from collections.abc import AsyncGenerator, Mapping, Sequence
from typing import Any

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
        formatted_context = self._format_contexts(docs)
        async for chunk in self.llm.generate(context.query, context=formatted_context):
            yield chunk

    def _format_contexts(self, docs: Sequence[Any]) -> list[str]:
        contexts: list[str] = []
        for doc in docs:
            if isinstance(doc, Mapping):
                content = doc.get("content", "")
                metadata = doc.get("metadata") or {}
                if metadata:
                    metadata_blob = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
                    contexts.append(f"{content}\n\nMetadata: {metadata_blob}".strip())
                else:
                    contexts.append(str(content))
            else:
                contexts.append(str(doc))
        return contexts


__all__ = ["RAGStrategy"]
