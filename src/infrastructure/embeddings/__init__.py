"""Embedding client exports."""

from .base import EMBEDDING_DIMENSION, EmbeddingClient
from .factory import create_embedding_client
from .local import LocalEmbeddingClient
from .ollama import OllamaEmbeddingClient

__all__ = [
    "EMBEDDING_DIMENSION",
    "EmbeddingClient",
    "create_embedding_client",
    "LocalEmbeddingClient",
    "OllamaEmbeddingClient",
]
