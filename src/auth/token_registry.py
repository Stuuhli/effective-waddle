"""In-memory token registry to enforce single active JWT per user."""
from __future__ import annotations

from asyncio import Lock
from typing import Dict

_registry: Dict[str, str] = {}
_lock = Lock()


async def register(user_id: str, token: str) -> None:
    """Store the latest token for the given user."""

    async with _lock:
        _registry[user_id] = token


async def validate(user_id: str, token: str) -> bool:
    """Return True when the token matches the stored entry."""

    async with _lock:
        current = _registry.get(user_id)
    return current == token


async def revoke(user_id: str) -> None:
    """Remove the token associated with the user id."""

    async with _lock:
        _registry.pop(user_id, None)


__all__ = ["register", "validate", "revoke"]
