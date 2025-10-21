"""Ingestion pipeline utilities for parsing, chunking and embedding documents."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .exceptions import IngestionError
from ..infrastructure.database import IngestionJob
from ..infrastructure.embeddings.base import EmbeddingClient
from ..infrastructure.repositories.document_repo import DocumentRepository

LOGGER = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf", ".json"}


@dataclass(slots=True)
class ParsedDocument:
    """Representation of a parsed document ready for chunking."""

    title: str
    content: str
    metadata: dict[str, object]


class DocumentParser(Protocol):
    """Protocol for document parsing backends."""

    async def parse(self, path: Path) -> list[ParsedDocument]:
        """Parse the given path into parsed documents."""


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
            return [ParsedDocument(title=path.stem, content=content, metadata={"source_path": str(path)})]

        def _convert() -> list[ParsedDocument]:
            result = self._converter.convert(self._document_input(file_path=str(path)))
            document = result.document
            if hasattr(document, "export_to_text"):
                content = document.export_to_text()
            elif hasattr(document, "to_text"):
                content = document.to_text()
            else:  # pragma: no cover - defensive
                content = path.read_text(encoding="utf-8", errors="ignore")
            metadata_obj = getattr(document, "metadata", None)
            title = getattr(metadata_obj, "title", None) if metadata_obj else None
            if not title:
                title = getattr(document, "title", None)
            title = title or path.stem
            metadata: dict[str, object] = {"source_path": str(path)}
            if hasattr(result, "metadata") and isinstance(result.metadata, dict):
                metadata.update(result.metadata)
            return [ParsedDocument(title=title, content=content, metadata=metadata)]

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
                document = await self.repository.create_document(
                    title=parsed.title or path.stem,
                    source_path=str(path),
                    collection_name=job.collection_name,
                    metadata={**parsed.metadata, "ingestion_job_id": job.id},
                    job=job,
                )
                chunks = list(self._chunk_text(parsed.content))
                if not chunks:
                    LOGGER.debug("Document %s produced no chunks", path)
                    continue
                embeddings = await self.embedder.embed(chunks)
                for chunk_text, vector in zip(chunks, embeddings):
                    await self.repository.add_chunk(
                        document_id=document.id,
                        content=chunk_text,
                        embedding_model=getattr(self.embedder, "model_name", None),
                        embedding=vector,
                    )
                await self.repository.commit()

    def _collect_sources(self, source: str) -> list[Path]:
        path = Path(source).expanduser().resolve()
        if path.is_file() and self._is_supported(path):
            return [path]
        if path.is_dir():
            return [p for p in path.rglob("*") if p.is_file() and self._is_supported(p)]
        raise IngestionError(f"Source {source} does not exist")

    def _is_supported(self, path: Path) -> bool:
        return path.suffix.lower() in self.allowed_extensions

    def _chunk_text(self, text: str) -> list[str]:
        words = text.split()
        if not words:
            return []
        step = max(self.chunk_size - self.chunk_overlap, 1)
        chunks: list[str] = []
        for start in range(0, len(words), step):
            end = start + self.chunk_size
            chunk_words = words[start:end]
            if not chunk_words:
                continue
            chunks.append(" ".join(chunk_words))
        return chunks


__all__ = ["DocumentIngestionPipeline", "DoclingParser", "ParsedDocument"]
