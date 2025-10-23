"""vLLM client streaming via OpenAI compatible REST API."""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator, Sequence
from time import perf_counter

import httpx

from ...config import Settings
from .base import LLMClient

_SYSTEM_PROMPT = (
    "You are a retrieval-augmented assistant. Use the provided context snippets to answer questions and include "
    "inline citations like [1], [2] that reference the supporting snippets. If the answer is absent from the context, "
    "acknowledge the gap instead of guessing."
)

LOGGER = logging.getLogger(__name__)


class VLLMClient(LLMClient):
    """Interact with a vLLM server that exposes the OpenAI-compatible API."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._host = settings.llm.vllm_host.rstrip("/")
        self._model = settings.llm.vllm_model
        self._timeout = settings.llm.request_timeout

    async def generate(self, prompt: str, *, context: Sequence[str] | None = None) -> AsyncGenerator[str, None]:
        """Generate a streamed completion from vLLM."""

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": self._build_user_prompt(prompt, context)},
        ]
        payload = {
            "model": self._model,
            "messages": messages,
            "stream": True,
            "temperature": 0.1,
            "top_p": 0.9,
        }
        url = f"{self._host}/v1/chat/completions"
        timeout = httpx.Timeout(self._timeout, connect=self._timeout, read=None, write=self._timeout)
        LOGGER.info(
            "vLLM request started | model=%s context_chunks=%d prompt_chars=%d",
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
                        chunk = self._parse_line(line)
                        if chunk:
                            chunk_count += 1
                            LOGGER.debug(
                                "vLLM streamed chunk | model=%s length=%d",
                                self._model,
                                len(chunk),
                            )
                            yield chunk
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"vLLM generation failed with status {exc.response.status_code}: {exc.response.text}"
            ) from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Failed to reach vLLM server at {url}: {exc}") from exc
        finally:
            duration = perf_counter() - start_time
            LOGGER.info(
                "vLLM request finished | model=%s duration=%.2fs chunks=%d",
                self._model,
                duration,
                chunk_count,
            )

    def _build_user_prompt(self, prompt: str, context: Sequence[str] | None) -> str:
        if not context:
            return prompt
        context_block = "\n\n".join(context)
        return f"Context:\n{context_block}\n\nQuestion:\n{prompt}"

    @staticmethod
    def _parse_line(line: str) -> str:
        prefix = "data:"
        if not line.startswith(prefix):
            return ""
        data = line[len(prefix) :].strip()
        if not data or data == "[DONE]":
            return ""
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            return ""
        choices = payload.get("choices") or []
        if not choices:
            return ""
        delta = (choices[0] or {}).get("delta") or {}
        text = delta.get("content")
        return str(text) if text else ""


__all__ = ["VLLMClient"]
