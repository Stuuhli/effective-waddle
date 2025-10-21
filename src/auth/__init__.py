"""Authentication package exports."""
from __future__ import annotations

from typing import Any

__all__ = ["router"]


def __getattr__(name: str) -> Any:
    if name == "router":
        from .router import router as _router

        return _router
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
