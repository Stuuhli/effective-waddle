"""Frontend package exports."""
from __future__ import annotations

from .config import DEFAULT_FRONTEND_CONFIG, FrontendConfig
from .router import router

__all__ = ["router", "FrontendConfig", "DEFAULT_FRONTEND_CONFIG"]
