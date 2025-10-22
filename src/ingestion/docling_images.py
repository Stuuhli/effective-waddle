"""Utilities for locating Docling generated page images."""
from __future__ import annotations

import base64
import json
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

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

    storage: StorageSettings = StorageSettings()

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

def _iter_pages(payload: Mapping[str, object]) -> Iterable[tuple[int | None, Mapping[str, object]]]:
    pages = payload.get("pages")
    if isinstance(pages, dict):
        for key, value in pages.items():
            if isinstance(value, Mapping):
                try:
                    number = int(key)
                except (TypeError, ValueError):
                    number = None
                yield number, value
    elif isinstance(pages, list):
        for index, value in enumerate(pages, start=1):
            if isinstance(value, Mapping):
                yield index, value

    documents = payload.get("documents")
    if isinstance(documents, list):
        for document in documents:
            if isinstance(document, Mapping):
                yield from _iter_pages(document)

    document = payload.get("document")
    if isinstance(document, Mapping):
        yield from _iter_pages(document)


def _candidate_media(payload: Mapping[str, object]) -> Iterable[Mapping[str, object] | str]:
    keys = ("image", "preview_image", "preview", "thumbnail")
    for key in keys:
        candidate = payload.get(key)
        if isinstance(candidate, Mapping) or isinstance(candidate, str):
            yield candidate

    resources = payload.get("resources")
    if isinstance(resources, Mapping):
        for key in keys:
            candidate = resources.get(key)
            if isinstance(candidate, Mapping) or isinstance(candidate, str):
                yield candidate
        assets = resources.get("assets")
        if isinstance(assets, list):
            for asset in assets:
                if isinstance(asset, Mapping) or isinstance(asset, str):
                    yield asset

    media = payload.get("media")
    if isinstance(media, list):
        for item in media:
            if isinstance(item, Mapping) or isinstance(item, str):
                yield item


def _media_to_bytes(candidate: Mapping[str, object] | str) -> tuple[bytes | None, str]:
    if isinstance(candidate, str):
        uri = candidate
        mimetype = None
    else:
        uri = candidate.get("uri") or candidate.get("data") or candidate.get("source")
        if isinstance(uri, str) and uri.startswith("file://"):
            return None, ""
        mimetype = candidate.get("mimetype") or candidate.get("mime_type") or candidate.get("content_type")
    if not isinstance(uri, str):
        return None, ""
    image_bytes = _decode_image(uri)
    if not image_bytes:
        return None, ""
    return image_bytes, _image_extension(mimetype if isinstance(mimetype, str) else None)


def _extract_page_image(payload: Mapping[str, object], page_number: int) -> tuple[bytes | None, str]:
    for fallback_number, page_info in _iter_pages(payload):
        if not isinstance(page_info, Mapping):
            continue
        raw_number = page_info.get("page_no") or page_info.get("page_number") or fallback_number
        try:
            number = int(raw_number) if raw_number is not None else None
        except (TypeError, ValueError):
            number = None
        if number != page_number:
            continue
        for media in _candidate_media(page_info):
            image_bytes, extension = _media_to_bytes(media)
            if image_bytes:
                return image_bytes, extension
        return None, ""
    return None, ""


def get_locator(storage: StorageSettings | None = None) -> DoclingImageLocator:
    settings = storage or load_settings().storage
    return DoclingImageLocator(storage=settings)


__all__ = ["DoclingImageLocator", "get_locator"]
