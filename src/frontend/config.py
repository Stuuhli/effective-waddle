"""Configuration helpers for the lightweight frontend."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FrontendConfig:
    """Paths and constants for serving the HTML frontend."""

    template_directory: Path = Path(__file__).resolve().parents[2] / "templates"
    static_directory: Path = Path(__file__).resolve().parents[2] / "templates" / "static"


DEFAULT_FRONTEND_CONFIG = FrontendConfig()


__all__ = ["FrontendConfig", "DEFAULT_FRONTEND_CONFIG"]
