"""Retrieval strategy selection tests."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.infrastructure.repositories.conversation_repo import ConversationRepository
from src.infrastructure.repositories.user_repo import UserRepository
from src.retrieval.dependencies import get_retrieval_service
from src.retrieval.service import RetrievalService
from src.retrieval.strategies.base import RetrievalContext, RetrievalStrategy


class RecordingStrategy(RetrievalStrategy):
    """Record invocations and return a labelled response."""

    def __init__(self, label: str) -> None:
        self.label = label
        self.calls: list[RetrievalContext] = []

    async def run(self, context: RetrievalContext) -> AsyncGenerator[str, None]:
        self.calls.append(context)
        yield f"{self.label}:{context.query}"


def _install_retrieval_override(
    app: FastAPI,
    session_factory: async_sessionmaker,
    rag_strategy: RecordingStrategy,
    graphrag_strategy: RecordingStrategy,
) -> None:
    async def override() -> AsyncGenerator[RetrievalService, None]:
        async with session_factory() as session:
            repo = ConversationRepository(session)
            service = RetrievalService(repo, rag_strategy, graphrag_strategy)
            yield service

    app.dependency_overrides[get_retrieval_service] = override


def test_default_role_uses_rag_strategy(app: FastAPI, session_factory: async_sessionmaker) -> None:
    rag_strategy = RecordingStrategy("rag")
    graphrag_strategy = RecordingStrategy("graphrag")
    _install_retrieval_override(app, session_factory, rag_strategy, graphrag_strategy)

    async def _run() -> None:
        async with app.router.lifespan_context(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                payload = {"email": "carol@example.com", "password": "AnotherSecret3!", "full_name": "Carol"}
                register = await client.post("/auth/register", json=payload)
                assert register.status_code == 201
                login = await client.post(
                    "/auth/login", json={"email": payload["email"], "password": payload["password"]}
                )
                assert login.status_code == 200
                token = login.json()["access_token"]
                headers = {"Authorization": f"Bearer {token}"}

                session_response = await client.post("/chat/sessions", json={"title": "Carol Session"}, headers=headers)
                assert session_response.status_code == 201
                session_id = session_response.json()["id"]

                message_response = await client.post(
                    f"/chat/{session_id}/messages",
                    json={"query": "Hello", "mode": None},
                    headers=headers,
                )
                assert message_response.status_code == 200
                chunks: list[str] = []
                async for piece in message_response.aiter_text():
                    chunks.append(piece)
                body = "".join(chunks)
                assert body.startswith("rag:")
                assert len(rag_strategy.calls) == 1
                assert not graphrag_strategy.calls

    try:
        asyncio.run(_run())
    finally:
        app.dependency_overrides.pop(get_retrieval_service, None)


def test_graphrag_role_triggers_graphrag_strategy(
    app: FastAPI, session_factory: async_sessionmaker
) -> None:
    rag_strategy = RecordingStrategy("rag")
    graphrag_strategy = RecordingStrategy("graphrag")
    _install_retrieval_override(app, session_factory, rag_strategy, graphrag_strategy)

    async def _run() -> None:
        async with app.router.lifespan_context(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                payload = {"email": "dana@example.com", "password": "DanaSecret4!", "full_name": "Dana"}
                register = await client.post("/auth/register", json=payload)
                assert register.status_code == 201
                login = await client.post(
                    "/auth/login", json={"email": payload["email"], "password": payload["password"]}
                )
                assert login.status_code == 200
                token = login.json()["access_token"]
                headers = {"Authorization": f"Bearer {token}"}

                async with session_factory() as session:
                    user_repo = UserRepository(session)
                    user = await user_repo.get_by_email(payload["email"])
                    assert user is not None
                    graph_role = await user_repo.ensure_role("graphrag", "GraphRAG access")
                    await user_repo.assign_role(user, graph_role)

                session_response = await client.post("/chat/sessions", json={"title": "Dana Session"}, headers=headers)
                assert session_response.status_code == 201
                session_id = session_response.json()["id"]

                message_response = await client.post(
                    f"/chat/{session_id}/messages",
                    json={"query": "Graph question", "mode": None},
                    headers=headers,
                )
                assert message_response.status_code == 200
                chunks: list[str] = []
                async for piece in message_response.aiter_text():
                    chunks.append(piece)
                body = "".join(chunks)
                assert body.startswith("graphrag:")
                assert not rag_strategy.calls
                assert len(graphrag_strategy.calls) == 1

    try:
        asyncio.run(_run())
    finally:
        app.dependency_overrides.pop(get_retrieval_service, None)
