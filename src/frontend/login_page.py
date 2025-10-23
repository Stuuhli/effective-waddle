"""HTML login frontend with glassmorphism styling."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..auth.dependencies import get_auth_backend_instance
from ..auth.user_manager import get_user_manager, UserManager
from ..infrastructure.database import IngestionJob, User
from ..config import load_settings
from ..ingestion.dependencies import get_ingestion_service
from ..ingestion.service import IngestionService
from ..retrieval.dependencies import get_retrieval_service
from ..retrieval.service import RetrievalService


async def _current_user_from_cookie(
    token: str | None = Cookie(default=None, alias="rag_token"),
    backend=Depends(get_auth_backend_instance),
    user_manager: UserManager = Depends(get_user_manager),
) -> User:
    if not token:
        raise HTTPException(status_code=status.HTTP_307_TEMPORARY_REDIRECT, headers={"Location": "/frontend/login"})

    strategy = backend.get_strategy()
    user = await strategy.read_token(token, user_manager)
    if user is None:
        raise HTTPException(status_code=status.HTTP_307_TEMPORARY_REDIRECT, headers={"Location": "/frontend/login"})
    return user

PACKAGE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = PACKAGE_DIR / "templates"
STATIC_DIR = PACKAGE_DIR / "static"


templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
router = APIRouter()


@router.get("/login", response_class=HTMLResponse, include_in_schema=False)
async def login_page(request: Request) -> HTMLResponse:
    """Render the custom login page."""
    return templates.TemplateResponse("login.html", {"request": request})

@router.get("/chat", response_class=HTMLResponse, include_in_schema=False)
async def chat_page(
    request: Request,
    user: User = Depends(_current_user_from_cookie),
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
) -> HTMLResponse:
    """Render the chat workspace with persisted conversations."""
    is_admin = any(role.name == "admin" for role in user.roles)
    conversations = await retrieval_service.list_sessions(user.id)
    context = {
        "request": request,
        "is_admin": is_admin,
        "conversations": conversations,
    }
    return templates.TemplateResponse("chat.html", context)


@router.get("/ingestion", response_class=HTMLResponse, include_in_schema=False)
async def ingestion_page(
    request: Request,
    user: User = Depends(_current_user_from_cookie),
    service: IngestionService = Depends(get_ingestion_service),
) -> HTMLResponse:
    """Render the ingestion workflow workspace."""
    is_admin = any(role.name == "admin" for role in user.roles)
    settings = load_settings()
    collections = await service.collection_summaries(list(user.roles))
    jobs = await service.list_jobs_for_user(None if user.is_superuser else user.id, limit=20)
    def _job_source(job: IngestionJob) -> str:
        parameters = job.parameters or {}
        if isinstance(parameters, dict):
            original = parameters.get("original_filename")
            if isinstance(original, str) and original.strip():
                return original.strip()
        return job.source

    recent_jobs = [
        {
            "id": job.id,
            "source": _job_source(job),
            "collection": job.collection.name if job.collection else "unknown",
            "status": job.status.value,
            "updated_at": job.updated_at.strftime("%Y-%m-%d %H:%M"),
        }
        for job in jobs
    ]
    context = {
        "request": request,
        "is_admin": is_admin,
        "collections": collections,
        "recent_jobs": recent_jobs,
        "chunk_defaults": {
            "size": settings.chunking.default_size,
            "overlap": settings.chunking.default_overlap,
        },
    }
    return templates.TemplateResponse("ingestion.html", context)


@router.get("/admin", response_class=HTMLResponse, include_in_schema=False)
async def admin_page(request: Request, user: User = Depends(_current_user_from_cookie)) -> HTMLResponse:
    """Render a placeholder admin dashboard."""
    is_admin = any(role.name == "admin" for role in user.roles)
    context = {
        "request": request,
        "is_admin": is_admin,
    }
    return templates.TemplateResponse("admin.html", context)


__all__ = ["router", "STATIC_DIR"]
