"""Utilities for resolving Docling-generated page images."""
from __future__ import annotations

import base64
import json
import logging
import mimetypes
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from ..config import StorageSettings

LOGGER = logging.getLogger(__name__)

_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")


class DoclingImageLocator:
    """Resolve Docling page preview images given stored metadata."""

    def __init__(self, *, storage: StorageSettings) -> None:
        self.storage = storage

    def locate_from_metadata(self, metadata: Mapping[str, Any], page_number: int) -> Path | None:
        """Return the filesystem path for the given page preview, if available."""

        if page_number <= 0:
            return None

        safe_metadata = dict(metadata or {})
        image_dir = self._resolve_image_dir(safe_metadata)
        if image_dir is not None:
            resolved = self._locate_in_directory(image_dir, page_number)
            if resolved is not None:
                return resolved

        json_path = self._resolve_docling_output_path(safe_metadata)
        if json_path is None:
            return None
        try:
            return self._materialise_from_json(
                json_path=json_path,
                page_number=page_number,
                fallback_dir=image_dir
                or self.storage.docling_output_dir / str(safe_metadata.get("docling_hash", "")),
            )
        except Exception:  # noqa: BLE001 - defensive, falls through to None
            LOGGER.debug("Unable to materialise Docling preview", exc_info=True)
            return None

    def _resolve_image_dir(self, metadata: Mapping[str, Any]) -> Path | None:
        image_dir_value = metadata.get("image_dir")
        docling_hash = metadata.get("docling_hash")

        candidates: list[Path] = []
        if isinstance(image_dir_value, str) and image_dir_value:
            candidates.append(Path(image_dir_value))
        if isinstance(docling_hash, str) and docling_hash:
            candidates.append(self.storage.docling_output_dir / docling_hash)

        for candidate in candidates:
            resolved = self._within_docling_root(candidate)
            if resolved is not None and resolved.exists():
                return resolved
        return None

    def _locate_in_directory(self, directory: Path, page_number: int) -> Path | None:
        if not directory.exists():
            return None

        candidates = [
            directory / f"page-{page_number}{ext}"
            for ext in _IMAGE_EXTENSIONS
        ]
        candidates.extend(
            directory / f"page-{page_number:04d}{ext}"
            for ext in _IMAGE_EXTENSIONS
        )

        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def _resolve_docling_output_path(self, metadata: Mapping[str, Any]) -> Path | None:
        docling_output = metadata.get("docling_output")
        if not isinstance(docling_output, str) or not docling_output:
            return None
        output_path = Path(docling_output)
        resolved = self._within_docling_root(output_path)
        if resolved is None:
            LOGGER.debug("Ignoring docling_output outside configured root: %s", output_path)
            return None
        if not resolved.exists():
            LOGGER.debug("Docling output JSON missing: %s", resolved)
            return None
        return resolved

    def _materialise_from_json(self, *, json_path: Path, page_number: int, fallback_dir: Path | None) -> Path | None:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        doc_payload = payload.get("docling_document", payload)
        pages = doc_payload.get("pages")
        page_entry: dict[str, Any] | None = None

        if isinstance(pages, dict):
            candidate = pages.get(str(page_number)) or pages.get(page_number)
            if isinstance(candidate, dict):
                page_entry = candidate
        elif isinstance(pages, list):
            for entry in pages:
                if not isinstance(entry, dict):
                    continue
                entry_page = entry.get("page_no")
                if entry_page == page_number or str(entry_page) == str(page_number):
                    page_entry = entry
                    break

        if page_entry is None:
            return None

        image_entry = page_entry.get("image")
        if not isinstance(image_entry, dict):
            return None
        uri = image_entry.get("uri")
        mimetype = image_entry.get("mimetype", "image/png")
        if not isinstance(uri, str):
            return None

        if fallback_dir is not None:
            target_dir = self._within_docling_root(fallback_dir) or json_path.parent
        else:
            target_dir = json_path.parent

        target_dir.mkdir(parents=True, exist_ok=True)

        extension = "png"
        if isinstance(mimetype, str) and "/" in mimetype:
            extension = mimetype.split("/", 1)[1]
        target = target_dir / f"page-{page_number}.{extension}"

        if uri.startswith("data:"):
            _, encoded = uri.split(",", 1)
            target.write_bytes(base64.b64decode(encoded))
            return target

        if uri.startswith("file:"):
            referenced = Path(uri[5:])
            referenced_bytes = referenced.read_bytes()
            target.write_bytes(referenced_bytes)
            return target

        return None

    def _within_docling_root(self, path: Path) -> Path | None:
        try:
            resolved = path.resolve()
        except FileNotFoundError:
            resolved = path.resolve(strict=False)
        docling_root = self.storage.docling_output_dir.resolve()
        if docling_root in resolved.parents or resolved == docling_root:
            return resolved
        return None

    def mimetype_for(self, path: Path) -> str:
        """Return an appropriate mimetype for a resolved preview image."""

        guessed, _ = mimetypes.guess_type(str(path))
        if isinstance(guessed, str):
            return guessed
        return "application/octet-stream"


@lru_cache(maxsize=1)
def get_locator(storage: StorageSettings) -> DoclingImageLocator:
    """Return a cached locator instance for the provided storage configuration."""

    return DoclingImageLocator(storage=storage)


__all__ = ["DoclingImageLocator", "get_locator"]
