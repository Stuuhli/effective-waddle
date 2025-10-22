"""Shared constants for embedding backends."""
from __future__ import annotations

DEFAULT_OLLAMA_EMBEDDING_MODEL = "qwen3-embedding:0.6b"
SUPPORTED_OLLAMA_EMBEDDING_MODELS = {
    "qwen3-embedding:0.6b",
    "qwen3:0.6b",
    "embeddinggemma",
}

__all__ = ["DEFAULT_OLLAMA_EMBEDDING_MODEL", "SUPPORTED_OLLAMA_EMBEDDING_MODELS"]
