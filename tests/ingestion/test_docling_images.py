from __future__ import annotations

import base64
import json
from pathlib import Path

from src.config import StorageSettings
from src.ingestion.docling_images import DoclingImageLocator


SAMPLE_PIXEL = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/w8AAn8B9t4S3QAAAABJRU5ErkJggg=="
)


def test_locator_returns_existing_image(tmp_path: Path) -> None:
    storage_dir = tmp_path / "docling"
    cache_dir = storage_dir / "hash"
    cache_dir.mkdir(parents=True)
    page_image = cache_dir / "page-1.png"
    page_image.write_bytes(b"png-data")

    locator = DoclingImageLocator(storage=StorageSettings(docling_output_dir=storage_dir))
    resolved = locator.locate_from_metadata({"docling_hash": "hash"}, 1)

    assert resolved == page_image


def test_locator_materialises_from_json(tmp_path: Path) -> None:
    storage_dir = tmp_path / "docling"
    cache_dir = storage_dir / "hash"
    cache_dir.mkdir(parents=True)
    json_path = cache_dir / "hash.json"
    json_payload = {
        "pages": {
            "1": {
                "page_no": 1,
                "image": {
                    "uri": f"data:image/png;base64,{SAMPLE_PIXEL}",
                    "mimetype": "image/png",
                },
            }
        }
    }
    json_path.write_text(json.dumps(json_payload), encoding="utf-8")

    locator = DoclingImageLocator(storage=StorageSettings(docling_output_dir=storage_dir))
    metadata = {"docling_hash": "hash", "docling_output": str(json_path)}

    resolved = locator.locate_from_metadata(metadata, 1)

    assert resolved is not None
    assert resolved.exists()
    assert resolved.read_bytes() == base64.b64decode(SAMPLE_PIXEL)


def test_locator_rejects_outside_directory(tmp_path: Path) -> None:
    storage_dir = tmp_path / "docling"
    storage_dir.mkdir(parents=True)
    locator = DoclingImageLocator(storage=StorageSettings(docling_output_dir=storage_dir))

    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    metadata = {"image_dir": str(outside_dir)}

    resolved = locator.locate_from_metadata(metadata, 1)

    assert resolved is None
