"""FastAPI application factory."""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi_users.password import PasswordHelper

from . import dependencies
from .admin.router import router as admin_router
from .auth.dependencies import configure_auth, get_auth_backend_instance
from .auth.models import UserCreate, UserRead, UserUpdate
from .auth.router import router as auth_router
from .auth.constants import (
    ADMIN_ROLE_DESCRIPTION,
    ADMIN_ROLE_NAME,
    DEFAULT_ROLE_DESCRIPTION,
    DEFAULT_ROLE_NAME,
    GRAPH_RAG_ROLE_DESCRIPTION,
    GRAPH_RAG_ROLE_NAME,
    RAG_ROLE_DESCRIPTION,
    RAG_ROLE_NAME,
)
from .frontend import STATIC_DIR, login_router
from .ingestion.router import router as ingestion_router
from .logging import setup_logging
from .retrieval.router import router as retrieval_router
from .infrastructure.repositories.document_repo import DocumentRepository
from .infrastructure.repositories.user_repo import UserRepository

try:
    from fastapi_voyager import create_voyager
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    create_voyager = None  # type: ignore[assignment]

LOGGER = logging.getLogger(__name__)

def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    settings = dependencies.get_settings()
    setup_logging(settings)

    session_factory = dependencies.get_session_factory()

    app = FastAPI(
        title=settings.fastapi.title,
        description=settings.fastapi.description,
        version=settings.fastapi.version,
        docs_url=settings.fastapi.docs_url,
        redoc_url=settings.fastapi.redoc_url,
        openapi_url=settings.fastapi.openapi_url,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.fastapi.cors_allow_origins,
        allow_credentials=settings.fastapi.cors_allow_credentials,
        allow_methods=settings.fastapi.cors_allow_methods,
        allow_headers=settings.fastapi.cors_allow_headers,
    )
    app.add_middleware(GZipMiddleware, minimum_size=settings.fastapi.gzip_minimum_size)

    fastapi_users = configure_auth(settings)
    auth_backend = get_auth_backend_instance()

    app.include_router(
        fastapi_users.get_auth_router(auth_backend),
        prefix="/auth/jwt",
        tags=["auth"],
    )
    app.include_router(
        fastapi_users.get_register_router(UserRead, UserCreate),
        prefix="/auth",
        tags=["auth"],
    )
    app.include_router(
        fastapi_users.get_users_router(UserRead, UserUpdate),
        prefix="/users",
        tags=["users"],
    )
    app.include_router(auth_router, prefix="/auth", tags=["auth"])
    app.include_router(retrieval_router, prefix="/chat", tags=["retrieval"])
    app.include_router(ingestion_router, prefix="/ingestion", tags=["ingestion"])
    app.include_router(admin_router, prefix="/admin", tags=["admin"])

    app.mount("/frontend/static", StaticFiles(directory=STATIC_DIR), name="frontend_static")
    app.include_router(login_router, prefix="/frontend", tags=["frontend"])

    if settings.fastapi.enable_voyager:
        if create_voyager is None:
            logging.warning(
                "FastAPI Voyager requested via settings.fastapi.enable_voyager, but fastapi-voyager is not installed.",
            )
        else:
            voyager_app = create_voyager(app, module_prefix="src")
            app.mount("/frontend/voyager", voyager_app)

    async def redirect_to_frontend() -> RedirectResponse:
        return RedirectResponse(url="/frontend/login", status_code=307)

    app.add_api_route("/", redirect_to_frontend, include_in_schema=False)
    app.add_api_route("/frontend", redirect_to_frontend, include_in_schema=False)

    async def _ensure_bootstrap_admin() -> None:
        async with session_factory() as session:  # type: ignore[call-arg]
            user_repo = UserRepository(session)
            document_repo = DocumentRepository(session)

            roles = {
                DEFAULT_ROLE_NAME: await user_repo.ensure_role(DEFAULT_ROLE_NAME, DEFAULT_ROLE_DESCRIPTION),
                ADMIN_ROLE_NAME: await user_repo.ensure_role(ADMIN_ROLE_NAME, ADMIN_ROLE_DESCRIPTION),
                RAG_ROLE_NAME: await user_repo.ensure_role(RAG_ROLE_NAME, RAG_ROLE_DESCRIPTION),
                GRAPH_RAG_ROLE_NAME: await user_repo.ensure_role(GRAPH_RAG_ROLE_NAME, GRAPH_RAG_ROLE_DESCRIPTION),
            }

            compliance = await document_repo.ensure_collection(
                "compliance", "Compliance document collection"
            )
            await document_repo.assign_collection_to_role(compliance, roles[ADMIN_ROLE_NAME])
            await session.commit()

            admin_email = settings.bootstrap.admin_email
            existing = await user_repo.get_by_email(admin_email)
            if existing:
                return

            capability = settings.bootstrap.admin_capability
            if capability not in (RAG_ROLE_NAME, GRAPH_RAG_ROLE_NAME):
                LOGGER.warning(
                    "Invalid bootstrap admin capability '%s'; defaulting to '%s'.",
                    capability,
                    RAG_ROLE_NAME,
                )
                capability = RAG_ROLE_NAME

            password_helper = PasswordHelper()
            hashed_password = password_helper.hash(settings.bootstrap.admin_password)
            await user_repo.create_user(
                email=admin_email,
                hashed_password=hashed_password,
                full_name=settings.bootstrap.admin_full_name,
                roles=[roles[ADMIN_ROLE_NAME], roles[capability]],
                is_active=True,
                is_superuser=True,
                is_verified=True,
            )

    @app.on_event("startup")
    async def _bootstrap_admin_user() -> None:
        await _ensure_bootstrap_admin()

    return app


app = create_app()
