"""Factory helpers for embedding clients."""
from __future__ import annotations

import logging

from ...config import Settings
from .base import EmbeddingClient
from .local import LocalEmbeddingClient
from .ollama import OllamaEmbeddingClient

LOGGER = logging.getLogger(__name__)


def create_embedding_client(settings: Settings) -> EmbeddingClient:
    """Create an embedding client based on runtime configuration."""

    if settings.llm.provider == "ollama":
        model_name = settings.llm.embedding_model
        if model_name not in {"qwen3:0.6b", "embeddinggemma"}:
            LOGGER.warning(
                "Unsupported Ollama embedding model '%s'. Falling back to qwen3:0.6b.",
                model_name,
            )
            model_name = "qwen3:0.6b"
        return OllamaEmbeddingClient(
            host=settings.llm.ollama_host,
            model_name=model_name,
            request_timeout=settings.llm.request_timeout,
        )
    return LocalEmbeddingClient()


__all__ = ["create_embedding_client"]
