"""Auth domain models re-exporting ORM entities."""
from __future__ import annotations

from ..infrastructure.database import Role, User

__all__ = ["User", "Role"]
