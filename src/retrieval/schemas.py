"""Schemas for retrieval/chat endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ChatSessionCreate(BaseModel):
    title: Optional[str] = Field(default=None, description="Optional session title")


class ChatSessionResponse(BaseModel):
    id: str
    title: Optional[str]
    created_at: datetime


class ChatMessageRequest(BaseModel):
    query: str
    mode: Optional[str] = None


class ChatMessageResponse(BaseModel):
    role: str
    content: str
    created_at: datetime


__all__ = [
    "ChatSessionCreate",
    "ChatSessionResponse",
    "ChatMessageRequest",
    "ChatMessageResponse",
]
