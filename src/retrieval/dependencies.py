"""Dependencies for retrieval module."""
from __future__ import annotations

from functools import lru_cache

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..dependencies import get_db_session, get_settings
from ..infrastructure.embeddings.local import LocalEmbeddingClient
from ..infrastructure.llm.ollama import OllamaClient
from ..infrastructure.llm.vllm import VLLMClient
from ..infrastructure.repositories.conversation_repo import ConversationRepository
from ..infrastructure.vectorstore.graphrag_engine import GraphRAGQueryEngine
from ..infrastructure.vectorstore.pgvector import PGVectorStore
from .service import RetrievalService
from .strategies.graphrag import GraphRAGStrategy
from .strategies.rag import RAGStrategy


@lru_cache()
def _get_graph_rag_engine() -> GraphRAGQueryEngine:
    settings = get_settings()
    return GraphRAGQueryEngine(settings.graphrag)


async def get_retrieval_service(session: AsyncSession = Depends(get_db_session)) -> RetrievalService:
    settings = get_settings()
    embedder = LocalEmbeddingClient()
    vector_store = PGVectorStore(session, embedder)
    llm_client = OllamaClient(settings) if settings.llm.provider == "ollama" else VLLMClient(settings)
    rag_strategy = RAGStrategy(vector_store, llm_client)
    graphrag_strategy = GraphRAGStrategy(_get_graph_rag_engine())
    repo = ConversationRepository(session)
    return RetrievalService(repo, rag_strategy, graphrag_strategy)


__all__ = ["get_retrieval_service"]
