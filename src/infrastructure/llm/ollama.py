"""Ollama backed LLM client with streaming responses."""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator, Sequence
from time import perf_counter
from typing import Any

import httpx

from ...config import Settings
from .base import LLMClient

_SYSTEM_PROMPT = (
    "You are a retrieval-augmented assistant. When context is provided, ground every factual statement in the "
    "supporting snippets. Cite sources inline using bracketed references such as [1] or [2]. If the answer cannot "
    "be derived from the context, explain that you cannot find the information. Provide clear, actionable responses."
)

LOGGER = logging.getLogger(__name__)


class OllamaClient(LLMClient):
    """Stream completions from an Ollama server."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._host = settings.llm.ollama_host.rstrip("/")
        self._model = settings.llm.ollama_model
        self._timeout = settings.llm.request_timeout

    async def generate(self, prompt: str, *, context: Sequence[str] | None = None) -> AsyncGenerator[str, None]:
        """Generate a completion using the configured Ollama model."""

        payload = {
            "model": self._model,
            "prompt": self._build_prompt(prompt, context),
            "stream": True,
            "options": {
                "temperature": 0.1,
                "top_p": 0.9,
            },
        }
        url = f"{self._host}/api/generate"
        timeout = httpx.Timeout(self._timeout, connect=self._timeout, read=None, write=self._timeout)
        LOGGER.info(
            "Ollama request started | model=%s context_chunks=%d prompt_chars=%d",
            self._model,
            len(context or []),
            len(prompt),
        )
        start_time = perf_counter()
        chunk_count = 0
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("POST", url, json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        chunk = self._parse_chunk(line)
                        if chunk:
                            chunk_count += 1
                            LOGGER.debug(
                                "Ollama streamed chunk | model=%s length=%d",
                                self._model,
                                len(chunk),
                            )
                            yield chunk
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"Ollama generation failed with status {exc.response.status_code}: {exc.response.text}"
            ) from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Failed to reach Ollama server at {url}: {exc}") from exc
        finally:
            duration = perf_counter() - start_time
            LOGGER.info(
                "Ollama request finished | model=%s duration=%.2fs chunks=%d",
                self._model,
                duration,
                chunk_count,
            )

    def _build_prompt(self, prompt: str, context: Sequence[str] | None) -> str:
        context_section = ""
        if context:
            joined = "\n\n".join(context)
            context_section = f"Context:\n{joined}\n\n"
        return f"{_SYSTEM_PROMPT}\n\n{context_section}Question:\n{prompt}\n\nAnswer:"

    @staticmethod
    def _parse_chunk(payload: str) -> str:
        try:
            data: dict[str, Any] = json.loads(payload)
        except json.JSONDecodeError:
            return ""
        if data.get("done"):
            return ""
        chunk = data.get("response")
        return str(chunk) if chunk else ""


__all__ = ["OllamaClient"]
