"""vLLM client placeholder."""
from __future__ import annotations

from collections.abc import AsyncGenerator, Sequence

from ...config import Settings
from .base import LLMClient


class VLLMClient(LLMClient):
    """Mock vLLM client that echoes prompts."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def generate(self, prompt: str, *, context: Sequence[str] | None = None) -> AsyncGenerator[str, None]:
        combined = "\n".join(context or [])
        yield f"[vLLM:{self.settings.llm.vllm_model}] {prompt}\n{combined}".strip()


__all__ = ["VLLMClient"]
