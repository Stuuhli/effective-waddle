"""Ingestion pipeline utilities for parsing, chunking and embedding documents."""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .exceptions import IngestionError
from ..infrastructure.database import IngestionEvent, IngestionJob
from ..infrastructure.embeddings.base import EmbeddingClient
from ..infrastructure.repositories.document_repo import DocumentRepository
from ..config import DoclingSettings, StorageSettings, load_settings
from ..infrastructure.database import IngestionEventStatus, IngestionStep

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

    def __init__(
        self,
        storage_settings: StorageSettings | None = None,
        docling_settings: DoclingSettings | None = None,
    ) -> None:
        settings = load_settings()
        self._storage = storage_settings or settings.storage
        self._docling_settings = docling_settings or settings.docling

        if not self._docling_settings.enabled:
            LOGGER.warning("Docling parsing disabled via configuration, falling back to plain text parsing")
            self._converter = None
        else:
            try:
                from docling.datamodel.base_models import InputFormat
                from docling.datamodel.pipeline_options import (
                    AcceleratorDevice,
                    AcceleratorOptions,
                    PdfPipelineOptions,
                    TableFormerMode,
                )
                from docling.document_converter import DocumentConverter, PdfFormatOption
            except Exception:  # pragma: no cover - optional dependency resolution
                LOGGER.warning("Docling not available, falling back to plain text parsing")
                self._converter = None
            else:
                pdf_options = PdfPipelineOptions()
                pdf_options.do_ocr = self._docling_settings.do_ocr
                pdf_options.do_table_structure = self._docling_settings.do_table_structure
                if self._docling_settings.do_table_structure:
                    try:
                        table_mode = TableFormerMode[self._docling_settings.table_mode.upper()]
                    except KeyError:
                        LOGGER.warning(
                            "Unknown Docling table mode '%s', defaulting to ACCURATE.",
                            self._docling_settings.table_mode,
                        )
                        table_mode = TableFormerMode.ACCURATE
                    pdf_options.table_structure_options.mode = table_mode
                    pdf_options.table_structure_options.do_cell_matching = self._docling_settings.table_cell_matching
                pdf_options.generate_page_images = self._docling_settings.generate_page_images
                pdf_options.images_scale = self._docling_settings.image_scale

                device = (
                    AcceleratorDevice.CUDA
                    if self._docling_settings.accelerator_device.lower() == "cuda"
                    else AcceleratorDevice.CPU
                )
                accel_kwargs: dict[str, object] = {"device": device}
                if self._docling_settings.accelerator_num_threads > 0:
                    accel_kwargs["num_threads"] = self._docling_settings.accelerator_num_threads
                pdf_options.accelerator_options = AcceleratorOptions(**accel_kwargs)

                format_options = {
                    InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_options),
                }
                self._converter = DocumentConverter(format_options=format_options)

        self._docling_dir = Path(self._storage.docling_output_dir)
        self._hash_index_path = Path(self._storage.docling_hash_index)
        self._hash_index_path.parent.mkdir(parents=True, exist_ok=True)
        if not self._hash_index_path.exists():
            self._hash_index_path.write_text("{}", encoding="utf-8")

    def _load_hash_index(self) -> dict[str, str]:
        try:
            return json.loads(self._hash_index_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):  # pragma: no cover - defensive
            return {}

    def _save_hash_index(self, index: dict[str, str]) -> None:
        self._hash_index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _create_file_hash(path: Path) -> str:
        hasher = hashlib.sha256(usedforsecurity=False)
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    @staticmethod
    def _decode_image(uri: str) -> bytes | None:
        if not uri or not uri.startswith("data:image"):
            return None
        try:
            _, data = uri.split(",", 1)
        except ValueError:  # pragma: no cover - defensive
            return None
        try:
            return base64.b64decode(data)
        except base64.binascii.Error:  # pragma: no cover - defensive
            return None

    @staticmethod
    def _serialize_markdown(document: Any) -> str | None:
        try:
            from docling_core.transforms.serializer.markdown import MarkdownDocSerializer  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover - optional dependency resolution
            return None
        try:
            serializer = MarkdownDocSerializer(doc=document)
            serialized = serializer.serialize()
        except Exception:  # pragma: no cover - serialization defensive
            LOGGER.debug("Docling markdown serialization failed", exc_info=True)
            return None
        if isinstance(serialized, str):
            return serialized
        return getattr(serialized, "markdown", None) or getattr(serialized, "content", None)

    @staticmethod
    def _extract_section_summaries(document: Any) -> list[dict[str, object]]:
        try:
            from docling_core.types.doc.document import SectionHeaderItem  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover - optional dependency resolution
            return []
        sections: list[dict[str, object]] = []
        spans = getattr(document, "spans", []) or []
        for span in spans:
            item = getattr(span, "item", None)
            if not isinstance(item, SectionHeaderItem):
                continue
            heading = getattr(item, "orig", None) or getattr(item, "title", None)
            if not isinstance(heading, str):
                continue
            page_numbers: list[int] = []
            for prov in getattr(item, "prov", []) or []:
                page_no = getattr(prov, "page_no", None)
                if isinstance(page_no, int):
                    page_numbers.append(page_no)
            sections.append(
                {
                    "heading": heading.strip(),
                    "pages": sorted(set(page_numbers)),
                }
            )
        return sections

    async def parse(self, path: Path) -> list[ParsedDocument]:
        if self._converter is None:
            LOGGER.debug("Reading %s as plaintext", path)
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except UnicodeDecodeError as exc:  # pragma: no cover - depends on input
                raise IngestionError(f"Unable to read {path} as UTF-8 text") from exc
            metadata = _sanitize_metadata(
                {"source_path": str(path), "title": path.stem, "document_name": path.name}
            )
            page = ParsedPage(number=1, content=content, metadata=metadata)
            return [ParsedDocument(title=path.stem, pages=[page], metadata=metadata)]

        def _convert() -> list[ParsedDocument]:
            file_hash = self._create_file_hash(path)
            cache_dir = self._docling_dir / file_hash
            cache_dir.mkdir(parents=True, exist_ok=True)
            json_path = cache_dir / f"{file_hash}.json"
            metadata_path = cache_dir / "conversion-metadata.json"

            metadata_dump: dict[str, Any] = {}
            document: Any | None = None

            cache_hit = json_path.exists()
            if cache_hit:
                try:
                    from docling_core.types.doc.document import DoclingDocument  # type: ignore[attr-defined]

                    document = DoclingDocument.load_from_json(json_path)
                    if metadata_path.exists():
                        metadata_dump = json.loads(metadata_path.read_text(encoding="utf-8"))
                except Exception as exc:  # pragma: no cover - corrupted cache
                    LOGGER.warning("Failed to load cached Docling artefacts for %s: %s. Re-parsing.", path, exc)
                    document = None
                    metadata_dump = {}
                    cache_hit = False

            if document is None:
                result = self._converter.convert(str(path))
                document = result.document
                try:
                    document.save_as_json(json_path)  # type: ignore[attr-defined]
                except Exception:  # pragma: no cover - best effort persistence
                    LOGGER.debug("Unable to persist Docling JSON for %s", path, exc_info=True)
                try:
                    metadata_dump = result.model_dump()
                    metadata_path.write_text(
                        json.dumps(metadata_dump, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                except Exception:  # pragma: no cover - serialization guard
                    LOGGER.debug("Skipping Docling metadata persistence for %s", path, exc_info=True)
                    metadata_dump = {}

            hash_index = self._load_hash_index()
            if hash_index.get(str(path)) != file_hash:
                hash_index[str(path)] = file_hash
                self._save_hash_index(hash_index)

            title = None
            metadata_obj = getattr(document, "metadata", None)
            if metadata_obj is not None:
                title = getattr(metadata_obj, "title", None)
            if not title:
                title = getattr(document, "title", None)
            title = title or path.stem

            document_metadata: dict[str, object] = {
                "source_path": str(path),
                "title": title,
                "document_name": path.name,
                "docling_hash": file_hash,
                "docling_output": str(json_path),
                "image_dir": str(cache_dir),
                "docling_cache_hit": cache_hit,
            }
            document_metadata.update(_extract_metadata(metadata_dump.get("metadata")))
            document_metadata.update(_extract_metadata(metadata_dump.get("document")))
            document_metadata.update(_extract_metadata(metadata_obj))
            markdown_text = self._serialize_markdown(document)
            if markdown_text:
                document_metadata["markdown"] = markdown_text
            section_summaries = self._extract_section_summaries(document)
            if section_summaries:
                document_metadata["sections"] = section_summaries
            document_metadata = _sanitize_metadata(document_metadata)

            pages: list[ParsedPage] = []
            raw_pages = getattr(document, "pages", None) or []
            if isinstance(raw_pages, dict):
                raw_pages = list(raw_pages.values())

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
                    "document_name": path.name,
                    "docling_hash": file_hash,
                }
                page_meta.update(_extract_metadata(getattr(page, "metadata", None)))
                page_meta.update(_extract_metadata(getattr(page, "attrs", None)))
                image_uri = getattr(getattr(page, "image", None), "uri", None)
                if image_uri:
                    image_bytes = self._decode_image(str(image_uri))
                    if image_bytes:
                        image_path = cache_dir / f"page-{number}.png"
                        image_path.write_bytes(image_bytes)
                        page_meta["image_path"] = str(image_path)
                pages.append(
                    ParsedPage(
                        number=number,
                        content=page_text,
                        metadata=_sanitize_metadata(page_meta),
                    )
                )

            if not pages:
                content = _extract_document_text(document, path)
                metadata = _sanitize_metadata(
                    {
                        "source_path": str(path),
                        "title": title,
                        "document_name": path.name,
                        "docling_hash": file_hash,
                        "docling_output": str(json_path),
                        "image_dir": str(cache_dir),
                    }
                )
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
        chunk_size: int = 750,
        chunk_overlap: int = 150,
        allowed_extensions: set[str] | None = None,
    ) -> None:
        self.repository = repository
        self.parser = parser
        self.embedder = embedder
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.allowed_extensions = allowed_extensions or SUPPORTED_EXTENSIONS

    async def _ensure_event(
        self,
        job: IngestionJob,
        step: IngestionStep,
        *,
        document_path: str | None = None,
    ) -> IngestionEvent:
        event = await self.repository.get_event_for_step(job.id, step)
        if event is None:
            event = await self.repository.create_event(
                job_id=job.id,
                step=step,
                status=IngestionEventStatus.pending,
                document_path=document_path,
            )
        elif document_path and not event.document_path:
            event.document_path = document_path
        return event

    async def run(self, job: IngestionJob) -> None:
        paths = self._collect_sources(job.source)
        if not paths:
            raise IngestionError(f"No documents found at source: {job.source}")

        for path in paths:
            LOGGER.info("Parsing document %s", path)
            path_str = str(path)
            docling_event = await self._ensure_event(
                job,
                IngestionStep.docling_parse,
                document_path=path_str,
            )
            await self.repository.update_event_status(
                docling_event,
                status=IngestionEventStatus.running,
                detail={"path": path_str},
            )
            await self.repository.commit()
            try:
                parsed_documents = await self.parser.parse(path)
            except Exception as exc:
                await self.repository.update_event_status(
                    docling_event,
                    status=IngestionEventStatus.failed,
                    detail={"error": str(exc)},
                )
                await self.repository.commit()
                raise
            await self.repository.update_event_status(
                docling_event,
                status=IngestionEventStatus.success,
                detail={"documents": len(parsed_documents)},
            )
            await self.repository.commit()
            for parsed in parsed_documents:
                document_metadata = dict(parsed.metadata)
                document_metadata["ingestion_job_id"] = job.id
                document_metadata = _sanitize_metadata(document_metadata)
                document = await self.repository.create_document(
                    title=parsed.title or path.stem,
                    source_path=str(path),
                    collection_name=job.collection.name if job.collection else "default",
                    metadata=document_metadata,
                    job=job,
                )
                await self.repository.commit()

                chunk_event = await self._ensure_event(
                    job,
                    IngestionStep.chunk_assembly,
                    document_path=path_str,
                )
                await self.repository.update_event_status(
                    chunk_event,
                    status=IngestionEventStatus.running,
                    document_id=document.id,
                    document_title=document.title,
                    detail={"document_id": document.id},
                )
                await self.repository.commit()

                chunk_payloads = self._prepare_chunks(
                    parsed,
                    document.id,
                    path,
                    job,
                    chunk_size=job.chunk_size or self.chunk_size,
                    chunk_overlap=job.chunk_overlap or self.chunk_overlap,
                )
                if not chunk_payloads:
                    LOGGER.debug("Document %s produced no chunks", path)
                    await self.repository.update_event_status(
                        chunk_event,
                        status=IngestionEventStatus.success,
                        document_id=document.id,
                        document_title=document.title,
                        detail={"chunks": 0},
                    )
                    await self.repository.commit()
                    continue

                await self.repository.update_event_status(
                    chunk_event,
                    status=IngestionEventStatus.success,
                    document_id=document.id,
                    document_title=document.title,
                    detail={"chunks": len(chunk_payloads)},
                )
                await self.repository.commit()

                embedding_event = await self._ensure_event(
                    job,
                    IngestionStep.embedding_indexing,
                    document_path=path_str,
                )
                await self.repository.update_event_status(
                    embedding_event,
                    status=IngestionEventStatus.running,
                    document_id=document.id,
                    document_title=document.title,
                    detail={"chunks": len(chunk_payloads)},
                )
                await self.repository.commit()

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

                await self.repository.update_event_status(
                    embedding_event,
                    status=IngestionEventStatus.success,
                    document_id=document.id,
                    document_title=document.title,
                    detail={"chunks_embedded": total_chunks},
                )
                await self.repository.commit()

                citation_event = await self._ensure_event(
                    job,
                    IngestionStep.citation_enrichment,
                    document_path=path_str,
                )
                citations = [
                    {
                        "chunk_index": chunk.metadata.get("chunk_index"),
                        "page_number": chunk.metadata.get("page_number"),
                        "image_path": chunk.metadata.get("citation", {}).get("image_path")
                        if isinstance(chunk.metadata.get("citation"), dict)
                        else None,
                    }
                    for chunk in chunk_payloads
                ]
                await self.repository.update_event_status(
                    citation_event,
                    status=IngestionEventStatus.success,
                    document_id=document.id,
                    document_title=document.title,
                    detail={"citations": citations},
                )
                await self.repository.commit()

    def _prepare_chunks(
        self,
        parsed: ParsedDocument,
        document_id: str,
        path: Path,
        job: IngestionJob,
        *,
        chunk_size: int,
        chunk_overlap: int,
    ) -> list[ChunkPayload]:
        chunk_payloads: list[ChunkPayload] = []
        chunk_index = 0
        for page in parsed.pages:
            for page_chunk_index, (chunk_text, start_word, end_word) in enumerate(
                self._chunk_text(page.content, chunk_size=chunk_size, chunk_overlap=chunk_overlap),
                start=1,
            ):
                if not chunk_text.strip():
                    continue
                chunk_index += 1
                chunk_metadata: dict[str, object] = {
                    "document_id": document_id,
                    "document_title": parsed.title,
                    "source_path": str(path),
                    "collection_name": job.collection.name if job.collection else "default",
                    "ingestion_job_id": job.id,
                    "page_number": page.number,
                    "page_chunk_index": page_chunk_index,
                    "chunk_index": chunk_index,
                    "word_start": start_word,
                    "word_end": end_word,
                    "chunk_size": chunk_size,
                    "chunk_overlap": chunk_overlap,
                }
                if parsed.metadata:
                    chunk_metadata["document_metadata"] = parsed.metadata
                citation: dict[str, object] = {"page_number": page.number}
                if page.metadata:
                    chunk_metadata["page_metadata"] = page.metadata
                    image_path = page.metadata.get("image_path")
                    if image_path:
                        citation["image_path"] = image_path
                    if page.metadata.get("docling_hash"):
                        citation["docling_hash"] = page.metadata.get("docling_hash")
                chunk_metadata["citation"] = citation
                if job.parameters:
                    chunk_metadata["ingestion_parameters"] = job.parameters
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

    def _chunk_text(
        self, text: str, *, chunk_size: int, chunk_overlap: int
    ) -> list[tuple[str, int, int]]:
        words = text.split()
        if not words:
            return []
        step = max(chunk_size - chunk_overlap, 1)
        chunks: list[tuple[str, int, int]] = []
        for start in range(0, len(words), step):
            end = min(start + chunk_size, len(words))
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
