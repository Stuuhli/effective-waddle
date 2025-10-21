"""LLM client base classes."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Sequence


class LLMClient(ABC):
    """Abstract LLM interface supporting streaming responses."""

    @abstractmethod
    async def generate(self, prompt: str, *, context: Sequence[str] | None = None) -> AsyncGenerator[str, None]:
        """Yield response chunks for the given prompt."""


__all__ = ["LLMClient"]
