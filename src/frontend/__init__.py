"""Frontend package exports."""
from __future__ import annotations

from .login_page import STATIC_DIR, router as login_router

__all__ = ["login_router", "STATIC_DIR"]
