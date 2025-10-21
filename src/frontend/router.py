"""Frontend integration routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..config import Settings
from ..dependencies import get_settings
from .config import DEFAULT_FRONTEND_CONFIG, FrontendConfig

router = APIRouter()
_templates_cache: dict[str, Jinja2Templates] = {}


def get_templates(config: FrontendConfig) -> Jinja2Templates:
    """Return a cached ``Jinja2Templates`` instance for the configured directory."""

    key = str(config.template_directory)
    if key not in _templates_cache:
        _templates_cache[key] = Jinja2Templates(directory=key)
    return _templates_cache[key]


@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    settings: Settings = Depends(get_settings),
    config: FrontendConfig = DEFAULT_FRONTEND_CONFIG,
) -> HTMLResponse:
    templates = get_templates(config)
    base_url = str(request.base_url).rstrip("/")
    context = {
        "request": request,
        "api_base": base_url,
        "app_title": settings.fastapi.title,
        "docs_url": settings.fastapi.docs_url,
    }
    return templates.TemplateResponse("index.html", context)


__all__ = ["router"]
