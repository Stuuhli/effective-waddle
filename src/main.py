"""FastAPI application factory."""
from __future__ import annotations

import gradio as gr
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import RedirectResponse

from . import dependencies
from .auth.dependencies import configure_auth, get_auth_backend_instance
from .auth.models import UserCreate, UserRead, UserUpdate
from .auth.router import router as auth_router
from .logging import setup_logging
from .retrieval.router import router as retrieval_router
from .ingestion.router import router as ingestion_router
from .admin.router import router as admin_router
from .frontend import create_frontend


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    settings = dependencies.get_settings()
    setup_logging(settings)

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

    gradio_app = create_frontend(settings)
    gr.mount_gradio_app(app, gradio_app, path="/frontend/login")

    async def redirect_to_frontend() -> RedirectResponse:
        return RedirectResponse(url="/frontend/login", status_code=307)

    app.add_api_route("/", redirect_to_frontend, include_in_schema=False)
    app.add_api_route("/frontend", redirect_to_frontend, include_in_schema=False)

    return app


app = create_app()
