"""Docling driven ingestion pipeline."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

from ..config import DoclingSettings, StorageSettings
from ..infrastructure.database import (
    IngestionEvent,
    IngestionEventStatus,
    IngestionJob,
    IngestionStep,
)
from ..infrastructure.embeddings.base import EmbeddingClient
from ..infrastructure.repositories.document_repo import DocumentRepository
from .exceptions import IngestionError

LOGGER = logging.getLogger(__name__)

_DATA_IMAGE_MD_PATTERN = re.compile(r"!\[[^\]]*]\(\s*data:image[^)]+\)", re.IGNORECASE)
_DATA_IMAGE_TAG_PATTERN = re.compile(r"<img[^>]+src=[\"']data:image[^\"']+[\"'][^>]*>", re.IGNORECASE)
_DATA_URI_PATTERN = re.compile(r"data:image/[a-z0-9.+-]+;base64,[^\s)\"'>]+", re.IGNORECASE)
_HTML_COMMENT_PATTERN = re.compile(r"<!--.*?-->", re.DOTALL)
_EMPTY_IMAGE_MARKDOWN_PATTERN = re.compile(r"!\[[^\]]*]\(\s*\)", re.IGNORECASE)
_HTML_TAG_PATTERN = re.compile(r"<img[^>]*>", re.IGNORECASE)


@dataclass(slots=True)
class ParsedPage:
    """Represents a single parsed page."""

    number: int
    content: str
    metadata: dict[str, object]


@dataclass(slots=True)
class ParsedDocument:
    """Docling parsing result."""

    title: str
    pages: list[ParsedPage]
    metadata: dict[str, object]
    docling_document: Any | None = None


@dataclass(slots=True)
class ChunkPayload:
    """Chunk ready for persistence and embedding."""

    content: str
    metadata: dict[str, object]


def _sanitize_page_text(text: str) -> str:
    """Remove inline base64 image payloads and tidy whitespace."""

    if not text:
        return ""
    cleaned = _DATA_IMAGE_MD_PATTERN.sub(" ", text)
    cleaned = _DATA_IMAGE_TAG_PATTERN.sub(" ", cleaned)
    cleaned = _DATA_URI_PATTERN.sub(" ", cleaned)
    cleaned = _HTML_COMMENT_PATTERN.sub(" ", cleaned)
    cleaned = _EMPTY_IMAGE_MARKDOWN_PATTERN.sub(" ", cleaned)
    cleaned = _HTML_TAG_PATTERN.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _split_long_tokens(tokens: Sequence[str], max_length: int) -> list[str]:
    """Ensure tokens fit within max length by splitting oversized entries."""

    if max_length <= 0:
        raise ValueError("max_length must be positive")
    pieces: list[str] = []
    for token in tokens:
        if len(token) <= max_length:
            pieces.append(token)
            continue
        start = 0
        while start < len(token):
            end = min(len(token), start + max_length)
            pieces.append(token[start:end])
            start = end
    return pieces


class DoclingParser:
    """Handle Docling based parsing and caching."""

    def __init__(self, *, storage_settings: StorageSettings, docling_settings: DoclingSettings) -> None:
        self.storage = storage_settings
        self.docling_settings = docling_settings
        self._hash_index_lock = asyncio.Lock()

    async def parse(self, source: str | Path) -> ParsedDocument:
        if not self.docling_settings.enabled:
            raise IngestionError("Docling parsing is disabled by configuration")

        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(path)

        file_hash = self._create_file_hash(path)
        cache_dir = self.storage.docling_output_dir / file_hash
        cache_dir.mkdir(parents=True, exist_ok=True)
        json_path = cache_dir / f"{file_hash}.json"

        cached_document = None
        if json_path.exists():
            try:
                cached_document = self._load_cached_document(json_path)
            except Exception as exc:  # noqa: BLE001 - cache corruption
                LOGGER.warning("Failed to load cached Docling artefact %s: %s", json_path, exc)

        if cached_document is not None:
            return cached_document

        conversion_result = await self._run_conversion(path, cache_dir)
        docling_document = getattr(conversion_result, "document", None)
        if docling_document is None:
            raise IngestionError("Docling conversion did not produce a document.")

        pages = self._build_pages(conversion_result, cache_dir, file_hash, json_path)
        document_title = self._resolve_title(conversion_result, path)
        metadata: dict[str, object] = {
            "docling_hash": file_hash,
            "docling_output": str(json_path),
            "image_dir": str(cache_dir),
            "source_path": str(path),
            "page_count": len(pages),
        }
        parsed = ParsedDocument(
            title=document_title,
            pages=pages,
            metadata=metadata,
            docling_document=docling_document,
        )
        self._persist_cache(parsed, json_path)
        await self._update_hash_index(path, file_hash)
        return parsed

    async def _run_conversion(self, path: Path, cache_dir: Path) -> Any:
        """Execute Docling conversion in a worker thread."""

        try:
            from docling.document_converter import DocumentConverter, PdfFormatOption
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode
            from docling.datamodel.accelerator_options import AcceleratorOptions
        except ModuleNotFoundError as exc:  # pragma: no cover - guarded import
            raise IngestionError("Docling package is not installed. Install 'docling' to enable parsing.") from exc

        pipeline_options = PdfPipelineOptions(
            do_ocr=self.docling_settings.do_ocr,
            do_table_structure=self.docling_settings.do_table_structure,
            generate_page_images=self.docling_settings.generate_page_images,
            images_scale=self.docling_settings.image_scale,
        )
        pipeline_options.table_structure_options.mode = TableFormerMode(self.docling_settings.table_mode)
        pipeline_options.table_structure_options.do_cell_matching = self.docling_settings.table_cell_matching

        accel_kwargs: dict[str, object] = {"device": self.docling_settings.accelerator_device}
        if self.docling_settings.accelerator_num_threads > 0:
            accel_kwargs["num_threads"] = self.docling_settings.accelerator_num_threads
        pipeline_options.accelerator_options = AcceleratorOptions(**accel_kwargs)

        pdf_option = PdfFormatOption(pipeline_options=pipeline_options)
        converter = DocumentConverter(format_options={InputFormat.PDF: pdf_option})

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, converter.convert, path)

    @staticmethod
    def _load_cached_document(self, json_path: Path) -> ParsedDocument | None:
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

        doc_payload = payload.get("docling_document", payload)
        parsed_payload = payload.get("parsed_document")
        if parsed_payload is None:
            return None

        try:
            from docling_core.types.doc.document import DoclingDocument
        except ModuleNotFoundError as exc:  # pragma: no cover - guarded import
            raise IngestionError("Docling package is required to load cached artefacts.") from exc

        docling_document = DoclingDocument.model_validate(doc_payload)
        pages_data = parsed_payload.get("pages") or []
        pages: list[ParsedPage] = [
            ParsedPage(
                number=int(page_data.get("number", index + 1)),
                content=str(page_data.get("content", "")),
                metadata=dict(page_data.get("metadata", {})),
            )
            for index, page_data in enumerate(pages_data)
        ]
        metadata = dict(parsed_payload.get("metadata", {}))
        metadata["docling_output"] = str(json_path)
        for page in pages:
            page.metadata.setdefault("docling_output", str(json_path))
        title = str(parsed_payload.get("title") or Path(json_path).stem)
        return ParsedDocument(title=title, pages=pages, metadata=metadata, docling_document=docling_document)

    def _persist_cache(self, document: ParsedDocument, json_path: Path) -> None:
        docling_document = getattr(document, "docling_document", None)
        if docling_document is None:
            return
        doc_payload = docling_document.model_dump(mode="json")
        cache_payload = {
            "docling_document": doc_payload,
            "parsed_document": {
                "title": document.title,
                "metadata": document.metadata,
                "pages": [
                    {
                        "number": page.number,
                        "content": page.content,
                        "metadata": page.metadata,
                    }
                    for page in document.pages
                ],
            },
        }
        json_path.write_text(json.dumps(cache_payload, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def _resolve_title(conversion_result: Any, path: Path) -> str:
        document = getattr(conversion_result, "document", None)
        if document is not None:
            name = getattr(document, "name", None)
            if isinstance(name, str) and name.strip():
                return name.strip()
        return path.stem

    def _build_pages(
        self,
        conversion_result: Any,
        cache_dir: Path,
        file_hash: str,
        json_path: Path,
    ) -> list[ParsedPage]:
        try:
            from docling.utils.export import generate_multimodal_pages
        except ModuleNotFoundError:
            LOGGER.warning("Docling utilities not available; falling back to empty page content.")
            return []

        pages: list[ParsedPage] = []
        for entry in generate_multimodal_pages(conversion_result):
            content_text, content_md, _tokens, _cells, _segments, page = entry
            page_no = getattr(page, "page_no", len(pages) + 1)
            raw_text = content_md or content_text or ""
            sanitised = _sanitize_page_text(raw_text)
            metadata: dict[str, object] = {
                "page_number": page_no,
                "docling_hash": file_hash,
                "docling_output": str(json_path),
                "image_dir": str(cache_dir),
            }
            image_path = self._materialise_page_image(page, cache_dir, page_no)
            if image_path is not None:
                metadata["image_path"] = image_path.as_posix()
            pages.append(ParsedPage(number=page_no, content=sanitised, metadata=metadata))
        return pages

    @staticmethod
    def _materialise_page_image(page: Any, cache_dir: Path, page_no: int) -> Path | None:
        image_ref = getattr(page, "image", None)
        if image_ref is None:
            return None
        uri = getattr(image_ref, "uri", None)
        mimetype = getattr(image_ref, "mimetype", "image/png")
        if uri is None:
            return None

        ext = "png"
        if isinstance(mimetype, str) and "/" in mimetype:
            ext = mimetype.split("/", 1)[1]
        target = cache_dir / f"page-{page_no:04d}.{ext}"

        if isinstance(uri, Path):
            try:
                data = uri.read_bytes()
            except FileNotFoundError:
                return None
            target.write_bytes(data)
            return target

        uri_text = str(uri)
        if uri_text.startswith("data:"):
            try:
                _, payload = uri_text.split(",", 1)
                target.write_bytes(base64.b64decode(payload))
                return target
            except (ValueError, base64.binascii.Error):
                LOGGER.debug("Failed to decode inline image for page %s", page_no)
        elif uri_text.startswith("file:"):
            try:
                file_path = Path(uri_text[5:])
                target.write_bytes(file_path.read_bytes())
                return target
            except FileNotFoundError:
                LOGGER.debug("Referenced page image not found: %s", uri_text)
        return None

    async def _update_hash_index(self, path: Path, file_hash: str) -> None:
        index_path = self.storage.docling_hash_index
        async with self._hash_index_lock:
            mapping: dict[str, object] = {}
            if index_path.exists():
                try:
                    mapping = json.loads(index_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    LOGGER.warning("Docling hash index %s is corrupted; rebuilding.", index_path)
            mapping[str(path)] = {
                "hash": file_hash,
                "updated_at": datetime.utcnow().isoformat(timespec="seconds"),
            }
            index_path.parent.mkdir(parents=True, exist_ok=True)
            index_path.write_text(json.dumps(mapping, indent=2, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def _create_file_hash(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()


class DocumentIngestionPipeline:
    """End-to-end ingestion pipeline orchestrating parsing, chunking, and embedding."""

    def __init__(
        self,
        repository: DocumentRepository,
        parser: DoclingParser,
        embedder: EmbeddingClient,
        *,
        chunk_size: int = 1200,
        chunk_overlap: int = 150,
    ) -> None:
        self.repository = repository
        self.parser = parser
        self.embedder = embedder
        self.default_chunk_size = chunk_size
        self.default_chunk_overlap = chunk_overlap

    async def run(self, job: IngestionJob) -> None:
        source_paths = self._discover_sources(job.source)
        if not source_paths:
            raise IngestionError(f"No documents discovered at {job.source}")

        produced_any_chunks = False
        for path in source_paths:
            LOGGER.info("Ingesting document %s for job %s", path, job.id)
            parse_event = await self._ensure_event(job, IngestionStep.docling_parse, document_path=str(path))
            await self._mark_event_running(parse_event)

            parsed = await self.parser.parse(path)
            document = await self.repository.create_document(
                title=parsed.title or path.stem,
                source_path=str(path),
                collection_name=job.collection.name if job.collection else "default",
                metadata=parsed.metadata,
                job=job,
            )

            await self._mark_event_success(
                parse_event,
                document=document,
                detail={"pages": len(parsed.pages), "docling_hash": parsed.metadata.get("docling_hash")},
            )

            chunk_event = await self._ensure_event(job, IngestionStep.chunk_assembly, document=document, document_path=str(path))
            await self._mark_event_running(chunk_event, document=document)

            chunk_size = job.chunk_size or self.default_chunk_size
            chunk_overlap = job.chunk_overlap or self.default_chunk_overlap
            chunks = self._prepare_chunks(
                parsed,
                document_id=document.id,
                path=Path(path),
                job=job,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )

            if not chunks:
                detail = {
                    "chunks": 0,
                    "chunk_size": chunk_size,
                    "chunk_overlap": chunk_overlap,
                    "reason": "Document did not contain chunkable content.",
                }
                await self._mark_event_failure(chunk_event, document=document, detail=detail)
                raise IngestionError("No chunks produced for document")

            await self._mark_event_success(
                chunk_event,
                document=document,
                detail={"chunks": len(chunks), "chunk_size": chunk_size, "chunk_overlap": chunk_overlap},
            )
            produced_any_chunks = True

            embed_event = await self._ensure_event(job, IngestionStep.embedding_indexing, document=document, document_path=str(path))
            await self._mark_event_running(embed_event, document=document)

            embeddings = await self._embed_chunks(chunks)
            await self._persist_chunks(document_id=document.id, chunks=chunks, embeddings=embeddings)
            await self._mark_event_success(
                embed_event,
                document=document,
                detail={"embedded_chunks": len(embeddings), "embedding_model": getattr(self.embedder, "model_name", "unknown")},
            )

            citation_event = await self._ensure_event(job, IngestionStep.citation_enrichment, document=document, document_path=str(path))
            await self._mark_event_running(citation_event, document=document)
            await self._mark_event_success(
                citation_event,
                document=document,
                detail={"citations": self._build_citation_payload(chunks, document.id)},
            )

        if not produced_any_chunks:
            raise IngestionError("Ingestion completed without producing any chunks.")

    def _discover_sources(self, source: str) -> list[Path]:
        path = Path(source)
        if path.is_file():
            return [path]
        if path.is_dir():
            return sorted(item for item in path.iterdir() if item.is_file())
        raise FileNotFoundError(source)

    async def _ensure_event(
        self,
        job: IngestionJob,
        step: IngestionStep,
        *,
        document: Any | None = None,
        document_path: str | None = None,
    ) -> IngestionEvent:
        existing = await self.repository.get_event_for_step(job.id, step)
        if existing:
            return existing
        return await self.repository.create_event(
            job_id=job.id,
            step=step,
            status=IngestionEventStatus.pending,
            document_id=getattr(document, "id", None),
            document_title=getattr(document, "title", None),
            document_path=document_path,
        )

    async def _mark_event_running(self, event: IngestionEvent, *, document: Any | None = None) -> None:
        await self.repository.update_event_status(
            event,
            status=IngestionEventStatus.running,
            document_id=getattr(document, "id", None),
            document_title=getattr(document, "title", None),
        )
        await self.repository.commit()

    async def _mark_event_success(
        self,
        event: IngestionEvent,
        *,
        document: Any | None = None,
        detail: dict[str, object] | None = None,
    ) -> None:
        await self.repository.update_event_status(
            event,
            status=IngestionEventStatus.success,
            detail=detail,
            document_id=getattr(document, "id", None),
            document_title=getattr(document, "title", None),
        )
        await self.repository.commit()

    async def _mark_event_failure(
        self,
        event: IngestionEvent,
        *,
        document: Any | None = None,
        detail: dict[str, object] | None = None,
    ) -> None:
        await self.repository.update_event_status(
            event,
            status=IngestionEventStatus.failed,
            detail=detail,
            document_id=getattr(document, "id", None),
            document_title=getattr(document, "title", None),
        )
        await self.repository.commit()

    def _prepare_chunks(
        self,
        document: ParsedDocument,
        *,
        document_id: str,
        path: Path,
        job: IngestionJob,
        chunk_size: int,
        chunk_overlap: int,
    ) -> list[ChunkPayload]:
        page_lookup = {page.number: page for page in document.pages}
        base_metadata = {
            "document_id": document_id,
            "document_title": document.title,
            "source_path": str(path),
            "collection": job.collection.name if job.collection else None,
            "ingestion_job_id": job.id,
            "docling_hash": document.metadata.get("docling_hash"),
        }

        if document.docling_document is not None:
            try:
                chunks = self._chunk_with_hybrid(
                    document,
                    base_metadata=base_metadata,
                    page_lookup=page_lookup,
                    document_id=document_id,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                )
            except IngestionError:
                chunks = self._chunk_with_fallback(
                    document,
                    base_metadata=base_metadata,
                    page_lookup=page_lookup,
                    document_id=document_id,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                )
        else:
            chunks = self._chunk_with_fallback(
                document,
                base_metadata=base_metadata,
                page_lookup=page_lookup,
                document_id=document_id,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )

        total = len(chunks)
        for index, chunk in enumerate(chunks):
            chunk.metadata.setdefault("chunk_index", index)
            chunk.metadata.setdefault("chunk_total", total)
        return chunks

    def _chunk_with_hybrid(
        self,
        document: ParsedDocument,
        *,
        base_metadata: dict[str, object],
        page_lookup: dict[int, ParsedPage],
        document_id: str,
        chunk_size: int,
        chunk_overlap: int,
    ) -> list[ChunkPayload]:
        try:
            from docling.chunking import HybridChunker
        except ModuleNotFoundError as exc:  # pragma: no cover - guarded import
            raise IngestionError("Docling chunking extras are required for hybrid chunking") from exc
        except RuntimeError as exc:  # missing optional extras such as semchunk
            raise IngestionError(str(exc)) from exc

        hybrid_chunker = HybridChunker()
        doc_chunks = list(hybrid_chunker.chunk(document.docling_document))  # type: ignore[arg-type]
        result: list[ChunkPayload] = []
        for doc_chunk in doc_chunks:
            text = getattr(doc_chunk, "text", "")
            if not isinstance(text, str):
                continue
            sanitised = _sanitize_page_text(text)
            if not sanitised:
                continue

            slices = self._slice_text(sanitised, chunk_size, chunk_overlap)
            page_numbers = self._extract_page_numbers(doc_chunk)
            primary_page = page_numbers[0] if page_numbers else None
            parsed_page = page_lookup.get(primary_page) if primary_page is not None else None
            page_metadata = dict(parsed_page.metadata) if parsed_page else {}

            for content, start, end in slices:
                metadata = {
                    **base_metadata,
                    "page_number": primary_page,
                    "page_numbers": page_numbers,
                    "character_start": start,
                    "character_end": end,
                    "page_metadata": page_metadata,
                    "docling_chunk": self._safe_export_meta(doc_chunk),
                }
                metadata["citation"] = self._build_citation(
                    document_id=document_id,
                    pages=[page for page in (page_lookup.get(number) for number in page_numbers) if page is not None],
                    page_numbers=page_numbers,
                    fallback_page=primary_page,
                    docling_hash=base_metadata.get("docling_hash"),
                )
                result.append(ChunkPayload(content=content, metadata=metadata))
        return result

    def _chunk_with_fallback(
        self,
        document: ParsedDocument,
        *,
        base_metadata: dict[str, object],
        page_lookup: dict[int, ParsedPage],
        document_id: str,
        chunk_size: int,
        chunk_overlap: int,
    ) -> list[ChunkPayload]:
        result: list[ChunkPayload] = []
        for page in document.pages:
            sanitised = _sanitize_page_text(page.content)
            if not sanitised:
                continue
            page_metadata = dict(page.metadata)
            slices = self._slice_text(sanitised, chunk_size, chunk_overlap)
            for content, start, end in slices:
                metadata = {
                    **base_metadata,
                    "page_number": page.number,
                    "page_numbers": [page.number],
                    "character_start": start,
                    "character_end": end,
                    "page_metadata": page_metadata,
                }
                metadata["citation"] = self._build_citation(
                    document_id=document_id,
                    pages=[page],
                    page_numbers=[page.number],
                    fallback_page=page.number,
                    docling_hash=base_metadata.get("docling_hash"),
                )
                result.append(ChunkPayload(content=content, metadata=metadata))
        return result

    @staticmethod
    def _safe_export_meta(doc_chunk: Any) -> dict[str, object] | None:
        meta = getattr(doc_chunk, "meta", None)
        if meta is None:
            return None
        export = getattr(meta, "export_json_dict", None)
        if callable(export):
            try:
                return export()
            except Exception:  # noqa: BLE001 - defensive
                LOGGER.debug("Failed to export doc chunk metadata", exc_info=True)
        return None

    @staticmethod
    def _slice_text(text: str, chunk_size: int, chunk_overlap: int) -> list[tuple[str, int, int]]:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if chunk_overlap < 0 or chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be between 0 and chunk_size")
        if not text:
            return []

        segments: list[tuple[str, int, int]] = []
        start = 0
        length = len(text)
        while start < length:
            end = min(length, start + chunk_size)
            segments.append((text[start:end], start, end))
            if end == length:
                break
            start = end - chunk_overlap
        return segments

    @staticmethod
    def _extract_page_numbers(doc_chunk: Any) -> list[int]:
        meta = getattr(doc_chunk, "meta", None)
        if meta is None:
            return []
        doc_items = getattr(meta, "doc_items", []) or []
        page_numbers: set[int] = set()
        for item in doc_items:
            prov_list = getattr(item, "prov", []) or []
            for prov in prov_list:
                page = getattr(prov, "page_no", getattr(prov, "page", None))
                if page is not None:
                    page_numbers.add(int(page))
        return sorted(page_numbers)

    @staticmethod
    def _build_citation(
        *,
        document_id: str,
        pages: Sequence[ParsedPage],
        page_numbers: Sequence[int] | None,
        fallback_page: int | None,
        docling_hash: object,
    ) -> dict[str, object]:
        citation: dict[str, object] = {}

        ordered_numbers: list[int] = []
        if page_numbers:
            for candidate in page_numbers:
                try:
                    number = int(candidate)
                except (TypeError, ValueError):
                    continue
                if number not in ordered_numbers:
                    ordered_numbers.append(number)
        if fallback_page is not None and fallback_page not in ordered_numbers:
            ordered_numbers.append(fallback_page)

        page_map: dict[int, ParsedPage] = {}
        for page in pages:
            try:
                page_number = int(page.number)
            except (TypeError, ValueError):
                continue
            page_map[page_number] = page
            if page_number not in ordered_numbers:
                ordered_numbers.append(page_number)

        page_entries: list[dict[str, object]] = []
        for number in ordered_numbers:
            entry: dict[str, object] = {
                "page_number": number,
                "image_url": f"/ingestion/documents/{document_id}/pages/{number}/preview",
            }
            page = page_map.get(number)
            if page is not None:
                image_path = page.metadata.get("image_path")
                if image_path:
                    entry["image_path"] = image_path
            page_entries.append(entry)

        primary_page_number: int | None = ordered_numbers[0] if ordered_numbers else None
        if primary_page_number is not None:
            citation["page_number"] = primary_page_number
            citation["image_url"] = f"/ingestion/documents/{document_id}/pages/{primary_page_number}/preview"

        if docling_hash is not None:
            citation["docling_hash"] = docling_hash

        if page_entries:
            citation["pages"] = page_entries
            if primary_page_number is not None:
                primary_entry = next(
                    (entry for entry in page_entries if entry["page_number"] == primary_page_number),
                    page_entries[0],
                )
            else:
                primary_entry = page_entries[0]
            image_path = primary_entry.get("image_path")
            if image_path:
                citation["image_path"] = image_path

        return citation

    @staticmethod
    def _build_citation_payload(chunks: Sequence[ChunkPayload], document_id: str) -> list[dict[str, object]]:
        payload: list[dict[str, object]] = []
        for chunk in chunks:
            citation = chunk.metadata.get("citation")
            if isinstance(citation, dict):
                payload.append(
                    {
                        "chunk_index": chunk.metadata.get("chunk_index"),
                        "page_number": citation.get("page_number"),
                        "image_url": citation.get("image_url"),
                        "image_path": citation.get("image_path"),
                        "docling_hash": citation.get("docling_hash"),
                        "pages": citation.get("pages"),
                    }
                )
        return payload

    async def _embed_chunks(self, chunks: Sequence[ChunkPayload]) -> list[list[float]]:
        texts = [chunk.content for chunk in chunks]
        return await self.embedder.embed(texts)

    async def _persist_chunks(
        self,
        *,
        document_id: str,
        chunks: Sequence[ChunkPayload],
        embeddings: Sequence[Sequence[float]],
    ) -> None:
        if len(chunks) != len(embeddings):
            raise IngestionError("Embedding result length does not match chunk count")
        model_name = getattr(self.embedder, "model_name", None)
        for payload, vector in zip(chunks, embeddings, strict=True):
            await self.repository.add_chunk(
                document_id=document_id,
                content=payload.content,
                embedding=vector,
                embedding_model=model_name,
                metadata=payload.metadata,
            )
        await self.repository.commit()


__all__ = [
    "DocumentIngestionPipeline",
    "DoclingParser",
    "ParsedDocument",
    "ParsedPage",
    "ChunkPayload",
    "_sanitize_page_text",
    "_split_long_tokens",
]
