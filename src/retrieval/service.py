"""Retrieval service orchestrating strategy selection."""
from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import HTTPException, status

from ..infrastructure.repositories.conversation_repo import ConversationRepository
from .constants import GRAPH_RAG_MODE_ALIAS
from .strategies.base import RetrievalContext, RetrievalStrategy


class RetrievalService:
    """Apply retrieval strategies based on user roles/policies."""

    def __init__(
        self,
        conversation_repo: ConversationRepository,
        rag_strategy: RetrievalStrategy,
        graphrag_strategy: RetrievalStrategy,
    ) -> None:
        self.conversation_repo = conversation_repo
        self.rag_strategy = rag_strategy
        self.graphrag_strategy = graphrag_strategy

    async def create_session(self, user_id: str, title: str | None = None):
        return await self.conversation_repo.create_conversation(user_id=user_id, title=title)

    async def list_sessions(self, user_id: str):
        sessions = await self.conversation_repo.filter_by(user_id=user_id)
        return list(sessions)

    def _resolve_strategy(self, roles: list[str], mode: str | None) -> RetrievalStrategy:
        normalized_mode = mode.lower() if mode else None
        if normalized_mode == GRAPH_RAG_MODE_ALIAS:
            return self.graphrag_strategy
        if GRAPH_RAG_MODE_ALIAS in {role.lower() for role in roles}:
            return self.graphrag_strategy
        return self.rag_strategy

    async def send_message(
        self,
        *,
        conversation_id: str,
        user_id: str,
        query: str,
        roles: list[str],
        mode: str | None,
    ) -> AsyncGenerator[str, None]:
        conversation = await self.conversation_repo.get_conversation(conversation_id, user_id)
        if conversation is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        await self.conversation_repo.add_message(conversation_id, "user", query)

        strategy = self._resolve_strategy(roles, mode)
        context = RetrievalContext(conversation_id=conversation_id, query=query, mode=mode, user_roles=roles)
        buffer: list[str] = []
        async for chunk in strategy.run(context):
            buffer.append(chunk)
            yield chunk
        response_text = "".join(buffer)
        await self.conversation_repo.add_message(conversation_id, "assistant", response_text)


__all__ = ["RetrievalService"]
