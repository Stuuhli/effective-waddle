"""Retrieval endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse

from ..auth.dependencies import get_current_user
from .dependencies import get_retrieval_service
from .schemas import ChatMessageRequest, ChatSessionCreate, ChatSessionResponse
from .service import RetrievalService

router = APIRouter()


@router.post("/sessions", response_model=ChatSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    payload: ChatSessionCreate,
    user_info: tuple[str, list[str]] = Depends(get_current_user),
    service: RetrievalService = Depends(get_retrieval_service),
) -> ChatSessionResponse:
    session = await service.create_session(user_info[0], payload.title)
    return ChatSessionResponse(id=session.id, title=session.title, created_at=session.created_at)


@router.get("/sessions", response_model=list[ChatSessionResponse])
async def list_sessions(
    user_info: tuple[str, list[str]] = Depends(get_current_user),
    service: RetrievalService = Depends(get_retrieval_service),
) -> list[ChatSessionResponse]:
    sessions = await service.list_sessions(user_info[0])
    return [ChatSessionResponse(id=conv.id, title=conv.title, created_at=conv.created_at) for conv in sessions]


@router.post("/{session_id}/messages", response_class=StreamingResponse)
async def send_message(
    session_id: str,
    payload: ChatMessageRequest,
    user_info: tuple[str, list[str]] = Depends(get_current_user),
    service: RetrievalService = Depends(get_retrieval_service),
) -> StreamingResponse:
    stream = service.send_message(
        conversation_id=session_id,
        user_id=user_info[0],
        query=payload.query,
        roles=user_info[1],
        mode=payload.mode,
    )
    return StreamingResponse(stream, media_type="text/plain")


__all__ = ["router"]
