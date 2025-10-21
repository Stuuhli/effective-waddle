"""HTML login frontend with glassmorphism styling."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..auth.dependencies import get_auth_backend_instance
from ..auth.user_manager import get_user_manager, UserManager
from ..infrastructure.database import User


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
async def chat_page(request: Request, user: User = Depends(_current_user_from_cookie)) -> HTMLResponse:
    """Render the chat workspace with placeholder data."""
    is_admin = any(role.name == "admin" for role in user.roles)
    context = {
        "request": request,
        "is_admin": is_admin,
        "conversations": [
            {"id": "conv-1", "title": "Welcome Tour", "updated_at": "Just now"},
            {"id": "conv-2", "title": "Product Brainstorm", "updated_at": "2 hours ago"},
            {"id": "conv-3", "title": "Research Notes", "updated_at": "Yesterday"},
        ],
    }
    return templates.TemplateResponse("chat.html", context)


@router.get("/ingestion", response_class=HTMLResponse, include_in_schema=False)
async def ingestion_page(request: Request, user: User = Depends(_current_user_from_cookie)) -> HTMLResponse:
    """Render the ingestion workflow workspace."""
    is_admin = any(role.name == "admin" for role in user.roles)
    context = {
        "request": request,
        "is_admin": is_admin,
        "collections": [
            {"name": "documents", "document_count": 128},
            {"name": "product-guides", "document_count": 56},
        ],
        "recent_jobs": [
            {
                "id": "job-1",
                "source": "s3://bucket/onboarding.pdf",
                "collection": "documents",
                "status": "completed",
                "updated_at": "5 minutes ago",
            },
            {
                "id": "job-2",
                "source": "/uploads/support-handbook.pdf",
                "collection": "product-guides",
                "status": "processing",
                "updated_at": "18 minutes ago",
            },
        ],
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
