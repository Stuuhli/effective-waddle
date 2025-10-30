"""Shared constants for embedding backends."""
from __future__ import annotations

DEFAULT_OLLAMA_EMBEDDING_MODEL = "qwen3-embedding:0.6b"
SUPPORTED_OLLAMA_EMBEDDING_MODELS = {
    "qwen3-embedding:0.6b",
    "qwen3-embedding:4b",
    "qwen4-embedding:4b",
    "embeddinggemma",
    "qwen3:0.6b",
}

MODEL_DIMENSIONS = {
    "qwen3-embedding:0.6b": 1024,
    "qwen3-embedding:4b": 2560,
    "qwen4-embedding:4b": 2560,
}


def embedding_dimension_for_model(model_name: str | None) -> int:
    """Return the expected embedding dimensionality for a given model string."""

    if not model_name:
        return MODEL_DIMENSIONS[DEFAULT_OLLAMA_EMBEDDING_MODEL]
    key = model_name.lower()
    if key in MODEL_DIMENSIONS:
        return MODEL_DIMENSIONS[key]
    # Some models might be referenced without the exact suffix; try prefix matches.
    for candidate, dimension in MODEL_DIMENSIONS.items():
        if key.startswith(candidate):
            return dimension
    return MODEL_DIMENSIONS[DEFAULT_OLLAMA_EMBEDDING_MODEL]

__all__ = [
    "DEFAULT_OLLAMA_EMBEDDING_MODEL",
    "SUPPORTED_OLLAMA_EMBEDDING_MODELS",
    "MODEL_DIMENSIONS",
    "embedding_dimension_for_model",
]
