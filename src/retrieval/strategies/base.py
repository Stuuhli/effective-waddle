"""Strategy interfaces for retrieval pipelines."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Iterable

from ..stream import StreamEvent

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
    async def run(self, context: RetrievalContext) -> AsyncGenerator[StreamEvent, None]:
        """Return a streaming generator of response events."""


__all__ = ["RetrievalStrategy", "RetrievalContext"]
