"""Constants used across the authentication package."""

DEFAULT_ROLE_NAME = "user"
DEFAULT_ROLE_DESCRIPTION = "Default user role"
ADMIN_ROLE_NAME = "admin"
GRAPH_RAG_ROLE_NAME = "graphrag"
ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"
OAUTH2_TOKEN_URL = "/auth/login"

__all__ = [
    "DEFAULT_ROLE_NAME",
    "DEFAULT_ROLE_DESCRIPTION",
    "ADMIN_ROLE_NAME",
    "GRAPH_RAG_ROLE_NAME",
    "ACCESS_TOKEN_TYPE",
    "REFRESH_TOKEN_TYPE",
    "OAUTH2_TOKEN_URL",
]
