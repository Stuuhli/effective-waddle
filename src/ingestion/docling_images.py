"""Utilities for locating Docling generated page images."""
from __future__ import annotations

import base64
import json
import mimetypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from ..config import StorageSettings, load_settings


def _decode_image(uri: str) -> bytes | None:
    if not uri.startswith("data:image"):
        return None
    try:
        _, data = uri.split(",", 1)
    except ValueError:
        return None
    try:
        return base64.b64decode(data)
    except (base64.binascii.Error, ValueError):
        return None


def _image_extension(mimetype: str | None) -> str:
    if not mimetype or "/" not in mimetype:
        return ".png"
    subtype = mimetype.split("/", 1)[1].lower()
    if subtype in {"jpeg", "jpg"}:
        return ".jpg"
    if subtype in {"png", "gif", "webp", "bmp"}:
        return f".{subtype}"
    return ".png"


@dataclass(slots=True)
class DoclingImageLocator:
    """Resolve Docling page preview images on demand."""

    storage: StorageSettings = field(default_factory=StorageSettings)
    _docling_dir: Path = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._docling_dir = Path(self.storage.docling_output_dir).resolve()

    def locate_from_metadata(self, metadata: Mapping[str, object], page_number: int) -> Path | None:
        """Return a filesystem path for the requested page image if it exists."""

        cache_dir = self._resolve_cache_dir(metadata)
        if cache_dir is None:
            return None
        image_path = self._existing_page_image(cache_dir, page_number)
        if image_path and image_path.exists():
            return image_path

        json_path = self._resolve_json_path(metadata)
        if not json_path:
            return image_path if image_path and image_path.exists() else None

        payload = self._load_json(json_path)
        if payload is None:
            return image_path if image_path and image_path.exists() else None

        image_bytes, extension = self._extract_page_image(payload, page_number)
        if not image_bytes:
            return image_path if image_path and image_path.exists() else None

        cache_dir.mkdir(parents=True, exist_ok=True)
        materialised = cache_dir / f"page-{page_number}{extension}"
        materialised.write_bytes(image_bytes)
        return materialised

    def mimetype_for(self, path: Path) -> str:
        guess, _ = mimetypes.guess_type(path.name)
        return guess or "image/png"

    def _resolve_cache_dir(self, metadata: Mapping[str, object]) -> Path | None:
        docling_hash = metadata.get("docling_hash")
        if isinstance(docling_hash, str) and docling_hash.strip():
            candidate = (self._docling_dir / docling_hash.strip()).resolve()
        else:
            image_dir = metadata.get("image_dir")
            if not isinstance(image_dir, str) or not image_dir.strip():
                return None
            candidate = Path(image_dir).expanduser().resolve()

        try:
            candidate.relative_to(self._docling_dir)
        except ValueError:
            return None
        return candidate

    def _resolve_json_path(self, metadata: Mapping[str, object]) -> Path | None:
        raw = metadata.get("docling_output")
        if not isinstance(raw, str) or not raw.strip():
            return None
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = (self._docling_dir / candidate).resolve()
        else:
            candidate = candidate.resolve()
        try:
            candidate.relative_to(self._docling_dir)
        except ValueError:
            return None
        return candidate if candidate.exists() else None

    @staticmethod
    def _existing_page_image(cache_dir: Path, page_number: int) -> Path | None:
        for candidate in sorted(cache_dir.glob(f"page-{page_number}.*")):
            if candidate.is_file():
                return candidate
        return None

    @staticmethod
    def _load_json(path: Path) -> dict[str, object] | None:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    @staticmethod
    def _extract_page_image(payload: Mapping[str, object], page_number: int) -> tuple[bytes | None, str]:
        pages = payload.get("pages")
        if isinstance(pages, dict):
            items = pages.items()
        elif isinstance(pages, list):
            items = enumerate(pages, start=1)
        else:
            return None, ""

        for key, page_info in items:
            if not isinstance(page_info, dict):
                continue
            raw_number = page_info.get("page_no", key)
            try:
                number = int(raw_number)
            except (TypeError, ValueError):
                continue
            if number != page_number:
                continue
            image_info = page_info.get("image")
            if not isinstance(image_info, dict):
                return None, ""
            uri = image_info.get("uri")
            mimetype = image_info.get("mimetype") if isinstance(image_info.get("mimetype"), str) else None
            if not isinstance(uri, str):
                return None, ""
            image_bytes = _decode_image(uri)
            if not image_bytes:
                return None, ""
            return image_bytes, _image_extension(mimetype)
        return None, ""


def get_locator(storage: StorageSettings | None = None) -> DoclingImageLocator:
    settings = storage or load_settings().storage
    return DoclingImageLocator(storage=settings)


__all__ = ["DoclingImageLocator", "get_locator"]
