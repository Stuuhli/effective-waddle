"""Vector-store backed retrieval strategy."""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator, Mapping, Sequence
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from ...infrastructure.llm.base import LLMClient
from ...infrastructure.vectorstore.base import VectorStoreClient
from ..stream import StreamEvent
from .base import RetrievalContext, RetrievalStrategy

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class RetrievedChunk:
    """Structured representation of a retrieved chunk."""

    label: str
    chunk_id: str | None
    document_id: str | None
    content: str
    snippet: str
    score: float | None
    chunk_metadata: dict[str, Any]
    document_title: str | None
    document_metadata: dict[str, Any]

    def llm_block(self) -> str:
        metadata_blob = {
            "chunk": self.chunk_metadata,
            "document": self.document_metadata,
            "document_id": self.document_id,
            "chunk_id": self.chunk_id,
            "title": self.document_title,
            "score": self.score,
        }
        metadata_json = json.dumps(metadata_blob, ensure_ascii=False, sort_keys=True)
        return f"{self.label} {self.content}\nMetadata: {metadata_json}".strip()

    def context_payload(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "snippet": self.snippet,
            "score": self.score,
            "metadata": self.chunk_metadata,
            "document_title": self.document_title,
            "document_metadata": self.document_metadata,
        }

    def citation_payload(self) -> dict[str, Any]:
        source = self.chunk_metadata.get("source") or self.document_metadata.get("source_path")
        page = self.chunk_metadata.get("page") or self.chunk_metadata.get("page_number")
        return {
            "label": self.label,
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "document_title": self.document_title,
            "score": self.score,
            "source": source,
            "page": page,
        }


class RAGStrategy(RetrievalStrategy):
    """Retrieval augmented generation workflow backed by a vector store."""

    _SNIPPET_MAX_LENGTH = 280

    def __init__(self, vector_store: VectorStoreClient, llm: LLMClient) -> None:
        self.vector_store = vector_store
        self.llm = llm

    async def run(self, context: RetrievalContext) -> AsyncGenerator[StreamEvent, None]:
        yield StreamEvent.status(stage="retrieving", message="Retrieving relevant information…")
        retrieval_start = perf_counter()
        LOGGER.info(
            "RAGStrategy: retrieving context | conversation=%s query=%r",
            context.conversation_id,
            context.query,
        )
        documents = await self.vector_store.similarity_search(context.query)
        chunks = self._prepare_chunks(documents)
        retrieval_time = perf_counter() - retrieval_start
        LOGGER.info(
            "RAGStrategy: vector search finished | conversation=%s chunks=%d duration=%.3fs",
            context.conversation_id,
            len(chunks),
            retrieval_time,
        )

        if chunks:
            LOGGER.info(
                "RAGStrategy: context prepared | conversation=%s first_chunk_labels=%s",
                context.conversation_id,
                [chunk.label for chunk in chunks[:3]],
            )
            yield StreamEvent.status(
                stage="retrieved",
                message=f"Found {len(chunks)} relevant chunk{'s' if len(chunks) != 1 else ''}.",
            )
        else:
            LOGGER.info(
                "RAGStrategy: no chunks found | conversation=%s using model knowledge",
                context.conversation_id,
            )
            yield StreamEvent.status(
                stage="retrieved",
                message="No relevant documents found; responding with model knowledge.",
            )

        yield StreamEvent.context(chunks=[chunk.context_payload() for chunk in chunks])

        llm_context = [chunk.llm_block() for chunk in chunks] if chunks else None
        yield StreamEvent.status(stage="generating", message="Generating response…")
        LOGGER.info(
            "RAGStrategy: starting generation | conversation=%s context_chunks=%d",
            context.conversation_id,
            len(chunks),
        )
        generation_start = perf_counter()
        chunk_count = 0
        async for piece in self.llm.generate(context.query, context=llm_context):
            if piece:
                chunk_count += 1
                LOGGER.debug(
                    "RAGStrategy: streamed chunk | conversation=%s length=%d",
                    context.conversation_id,
                    len(piece),
                )
                yield StreamEvent.token(text=piece)
        generation_time = perf_counter() - generation_start
        LOGGER.info(
            "RAGStrategy: generation finished | conversation=%s duration=%.3fs chunks=%d",
            context.conversation_id,
            generation_time,
            chunk_count,
        )

        if chunks:
            yield StreamEvent.status(stage="citations", message="Adding citations…")
            yield StreamEvent.citations(citations=[chunk.citation_payload() for chunk in chunks])
            LOGGER.info(
                "RAGStrategy: citations prepared | conversation=%s citations=%d",
                context.conversation_id,
                len(chunks),
            )

        yield StreamEvent.status(stage="complete", message="Response ready.")
        yield StreamEvent.done()
        LOGGER.info("RAGStrategy: completed | conversation=%s", context.conversation_id)

    def _prepare_chunks(self, docs: Sequence[Any]) -> list[RetrievedChunk]:
        prepared: list[RetrievedChunk] = []
        for index, doc in enumerate(docs, start=1):
            if not isinstance(doc, Mapping):
                content = str(doc)
                metadata = {}
                document_meta = {}
                document_title = None
            else:
                content = str(doc.get("content", ""))
                metadata = doc.get("metadata") or {}
                document_meta = doc.get("document_metadata") or {}
                document_title = doc.get("document_title") or metadata.get("title") or document_meta.get("title")
            snippet = self._build_snippet(content)
            prepared.append(
                RetrievedChunk(
                    label=f"[{index}]",
                    chunk_id=str(doc.get("chunk_id")) if isinstance(doc, Mapping) and doc.get("chunk_id") else None,
                    document_id=str(doc.get("document_id"))
                    if isinstance(doc, Mapping) and doc.get("document_id") is not None
                    else None,
                    content=content,
                    snippet=snippet,
                    score=float(doc.get("score")) if isinstance(doc, Mapping) and doc.get("score") is not None else None,
                    chunk_metadata=dict(metadata),
                    document_title=document_title,
                    document_metadata=dict(document_meta),
                )
            )
        return prepared

    def _build_snippet(self, content: str) -> str:
        snippet = content.strip()
        if len(snippet) <= self._SNIPPET_MAX_LENGTH:
            return snippet
        return snippet[: self._SNIPPET_MAX_LENGTH].rstrip() + "…"


__all__ = ["RAGStrategy"]
