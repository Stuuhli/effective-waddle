"""Common dependency helpers."""
from __future__ import annotations

from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings, load_settings
from .infrastructure.database import AsyncSessionFactory, configure_engine


@lru_cache()
def get_settings() -> Settings:
    """Return cached settings instance."""

    return load_settings()


def get_session_factory() -> AsyncSessionFactory:
    """Initialise the session factory based on configuration."""

    settings = get_settings()
    return configure_engine(settings)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an AsyncSession for request scope."""

    session_factory = get_session_factory()
    async with session_factory() as session:  # type: ignore[call-arg]
        yield session
