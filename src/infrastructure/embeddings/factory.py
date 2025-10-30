"""Factory helpers for embedding clients."""
from __future__ import annotations

import logging

from ...config import Settings
from .base import EmbeddingClient
from .constants import (
    DEFAULT_OLLAMA_EMBEDDING_MODEL,
    SUPPORTED_OLLAMA_EMBEDDING_MODELS,
    embedding_dimension_for_model,
)
from .local import LocalEmbeddingClient
from .ollama import OllamaEmbeddingClient

LOGGER = logging.getLogger(__name__)


def create_embedding_client(settings: Settings) -> EmbeddingClient:
    """Create an embedding client based on runtime configuration."""

    model_name = settings.llm.embedding_model or DEFAULT_OLLAMA_EMBEDDING_MODEL
    if settings.llm.provider == "ollama":
        normalised_model = model_name.lower()
        if normalised_model not in SUPPORTED_OLLAMA_EMBEDDING_MODELS:
            LOGGER.warning(
                "Unsupported Ollama embedding model '%s'. Falling back to %s.",
                model_name,
                DEFAULT_OLLAMA_EMBEDDING_MODEL,
            )
            model_name = DEFAULT_OLLAMA_EMBEDDING_MODEL
            normalised_model = model_name
        return OllamaEmbeddingClient(
            host=settings.llm.ollama_host,
            model_name=model_name,
            request_timeout=settings.llm.request_timeout,
            binary_path=settings.llm.ollama_binary,
            dimension=embedding_dimension_for_model(normalised_model),
        )
    return LocalEmbeddingClient(dimension=embedding_dimension_for_model(model_name))


__all__ = ["create_embedding_client"]
