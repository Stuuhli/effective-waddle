from __future__ import annotations

from collections.abc import Iterator
import os
from pathlib import Path
import sys
import tempfile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import Session, sessionmaker

from src import dependencies
from src.config import Settings
from src.infrastructure.database import Base

import src.auth.dependencies as auth_dependencies
import src.auth.user_manager as auth_user_manager
import src.retrieval.dependencies as retrieval_dependencies
import src.ingestion.dependencies as ingestion_dependencies


class AsyncSessionWrapper:
    """Minimal async-compatible wrapper around a synchronous SQLAlchemy session."""

    def __init__(self, sync_session: Session) -> None:
        self._sync = sync_session

    def add(self, instance: object) -> None:
        self._sync.add(instance)

    async def execute(self, statement, *args, **kwargs):
        return self._sync.execute(statement, *args, **kwargs)

    async def commit(self) -> None:
        self._sync.commit()

    async def flush(self) -> None:
        self._sync.flush()

    async def refresh(self, instance: object) -> None:
        self._sync.refresh(instance)

    async def delete(self, instance: object) -> None:
        self._sync.delete(instance)

    async def close(self) -> None:
        self._sync.close()

    def __getattr__(self, item: str):
        return getattr(self._sync, item)


class AsyncSessionContext:
    def __init__(self, factory: sessionmaker) -> None:
        self._factory = factory
        self._sync: Session | None = None

    async def __aenter__(self) -> AsyncSessionWrapper:
        self._sync = self._factory()
        return AsyncSessionWrapper(self._sync)

    async def __aexit__(self, exc_type, exc, tb) -> None:
        assert self._sync is not None
        if exc_type is not None:
            self._sync.rollback()
        self._sync.close()


class AsyncSessionFactory:
    def __init__(self, factory: sessionmaker) -> None:
        self._factory = factory

    def __call__(self) -> AsyncSessionContext:
        return AsyncSessionContext(self._factory)


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> Iterator[FastAPI]:
    """Provide a FastAPI app wired to an in-memory SQLite database."""

    if hasattr(dependencies.get_settings, "cache_clear"):
        dependencies.get_settings.cache_clear()

    fd, db_path = tempfile.mkstemp(prefix="rag_platform_tests_", suffix=".db")
    os.close(fd)
    engine = create_engine(
        f"sqlite:///{db_path}",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sync_session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session_factory = AsyncSessionFactory(sync_session_factory)

    settings = Settings()
    settings.fastapi.secret_key = "test-secret"

    async def _get_db_session():
        async with session_factory() as session:
            yield session

    def _get_session_factory() -> AsyncSessionFactory:
        return session_factory

    def _get_settings() -> Settings:
        return settings

    monkeypatch.setattr(dependencies, "get_db_session", _get_db_session)
    monkeypatch.setattr(dependencies, "get_session_factory", _get_session_factory)
    monkeypatch.setattr(dependencies, "get_settings", _get_settings)
    monkeypatch.setattr(auth_dependencies, "get_settings", _get_settings)
    monkeypatch.setattr(auth_user_manager, "get_db_session", _get_db_session)
    monkeypatch.setattr(auth_user_manager, "get_settings", _get_settings)
    monkeypatch.setattr(retrieval_dependencies, "get_settings", _get_settings)
    monkeypatch.setattr(ingestion_dependencies, "get_db_session", _get_db_session)

    from src.main import create_app

    app = create_app()
    app.state._session_factory = session_factory  # type: ignore[attr-defined]

    try:
        yield app
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
        try:
            os.remove(db_path)
        except OSError:
            pass


@pytest.fixture
def session_factory(app: FastAPI) -> AsyncSessionFactory:
    """Expose the session factory for direct database access in tests."""

    return app.state._session_factory  # type: ignore[attr-defined]
