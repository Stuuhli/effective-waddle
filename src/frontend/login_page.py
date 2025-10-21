"""HTML login frontend with glassmorphism styling."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

PACKAGE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = PACKAGE_DIR / "templates"
STATIC_DIR = PACKAGE_DIR / "static"


templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
router = APIRouter()


@router.get("/login", response_class=HTMLResponse, include_in_schema=False)
async def login_page(request: Request) -> HTMLResponse:
    """Render the custom login page."""
    return templates.TemplateResponse("login.html", {"request": request})

async def chat_page(request: Request) -> HTMLResponse:
    """Render a placeholder chat view."""
    return templates.TemplateResponse("chat.html", {"request": request})

__all__ = ["router", "STATIC_DIR", "chat_page"]
