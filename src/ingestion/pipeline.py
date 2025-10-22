"""Ingestion pipeline utilities for parsing, chunking and embedding documents."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .exceptions import IngestionError
from ..infrastructure.database import IngestionJob
from ..infrastructure.embeddings.base import EmbeddingClient
from ..infrastructure.repositories.document_repo import DocumentRepository

LOGGER = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf", ".json"}


def _normalise_value(value: Any) -> object:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(key): _normalise_value(val) for key, val in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_normalise_value(item) for item in value]
    return str(value)


def _sanitize_metadata(metadata: dict[str, Any]) -> dict[str, object]:
    return {str(key): _normalise_value(value) for key, value in metadata.items()}


def _extract_metadata(raw: Any) -> dict[str, object]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        items = raw.items()
    elif hasattr(raw, "__dict__"):
        items = vars(raw).items()
    else:
        return {}
    return _sanitize_metadata({key: value for key, value in items if not str(key).startswith("_")})


@dataclass(slots=True)
class ParsedPage:
    """Parsed representation of a single document page."""

    number: int
    content: str
    metadata: dict[str, object]


@dataclass(slots=True)
class ParsedDocument:
    """Representation of a parsed document ready for chunking."""

    title: str
    pages: list[ParsedPage]
    metadata: dict[str, object]


@dataclass(slots=True)
class ChunkPayload:
    """Chunk ready for embedding and persistence."""

    text: str
    metadata: dict[str, object]


class DocumentParser(Protocol):
    """Protocol for document parsing backends."""

    async def parse(self, path: Path) -> list[ParsedDocument]:
        """Parse the given path into parsed documents."""


def _extract_document_text(document: Any, path: Path) -> str:
    if hasattr(document, "export_to_text"):
        try:
            return str(document.export_to_text())
        except Exception:  # pragma: no cover - defensive
            LOGGER.debug("export_to_text failed for %s", path, exc_info=True)
    if hasattr(document, "to_text"):
        try:
            return str(document.to_text())
        except Exception:  # pragma: no cover - defensive
            LOGGER.debug("to_text failed for %s", path, exc_info=True)
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except UnicodeDecodeError as exc:  # pragma: no cover - depends on input
        raise IngestionError(f"Unable to read {path} as UTF-8 text") from exc


def _extract_page_text(page: Any) -> str:
    for attr in ("text", "content", "plain_text"):
        value = getattr(page, attr, None)
        if isinstance(value, str) and value.strip():
            return value
    for attr in ("export_to_text", "to_text"):
        method = getattr(page, attr, None)
        if callable(method):
            try:
                value = method()
            except Exception:  # pragma: no cover - defensive
                continue
            if isinstance(value, str) and value.strip():
                return value
    return ""


class DoclingParser:
    """Parse documents using Docling when available."""

    def __init__(self) -> None:
        try:
            from docling.document_converter import DocumentConverter
        except Exception:  # pragma: no cover - optional dependency resolution
            LOGGER.warning("Docling not available, falling back to plain text parsing")
            self._converter = None
            self._document_input = None
        else:
            try:  # pragma: no cover - import resolution depends on docling version
                from docling.models.input import DocumentInput  # type: ignore[attr-defined]
            except Exception:  # pragma: no cover - optional dependency resolution
                try:
                    from docling.models import DocumentInput  # type: ignore[attr-defined]
                except Exception:
                    LOGGER.warning("Docling DocumentInput model missing, using plaintext fallback")
                    self._converter = None
                    self._document_input = None
                else:
                    from docling.pipeline.standard import StandardPipeline  # type: ignore[attr-defined]
                    self._converter = DocumentConverter(pipeline=StandardPipeline())
                    self._document_input = DocumentInput
            else:
                from docling.pipeline.standard import StandardPipeline  # type: ignore[attr-defined]
                self._converter = DocumentConverter(pipeline=StandardPipeline())
                self._document_input = DocumentInput

    async def parse(self, path: Path) -> list[ParsedDocument]:
        if self._converter is None:
            LOGGER.debug("Reading %s as plaintext", path)
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except UnicodeDecodeError as exc:  # pragma: no cover - depends on input
                raise IngestionError(f"Unable to read {path} as UTF-8 text") from exc
            metadata = _sanitize_metadata({"source_path": str(path), "title": path.stem})
            page = ParsedPage(number=1, content=content, metadata=metadata)
            return [ParsedDocument(title=path.stem, pages=[page], metadata=metadata)]

        def _convert() -> list[ParsedDocument]:
            result = self._converter.convert(self._document_input(file_path=str(path)))
            document = result.document
            title = None
            metadata_obj = getattr(document, "metadata", None)
            if metadata_obj is not None:
                title = getattr(metadata_obj, "title", None)
            if not title:
                title = getattr(document, "title", None)
            title = title or path.stem

            document_metadata: dict[str, object] = {"source_path": str(path), "title": title}
            document_metadata.update(_extract_metadata(getattr(result, "metadata", None)))
            document_metadata.update(_extract_metadata(metadata_obj))
            document_metadata = _sanitize_metadata(document_metadata)

            pages: list[ParsedPage] = []
            raw_pages = []
            if hasattr(result, "pages"):
                raw_pages = getattr(result, "pages") or []
            elif hasattr(document, "pages"):
                raw_pages = getattr(document, "pages") or []

            for index, page in enumerate(raw_pages, start=1):
                page_text = _extract_page_text(page)
                if not page_text.strip():
                    continue
                raw_number = getattr(page, "page_no", None) or getattr(page, "number", None)
                try:
                    number = int(raw_number) if raw_number is not None else index
                except (TypeError, ValueError):
                    number = index
                page_meta: dict[str, object] = {
                    "source_path": str(path),
                    "document_title": title,
                }
                page_meta.update(_extract_metadata(getattr(page, "metadata", None)))
                page_meta.update(_extract_metadata(getattr(page, "attrs", None)))
                pages.append(
                    ParsedPage(
                        number=number,
                        content=page_text,
                        metadata=_sanitize_metadata(page_meta),
                    )
                )

            if not pages:
                content = _extract_document_text(document, path)
                metadata = _sanitize_metadata({"source_path": str(path), "title": title})
                pages.append(ParsedPage(number=1, content=content, metadata=metadata))

            return [ParsedDocument(title=title, pages=pages, metadata=document_metadata)]

        return await asyncio.to_thread(_convert)


class DocumentIngestionPipeline:
    """Coordinate the end-to-end ingestion process."""

    def __init__(
        self,
        repository: DocumentRepository,
        parser: DocumentParser,
        embedder: EmbeddingClient,
        *,
        chunk_size: int = 200,
        chunk_overlap: int = 40,
        allowed_extensions: set[str] | None = None,
    ) -> None:
        self.repository = repository
        self.parser = parser
        self.embedder = embedder
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.allowed_extensions = allowed_extensions or SUPPORTED_EXTENSIONS

    async def run(self, job: IngestionJob) -> None:
        paths = self._collect_sources(job.source)
        if not paths:
            raise IngestionError(f"No documents found at source: {job.source}")

        for path in paths:
            LOGGER.info("Parsing document %s", path)
            parsed_documents = await self.parser.parse(path)
            for parsed in parsed_documents:
                document_metadata = dict(parsed.metadata)
                document_metadata["ingestion_job_id"] = job.id
                document_metadata = _sanitize_metadata(document_metadata)
                document = await self.repository.create_document(
                    title=parsed.title or path.stem,
                    source_path=str(path),
                    collection_name=job.collection_name,
                    metadata=document_metadata,
                    job=job,
                )

                chunk_payloads = self._prepare_chunks(parsed, document.id, path, job)
                if not chunk_payloads:
                    LOGGER.debug("Document %s produced no chunks", path)
                    continue

                embeddings = await self.embedder.embed([chunk.text for chunk in chunk_payloads])
                total_chunks = len(chunk_payloads)
                for chunk, vector in zip(chunk_payloads, embeddings):
                    chunk.metadata.setdefault("chunk_count", total_chunks)
                    await self.repository.add_chunk(
                        document_id=document.id,
                        content=chunk.text,
                        embedding_model=getattr(self.embedder, "model_name", None),
                        embedding=vector,
                        metadata=_sanitize_metadata(chunk.metadata),
                    )
                await self.repository.commit()

    def _prepare_chunks(
        self,
        parsed: ParsedDocument,
        document_id: str,
        path: Path,
        job: IngestionJob,
    ) -> list[ChunkPayload]:
        chunk_payloads: list[ChunkPayload] = []
        chunk_index = 0
        for page in parsed.pages:
            for page_chunk_index, (chunk_text, start_word, end_word) in enumerate(self._chunk_text(page.content), start=1):
                if not chunk_text.strip():
                    continue
                chunk_index += 1
                chunk_metadata: dict[str, object] = {
                    "document_id": document_id,
                    "document_title": parsed.title,
                    "source_path": str(path),
                    "collection_name": job.collection_name,
                    "ingestion_job_id": job.id,
                    "page_number": page.number,
                    "page_chunk_index": page_chunk_index,
                    "chunk_index": chunk_index,
                    "word_start": start_word,
                    "word_end": end_word,
                }
                if parsed.metadata:
                    chunk_metadata["document_metadata"] = parsed.metadata
                if page.metadata:
                    chunk_metadata["page_metadata"] = page.metadata
                chunk_payloads.append(ChunkPayload(text=chunk_text, metadata=chunk_metadata))
        return chunk_payloads

    def _collect_sources(self, source: str) -> list[Path]:
        path = Path(source).expanduser().resolve()
        if path.is_file() and self._is_supported(path):
            return [path]
        if path.is_dir():
            return [p for p in path.rglob("*") if p.is_file() and self._is_supported(p)]
        raise IngestionError(f"Source {source} does not exist")

    def _is_supported(self, path: Path) -> bool:
        return path.suffix.lower() in self.allowed_extensions

    def _chunk_text(self, text: str) -> list[tuple[str, int, int]]:
        words = text.split()
        if not words:
            return []
        step = max(self.chunk_size - self.chunk_overlap, 1)
        chunks: list[tuple[str, int, int]] = []
        for start in range(0, len(words), step):
            end = min(start + self.chunk_size, len(words))
            chunk_words = words[start:end]
            if not chunk_words:
                continue
            chunks.append((" ".join(chunk_words), start, end))
        return chunks


__all__ = [
    "ChunkPayload",
    "DocumentIngestionPipeline",
    "DoclingParser",
    "ParsedDocument",
    "ParsedPage",
]
