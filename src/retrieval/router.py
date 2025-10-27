"""Retrieval endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse

from ..auth.dependencies import get_current_user
from ..infrastructure.database import User
from .dependencies import get_retrieval_service
from .schemas import ChatMessageRequest, ChatMessageResponse, ChatSessionCreate, ChatSessionResponse
from .service import RetrievalService

router = APIRouter()


@router.post("/sessions", response_model=ChatSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    payload: ChatSessionCreate,
    user: User = Depends(get_current_user),
    service: RetrievalService = Depends(get_retrieval_service),
) -> ChatSessionResponse:
    session = await service.create_session(user.id, payload.title)
    return ChatSessionResponse(id=session.id, title=session.title, created_at=session.created_at)


@router.get("/sessions", response_model=list[ChatSessionResponse])
async def list_sessions(
    user: User = Depends(get_current_user),
    service: RetrievalService = Depends(get_retrieval_service),
) -> list[ChatSessionResponse]:
    sessions = await service.list_sessions(user.id)
    return [ChatSessionResponse(id=conv.id, title=conv.title, created_at=conv.created_at) for conv in sessions]

@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: str,
    user: User = Depends(get_current_user),
    service: RetrievalService = Depends(get_retrieval_service),
) -> None:
    await service.delete_session(session_id, user.id)

@router.get("/{session_id}/messages", response_model=list[ChatMessageResponse])
async def list_messages(
    session_id: str,
    user: User = Depends(get_current_user),
    service: RetrievalService = Depends(get_retrieval_service),
) -> list[ChatMessageResponse]:
    messages = await service.get_messages(session_id, user.id)
    return [
        ChatMessageResponse(role=msg.role, content=msg.content, created_at=msg.created_at)
        for msg in messages
    ]


@router.post("/{session_id}/messages", response_class=StreamingResponse)
async def send_message(
    session_id: str,
    payload: ChatMessageRequest,
    user: User = Depends(get_current_user),
    service: RetrievalService = Depends(get_retrieval_service),
) -> StreamingResponse:
    stream = await service.send_message(
        conversation_id=session_id,
        user_id=user.id,
        query=payload.query,
        roles=[role.name for role in user.roles],
        mode=payload.mode,
    )
    response = StreamingResponse(
        stream,
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store"},
    )
    response.enable_compression = False
    return response


__all__ = ["router"]
