from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from pathlib import Path

from src.ingestion.pipeline import (
    DocumentIngestionPipeline,
    ParsedDocument,
    ParsedPage,
    _sanitize_page_text,
    _split_long_tokens,
)


def test_sanitize_page_text_removes_data_uri() -> None:
    text = (
        "Intro ![caption](data:image/png;base64,AAAA) middle "
        '<img src="data:image/png;base64,BBBB" alt="" /> '
        "data:image/png;base64,CCCC <!-- image --> end"
    )

    cleaned = _sanitize_page_text(text)

    assert cleaned == "Intro middle end"


def test_split_long_tokens_breaks_large_segments() -> None:
    long_word = "a" * 9000
    words = ["start", long_word, "end"]

    result = _split_long_tokens(words, max_length=2048)

    assert result[0] == "start"
    assert result[-1] == "end"
    # The long token should have been split into multiple pieces within bounds.
    assert all(len(piece) <= 2048 for piece in result[1:-1])
    reconstructed = "".join(result[1:-1])
    assert reconstructed == long_word


def test_prepare_chunks_includes_citation_image_url(tmp_path: Path) -> None:
    pipeline = DocumentIngestionPipeline(
        repository=MagicMock(),
        parser=MagicMock(),
        embedder=MagicMock(),
    )

    page_metadata = {
        "image_path": tmp_path.as_posix(),
        "docling_hash": "hash",
    }
    page = ParsedPage(number=1, content="Hello world", metadata=page_metadata)
    document = ParsedDocument(title="Doc", pages=[page], metadata={"docling_hash": "hash"})
    job = SimpleNamespace(
        id="job",
        collection=SimpleNamespace(name="default"),
        parameters=None,
    )

    chunks = pipeline._prepare_chunks(
        document,
        document_id="doc-1",
        path=Path("/tmp/doc.pdf"),
        job=job,
        chunk_size=50,
        chunk_overlap=0,
    )

    assert len(chunks) == 1
    citation = chunks[0].metadata.get("citation")
    assert isinstance(citation, dict)
    assert citation["image_path"] == tmp_path.as_posix()
    assert citation["docling_hash"] == "hash"
    assert citation["image_url"] == "/ingestion/documents/doc-1/pages/1/preview"
