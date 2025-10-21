"""Embedding client exports."""

from .base import EmbeddingClient
from .local import LocalEmbeddingClient

__all__ = ["EmbeddingClient", "LocalEmbeddingClient"]
