"""Factory helpers for embedding clients."""
from __future__ import annotations

import logging

from ...config import Settings
from .base import EmbeddingClient
from .constants import DEFAULT_OLLAMA_EMBEDDING_MODEL, SUPPORTED_OLLAMA_EMBEDDING_MODELS
from .local import LocalEmbeddingClient
from .ollama import OllamaEmbeddingClient

LOGGER = logging.getLogger(__name__)


def create_embedding_client(settings: Settings) -> EmbeddingClient:
    """Create an embedding client based on runtime configuration."""

    if settings.llm.provider == "ollama":
        model_name = settings.llm.embedding_model
        if model_name not in SUPPORTED_OLLAMA_EMBEDDING_MODELS:
            LOGGER.warning(
                "Unsupported Ollama embedding model '%s'. Falling back to %s.",
                model_name,
                DEFAULT_OLLAMA_EMBEDDING_MODEL,
            )
            model_name = DEFAULT_OLLAMA_EMBEDDING_MODEL
        return OllamaEmbeddingClient(
            host=settings.llm.ollama_host,
            model_name=model_name,
            request_timeout=settings.llm.request_timeout,
            binary_path=settings.llm.ollama_binary,
        )
    return LocalEmbeddingClient()


__all__ = ["create_embedding_client"]
