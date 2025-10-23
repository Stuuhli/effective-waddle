"""Embedding client backed by the Ollama embeddings API."""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin

import httpx

from .base import EMBEDDING_DIMENSION, EmbeddingClient

LOGGER = logging.getLogger(__name__)

# fallback for failed import, which was annoying within the IDE
if TYPE_CHECKING:  # pragma: no cover - for static analysis only
    from ollama import AsyncClient  # noqa: F401
else:
    AsyncClient = Any


def _normalise_dimension(vector: Sequence[float], dimension: int) -> list[float]:
    """Resize embeddings to match the configured pgvector dimension."""

    values = list(vector)
    current = len(values)
    if current == dimension:
        return values
    if current > dimension:
        LOGGER.debug("Truncating embedding from %s to %s dimensions", current, dimension)
        return values[:dimension]
    LOGGER.debug("Padding embedding from %s to %s dimensions", current, dimension)
    return values + [0.0] * (dimension - current)


class OllamaEmbeddingClient(EmbeddingClient):
    """Generate embeddings via an Ollama server."""

    _SERVER_POLL_INTERVAL = 1.0
    _SERVER_START_ATTEMPTS = 15

    def __init__(
        self,
        *,
        host: str,
        model_name: str,
        request_timeout: int,
        binary_path: str,
        dimension: int = EMBEDDING_DIMENSION,
    ) -> None:
        self._host = host.rstrip("/")
        self.model_name = model_name
        self._timeout = request_timeout
        self._dimension = dimension
        self._binary_path = binary_path
        self._client: AsyncClient | None = None
        self._server_lock: asyncio.Lock | None = None
        self._server_running = False
        self._server_process: subprocess.Popen[bytes] | None = None

    async def _ensure_client(self) -> AsyncClient:
        await self._ensure_server_running()
        if self._client is not None:
            return self._client
        try:
            from ollama import AsyncClient
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("The 'ollama' package is required to use Ollama embeddings") from exc
        self._client = AsyncClient(host=self._host, timeout=self._timeout)
        return self._client

    async def _ensure_server_running(self) -> None:
        if self._server_running:
            return
        if self._server_lock is None:
            self._server_lock = asyncio.Lock()
        async with self._server_lock:
            if self._server_running:
                return
            if await self._is_server_ready():
                self._server_running = True
                return
            self._start_server_process()
            for attempt in range(self._SERVER_START_ATTEMPTS):
                await asyncio.sleep(self._SERVER_POLL_INTERVAL)
                if await self._is_server_ready():
                    self._server_running = True
                    return
            raise RuntimeError(
                "Could not connect to the Ollama server after attempting to start it automatically."
            )

    async def _is_server_ready(self) -> bool:
        url = urljoin(f"{self._host}/", "api/version")
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(url)
        except httpx.HTTPError:
            return False
        return response.status_code == 200

    def _start_server_process(self) -> None:
        command = [self._binary_path, "serve"]
        LOGGER.info("Starting Ollama server using %s", " ".join(command))
        try:
            self._server_process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                env=os.environ.copy(),
                start_new_session=True,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"Unable to start Ollama server. Binary not found at '{self._binary_path}'."
            ) from exc
        except OSError as exc:  # pragma: no cover - system dependent failure
            raise RuntimeError("Failed to launch the Ollama server process.") from exc

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        client = await self._ensure_client()
        embeddings: list[list[float]] = []
        for text in texts:
            try:
                response = await client.embeddings(model=self.model_name, prompt=text)
            except Exception as exc:  # noqa: BLE001
                message = str(exc)
                if "context length" in message.lower():
                    approx_words = len(text.split())
                    raise RuntimeError(
                        "Ollama embeddings rejected a chunk because it exceeds the model context window. "
                        f"Approximate word count: {approx_words}. Consider reducing the ingestion chunk size "
                        "or splitting large documents before ingestion."
                    ) from exc
                raise
            vector = response.get("embedding")
            if not isinstance(vector, Sequence):
                raise RuntimeError("Unexpected response format from Ollama embeddings endpoint")
            embeddings.append(_normalise_dimension(vector, self._dimension))
        return embeddings


__all__ = ["OllamaEmbeddingClient"]
