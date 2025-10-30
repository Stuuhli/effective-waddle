"""Retrieval service orchestrating strategy selection."""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from time import perf_counter
from typing import Iterable

from fastapi import HTTPException, status

from ..infrastructure.repositories.conversation_repo import ConversationRepository
from .constants import DEFAULT_CHAT_TITLE, GRAPH_RAG_MODE_ALIAS
from .stream import StreamEvent
from .strategies.base import RetrievalContext, RetrievalStrategy

LOGGER = logging.getLogger(__name__)


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

    async def get_messages(self, conversation_id: str, user_id: str):
        conversation = await self.conversation_repo.get_conversation(conversation_id, user_id)
        if conversation is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        return await self.conversation_repo.list_messages(conversation_id)

    async def delete_session(self, conversation_id: str, user_id: str) -> None:
        conversation = await self.conversation_repo.get_conversation(conversation_id, user_id)
        if conversation is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        await self.conversation_repo.delete_conversation(conversation)

    def _resolve_strategy(self, roles: Iterable[str], mode: str | None) -> RetrievalStrategy:
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
    ) -> AsyncGenerator[bytes, None]:
        conversation = await self.conversation_repo.get_conversation(conversation_id, user_id)
        if conversation is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

        if not conversation.title:
            conversation.title = self._derive_title(query)

        await self.conversation_repo.add_message(conversation_id, "user", query)
        await self.conversation_repo.commit()

        strategy = self._resolve_strategy(roles, mode)
        context = RetrievalContext(conversation_id=conversation_id, query=query, mode=mode, user_roles=roles)

        async def _stream() -> AsyncGenerator[bytes, None]:
            LOGGER.info(
                "Chat stream started | conversation=%s user=%s mode=%s roles=%s",
                conversation_id,
                user_id,
                mode or "default",
                roles,
            )
            stream_start = perf_counter()
            tokens: list[str] = []
            context_chunks: list[dict[str, object]] = []
            citation_items: list[dict[str, object]] = []
            try:
                async for event in strategy.run(context):
                    if event.type == "status":
                        LOGGER.info(
                            "Chat event status | conversation=%s stage=%s message=%s",
                            conversation_id,
                            event.data.get("stage"),
                            event.data.get("message"),
                        )
                    elif event.type == "context":
                        chunks = event.data.get("chunks") or []
                        if isinstance(chunks, list):
                            context_chunks = [chunk for chunk in chunks if isinstance(chunk, dict)]
                        LOGGER.info(
                            "Chat event context | conversation=%s chunks=%d",
                            conversation_id,
                            len(chunks),
                        )
                    elif event.type == "citations":
                        citations = event.data.get("citations") or []
                        if isinstance(citations, list):
                            citation_items = [ citation for citation in citations if isinstance(citation, dict)]
                        LOGGER.info(
                            "Chat event citations | conversation=%s citations=%d",
                            conversation_id,
                            len(citations),
                        )
                    elif event.type == "token":
                        LOGGER.debug(
                            "Chat event token | conversation=%s size=%d",
                            conversation_id,
                            len(event.data.get("text") or ""),
                        )
                    if event.type == "token":
                        text = event.data.get("text")
                        if isinstance(text, str):
                            tokens.append(text)
                    yield self._encode_event(event)
            except Exception as exc:  # pragma: no cover - streaming failure
                error_message = str(exc) or "LLM request failed."
                LOGGER.exception("Failed to stream chat response for %s", conversation_id, exc_info=exc)
                yield self._encode_event(StreamEvent.status(stage="error", message=error_message))
                yield self._encode_event(StreamEvent.error(message=error_message))
                return
            finally:
                response_body = "".join(tokens).strip()
                elapsed = perf_counter() - stream_start
                LOGGER.info(
                    "Chat stream finished | conversation=%s duration=%.2fs tokens=%d characters=%d",
                    conversation_id,
                    elapsed,
                    len(tokens),
                    len(response_body),
                )
                if response_body:
                    await self.conversation_repo.add_message(
                        conversation_id,
                        "assistant",
                        response_body,
                        context=context_chunks or None,
                        citations=citation_items or None,
                    )
                    await self.conversation_repo.commit()

        return _stream()

    @staticmethod
    def _encode_event(event: StreamEvent) -> bytes:
        payload = json.dumps(event.as_dict(), ensure_ascii=False)
        return (payload + "\n").encode("utf-8")

    @staticmethod
    def _derive_title(query: str, *, max_length: int = 60) -> str:
        cleaned = " ".join(query.strip().split())
        if not cleaned:
            return DEFAULT_CHAT_TITLE
        if len(cleaned) <= max_length:
            return cleaned
        return cleaned[: max_length - 1].rstrip() + "…"


__all__ = ["RetrievalService"]
