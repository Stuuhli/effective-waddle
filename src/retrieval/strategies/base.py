"""Strategy interfaces for retrieval pipelines."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Iterable, Protocol


@dataclass
class RetrievalContext:
    """Context passed to retrieval strategies."""

    conversation_id: str
    query: str
    mode: str | None
    user_roles: Iterable[str]


class RetrievalStrategy(ABC):
    """Interface for retrieval strategies."""

    @abstractmethod
    async def run(self, context: RetrievalContext) -> AsyncGenerator[str, None]:
        """Return a streaming generator of response chunks."""


__all__ = ["RetrievalStrategy", "RetrievalContext"]
