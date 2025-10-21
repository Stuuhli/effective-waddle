"""Authentication specific exceptions."""
from __future__ import annotations

from ..exceptions import ServiceError


class AuthenticationError(ServiceError):
    """Raised when authentication fails."""


class AuthorizationError(ServiceError):
    """Raised when authorization checks fail."""


__all__ = ["AuthenticationError", "AuthorizationError"]
