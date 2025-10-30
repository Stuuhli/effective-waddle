"""Conversation repository implementation."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import Conversation, Message
from .base import AsyncRepository


class ConversationRepository(AsyncRepository[Conversation]):
    """Manage chat conversations and messages."""

    model = Conversation

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def create_conversation(self, user_id: str, title: str | None = None) -> Conversation:
        conversation = Conversation(user_id=user_id, title=title)
        await self.add(conversation)
        await self.commit()
        await self.session.refresh(conversation)
        return conversation

    async def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        *,
        context: list[dict[str, object]] | None = None,
        citations: list[dict[str, object]] | None = None,
    ) -> Message:
        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            context_json=context,
            citations_json=citations,
        )
        self.session.add(message)
        await self.session.flush()
        await self.session.refresh(message)
        return message

    async def list_messages(self, conversation_id: str) -> list[Message]:
        stmt = select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at)
        result = await self.session.execute(stmt)
        return list(result.scalars())

    async def get_conversation(self, conversation_id: str, user_id: str) -> Optional[Conversation]:
        stmt = select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_conversation(self, conversation: Conversation) -> None:
        await self.delete(conversation)
        await self.commit()


__all__ = ["ConversationRepository"]
