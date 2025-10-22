"""Modern ingestion pipeline built around Docling's Document Format v2."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol

from .exceptions import IngestionError
from ..config import DoclingSettings, StorageSettings, load_settings
from ..infrastructure.database import IngestionEvent, IngestionEventStatus, IngestionJob, IngestionStep
from ..infrastructure.embeddings.base import EmbeddingClient
from ..infrastructure.repositories.document_repo import DocumentRepository

LOGGER = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf", ".json"}


def _serialise(value: Any) -> object:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Mapping):
        return {str(key): _serialise(val) for key, val in value.items()}
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes, bytearray)):
        return [_serialise(item) for item in value]
    return str(value)


def _sanitize_metadata(metadata: Mapping[str, Any] | None) -> dict[str, object]:
    if not metadata:
        return {}
    return {str(key): _serialise(value) for key, value in metadata.items()}


def _decode_image(uri: str) -> bytes | None:
    if not isinstance(uri, str) or not uri.startswith("data:image"):
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
class ParsedPage:
    number: int
    content: str
    metadata: dict[str, object]


@dataclass(slots=True)
class ParsedDocument:
    title: str
    pages: list[ParsedPage]
    metadata: dict[str, object]


@dataclass(slots=True)
class ChunkPayload:
    text: str
    metadata: dict[str, object]


class DocumentParser(Protocol):
    async def parse(self, path: Path) -> list[ParsedDocument]:
        """Parse the provided path into parsed document representations."""


class DoclingParser:
    """Parser implementation that prefers Docling's Document Format v2."""

    def __init__(
        self,
        storage_settings: StorageSettings | None = None,
        docling_settings: DoclingSettings | None = None,
    ) -> None:
        settings = load_settings()
        self._storage = storage_settings or settings.storage
        self._docling_settings = docling_settings or settings.docling

        self._converter = self._initialise_converter()
        self._docling_dir = Path(self._storage.docling_output_dir).resolve()
        self._docling_dir.mkdir(parents=True, exist_ok=True)
        self._hash_index_path = Path(self._storage.docling_hash_index).resolve()
        self._hash_index_path.parent.mkdir(parents=True, exist_ok=True)
        if not self._hash_index_path.exists():
            self._hash_index_path.write_text("{}", encoding="utf-8")

    def _initialise_converter(self) -> Any | None:
        if not self._docling_settings.enabled:
            LOGGER.info("Docling parsing disabled via configuration; falling back to plaintext parsing")
            return None
        try:
            from docling.document_converter import DocumentConverter  # type: ignore
        except Exception:  # pragma: no cover - optional dependency
            LOGGER.warning("Docling library not available; falling back to plaintext parsing")
            return None
        try:
            return DocumentConverter()
        except Exception:  # pragma: no cover - optional dependency setup
            LOGGER.warning("Failed to instantiate Docling converter; falling back to plaintext", exc_info=True)
            return None

    def _load_hash_index(self) -> dict[str, str]:
        try:
            return json.loads(self._hash_index_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):  # pragma: no cover - defensive
            return {}

    def _save_hash_index(self, index: Mapping[str, str]) -> None:
        self._hash_index_path.write_text(json.dumps(dict(index), ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _create_file_hash(path: Path) -> str:
        hasher = hashlib.sha256(usedforsecurity=False)
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    @staticmethod
    def _normalise_object(value: Any) -> Any:
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        if isinstance(value, Mapping):
            return {str(key): DoclingParser._normalise_object(val) for key, val in value.items()}
        if isinstance(value, Iterable) and not isinstance(value, (str, bytes, bytearray)):
            return [DoclingParser._normalise_object(item) for item in value]
        for method_name in ("model_dump", "dict", "to_dict"):
            method = getattr(value, method_name, None)
            if callable(method):
                try:
                    data = method()
                except TypeError:
                    try:
                        data = method(mode="json")
                    except TypeError:
                        continue
                return DoclingParser._normalise_object(data)
        if hasattr(value, "__dict__"):
            return {
                str(key): DoclingParser._normalise_object(val)
                for key, val in vars(value).items()
                if not str(key).startswith("_")
            }
        return str(value)

    def _looks_like_document_format(self, payload: Mapping[str, Any]) -> bool:
        if "pages" in payload and isinstance(payload["pages"], (list, Mapping)):
            return True
        document = payload.get("document")
        if isinstance(document, Mapping) and "pages" in document:
            return True
        return False

    def _discover_document_formats(self, payload: Any) -> list[dict[str, Any]]:
        discovered: list[dict[str, Any]] = []

        def _walk(value: Any) -> None:
            normalised = self._normalise_object(value)
            if isinstance(normalised, Mapping):
                if self._looks_like_document_format(normalised):
                    discovered.append(dict(normalised))
                    return
                for key in ("documents", "items", "results", "document", "document_format"):
                    if key in normalised:
                        _walk(normalised[key])
                return
            if isinstance(normalised, Iterable) and not isinstance(normalised, (str, bytes, bytearray)):
                for item in normalised:
                    _walk(item)

        _walk(payload)
        return discovered

    def _load_cached_document(self, json_path: Path) -> list[dict[str, Any]]:
        payload = self._normalise_object(self._read_json(json_path))
        if not payload:
            return []
        if isinstance(payload, Mapping) and self._looks_like_document_format(payload):
            return [dict(payload)]
        return self._discover_document_formats(payload)

    @staticmethod
    def _read_json(path: Path) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    @staticmethod
    def _persist_json(path: Path, payload: Mapping[str, Any]) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _parse_plaintext(self, path: Path) -> list[ParsedDocument]:
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except UnicodeDecodeError as exc:  # pragma: no cover - depends on input
            raise IngestionError(f"Unable to read {path} as UTF-8 text") from exc
        metadata = _sanitize_metadata({"source_path": str(path), "title": path.stem, "document_name": path.name})
        page = ParsedPage(number=1, content=content, metadata=metadata)
        return [ParsedDocument(title=path.stem, pages=[page], metadata=metadata)]

    def _materialise_preview(
        self,
        page_payload: Mapping[str, Any],
        cache_dir: Path,
        page_number: int,
    ) -> str | None:
        candidates: list[Any] = []
        for key in ("preview_image", "preview", "image", "thumbnail"):
            if key in page_payload:
                candidates.append(page_payload[key])
        resources = page_payload.get("resources")
        if isinstance(resources, Mapping):
            for key in ("preview_image", "preview", "image", "thumbnail"):
                if key in resources:
                    candidates.append(resources[key])
            assets = resources.get("assets")
            if isinstance(assets, Iterable) and not isinstance(assets, (str, bytes, bytearray)):
                candidates.extend(assets)
        media = page_payload.get("media")
        if isinstance(media, Iterable) and not isinstance(media, (str, bytes, bytearray)):
            candidates.extend(media)

        for candidate in candidates:
            materialised = self._extract_image_path(candidate, cache_dir, page_number)
            if materialised:
                return materialised
        return None

    def _extract_image_path(self, media: Any, cache_dir: Path, page_number: int) -> str | None:
        payload = self._normalise_object(media)
        if isinstance(payload, str):
            if payload.startswith("data:image"):
                image_bytes = _decode_image(payload)
                if not image_bytes:
                    return None
                extension = ".png"
                target = cache_dir / f"page-{page_number}{extension}"
                cache_dir.mkdir(parents=True, exist_ok=True)
                target.write_bytes(image_bytes)
                return str(target)
            candidate_path = Path(payload)
            if not candidate_path.is_absolute():
                candidate_path = (cache_dir / payload).resolve()
            if candidate_path.exists():
                return str(candidate_path)
            return None
        if not isinstance(payload, Mapping):
            return None
        path_value = payload.get("path") or payload.get("file") or payload.get("href")
        if isinstance(path_value, str) and path_value.strip():
            candidate_path = Path(path_value)
            if not candidate_path.is_absolute():
                candidate_path = (cache_dir / path_value).resolve()
            if candidate_path.exists():
                return str(candidate_path)
        uri = payload.get("uri") or payload.get("data") or payload.get("source")
        if isinstance(uri, str) and uri.startswith("data:image"):
            image_bytes = _decode_image(uri)
            if not image_bytes:
                return None
            mimetype = payload.get("mimetype") or payload.get("mime_type") or payload.get("content_type")
            extension = _image_extension(str(mimetype) if isinstance(mimetype, str) else None)
            cache_dir.mkdir(parents=True, exist_ok=True)
            target = cache_dir / f"page-{page_number}{extension}"
            target.write_bytes(image_bytes)
            return str(target)
        if isinstance(uri, str) and uri.startswith("file://"):
            candidate_path = Path(uri.replace("file://", ""))
            if candidate_path.exists():
                return str(candidate_path.resolve())
        return None

    def _page_text(self, page_payload: Mapping[str, Any]) -> str:
        for key in ("text", "content", "plain_text"):
            value = page_payload.get(key)
            if isinstance(value, str) and value.strip():
                return value
        blocks = page_payload.get("blocks") or page_payload.get("elements")
        if isinstance(blocks, Iterable) and not isinstance(blocks, (str, bytes, bytearray)):
            parts: list[str] = []
            for block in blocks:
                if isinstance(block, Mapping):
                    text = block.get("text") or block.get("content")
                    if isinstance(text, str) and text.strip():
                        parts.append(text.strip())
            if parts:
                return "\n\n".join(parts)
        return ""

    def _extract_sections(self, document_payload: Mapping[str, Any]) -> list[dict[str, object]]:
        sections: list[dict[str, object]] = []
        raw_sections = document_payload.get("sections") or document_payload.get("outline")
        if isinstance(raw_sections, Iterable) and not isinstance(raw_sections, (str, bytes, bytearray)):
            for section in raw_sections:
                section_payload = section if isinstance(section, Mapping) else self._normalise_object(section)
                if not isinstance(section_payload, Mapping):
                    continue
                heading = section_payload.get("title") or section_payload.get("heading") or section_payload.get("label")
                if not isinstance(heading, str) or not heading.strip():
                    continue
                pages = section_payload.get("pages") or section_payload.get("page_numbers")
                if isinstance(pages, Iterable) and not isinstance(pages, (str, bytes, bytearray)):
                    page_numbers = [
                        int(page)
                        for page in pages
                        if isinstance(page, (int, float)) or (isinstance(page, str) and page.isdigit())
                    ]
                else:
                    page_numbers = []
                sections.append({"heading": heading.strip(), "pages": sorted(set(page_numbers))})
        return sections

    def _extract_metadata(self, document_payload: Mapping[str, Any]) -> dict[str, object]:
        metadata: dict[str, object] = {}
        for key in ("metadata", "info", "attributes", "properties"):
            raw = document_payload.get(key)
            if isinstance(raw, Mapping):
                metadata.update(_sanitize_metadata(raw))
        return metadata

    def _extract_markdown(self, payload: Mapping[str, Any]) -> str | None:
        exports = payload.get("exports") or payload.get("outputs")
        if isinstance(exports, Mapping):
            markdown = exports.get("markdown")
            if isinstance(markdown, str) and markdown.strip():
                return markdown
        document_payload = payload.get("document")
        if isinstance(document_payload, Mapping):
            markdown = document_payload.get("markdown")
            if isinstance(markdown, str) and markdown.strip():
                return markdown
        return None

    def _prepare_pages(
        self,
        document_payload: Mapping[str, Any],
        path: Path,
        file_hash: str,
        cache_dir: Path,
        json_path: Path,
    ) -> list[ParsedPage]:
        pages_raw = document_payload.get("pages")
        if isinstance(pages_raw, Mapping):
            iterable = pages_raw.values()
        elif isinstance(pages_raw, Iterable) and not isinstance(pages_raw, (str, bytes, bytearray)):
            iterable = pages_raw
        else:
            iterable = []
        pages: list[ParsedPage] = []
        for index, raw_page in enumerate(iterable, start=1):
            page_payload = raw_page if isinstance(raw_page, Mapping) else self._normalise_object(raw_page)
            if not isinstance(page_payload, Mapping):
                continue
            raw_number = (
                page_payload.get("page_number")
                or page_payload.get("page_no")
                or page_payload.get("number")
                or page_payload.get("index")
            )
            try:
                page_number = int(raw_number) if raw_number is not None else index
            except (TypeError, ValueError):
                page_number = index
            text = self._page_text(page_payload)
            if not text.strip():
                continue
            page_metadata = _sanitize_metadata(page_payload.get("metadata") if isinstance(page_payload.get("metadata"), Mapping) else None)
            page_metadata.setdefault("page_number", page_number)
            page_metadata.setdefault("docling_hash", file_hash)
            page_metadata.setdefault("docling_output", str(json_path))
            page_metadata.setdefault("image_dir", str(cache_dir))
            page_metadata.setdefault("source_path", str(path))
            preview_path = self._materialise_preview(page_payload, cache_dir, page_number)
            if preview_path:
                page_metadata["image_path"] = preview_path
            pages.append(ParsedPage(number=page_number, content=text, metadata=page_metadata))
        return pages

    def _prepare_document(
        self,
        document_payload: Mapping[str, Any],
        path: Path,
        file_hash: str,
        cache_dir: Path,
        json_path: Path,
    ) -> ParsedDocument:
        payload = document_payload.get("document") if isinstance(document_payload.get("document"), Mapping) else document_payload
        metadata = self._extract_metadata(payload)
        metadata.update(
            {
                "source_path": str(path),
                "docling_hash": file_hash,
                "docling_output": str(json_path),
                "image_dir": str(cache_dir),
            }
        )
        schema_version = document_payload.get("schema_version") or payload.get("schema_version")
        if schema_version:
            metadata["docling_schema_version"] = schema_version
        sections = self._extract_sections(payload)
        if sections:
            metadata["sections"] = sections
        markdown = self._extract_markdown(document_payload)
        if markdown:
            metadata["markdown"] = markdown
        title = metadata.get("title") or payload.get("title") or payload.get("name") or path.stem
        pages = self._prepare_pages(payload, path, file_hash, cache_dir, json_path)
        if not pages:
            fallback_text = payload.get("text") or payload.get("content") or ""
            fallback_metadata = {
                "source_path": str(path),
                "docling_hash": file_hash,
                "docling_output": str(json_path),
                "image_dir": str(cache_dir),
            }
            pages = [ParsedPage(number=1, content=str(fallback_text), metadata=_sanitize_metadata(fallback_metadata))]
        return ParsedDocument(title=str(title), pages=pages, metadata=_sanitize_metadata(metadata))

    def _parse_with_docling(self, path: Path) -> list[ParsedDocument]:
        file_hash = self._create_file_hash(path)
        cache_dir = (self._docling_dir / file_hash).resolve()
        cache_dir.mkdir(parents=True, exist_ok=True)
        json_path = cache_dir / f"{file_hash}.json"

        documents = self._load_cached_document(json_path)
        if not documents and self._converter is not None:
            try:
                result = self._converter.convert(str(path))
            except Exception as exc:  # pragma: no cover - depends on converter
                raise IngestionError(f"Docling conversion failed for {path}") from exc
            documents = self._discover_document_formats(result)
            if not documents:
                LOGGER.warning("Docling conversion for %s produced no document format; falling back to plaintext", path)
                return self._parse_plaintext(path)
            try:
                self._persist_json(json_path, documents[0])
            except Exception:  # pragma: no cover - best effort persistence
                LOGGER.debug("Unable to persist Docling JSON for %s", path, exc_info=True)
        elif not documents:
            return self._parse_plaintext(path)

        hash_index = self._load_hash_index()
        if hash_index.get(str(path)) != file_hash:
            updated = dict(hash_index)
            updated[str(path)] = file_hash
            self._save_hash_index(updated)

        parsed: list[ParsedDocument] = []
        for document_payload in documents:
            if not isinstance(document_payload, Mapping):
                continue
            parsed.append(self._prepare_document(document_payload, path, file_hash, cache_dir, json_path))
        return parsed or self._parse_plaintext(path)

    async def parse(self, path: Path) -> list[ParsedDocument]:
        if self._converter is None:
            return self._parse_plaintext(path)
        return await asyncio.to_thread(self._parse_with_docling, path)


class DocumentIngestionPipeline:
    """Coordinate ingestion: parsing, chunking, embedding and persistence."""

    def __init__(
        self,
        repository: DocumentRepository,
        parser: DocumentParser,
        embedder: EmbeddingClient,
        *,
        chunk_size: int = 1200,
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
            path_str = str(path)
            docling_event = await self._ensure_event(job, IngestionStep.docling_parse, document_path=path_str)
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

            for parsed_document in parsed_documents:
                document_metadata = dict(parsed_document.metadata)
                document_metadata["ingestion_job_id"] = job.id
                document_metadata = _sanitize_metadata(document_metadata)
                document = await self.repository.create_document(
                    title=parsed_document.title or path.stem,
                    source_path=path_str,
                    collection_name=job.collection.name if job.collection else "default",
                    metadata=document_metadata,
                    job=job,
                )
                await self.repository.commit()

                chunk_event = await self._ensure_event(job, IngestionStep.chunk_assembly, document_path=path_str)
                await self.repository.update_event_status(
                    chunk_event,
                    status=IngestionEventStatus.running,
                    document_id=document.id,
                    document_title=document.title,
                    detail={"document_id": document.id},
                )
                await self.repository.commit()

                chunk_payloads = self._prepare_chunks(
                    parsed_document,
                    document.id,
                    path,
                    job,
                    chunk_size=job.chunk_size or self.chunk_size,
                    chunk_overlap=job.chunk_overlap or self.chunk_overlap,
                )

                await self.repository.update_event_status(
                    chunk_event,
                    status=IngestionEventStatus.success,
                    document_id=document.id,
                    document_title=document.title,
                    detail={"chunks": len(chunk_payloads)},
                )
                await self.repository.commit()

                if not chunk_payloads:
                    continue

                embedding_event = await self._ensure_event(job, IngestionStep.embedding_indexing, document_path=path_str)
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

                citation_event = await self._ensure_event(job, IngestionStep.citation_enrichment, document_path=path_str)
                citations = [
                    {
                        "chunk_index": chunk.metadata.get("chunk_index"),
                        "page_number": chunk.metadata.get("page_number"),
                        "image_path": chunk.metadata.get("citation", {}).get("image_path")
                        if isinstance(chunk.metadata.get("citation"), Mapping)
                        else None,
                        "image_url": chunk.metadata.get("citation", {}).get("image_url")
                        if isinstance(chunk.metadata.get("citation"), Mapping)
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
            for page_chunk_index, (chunk_text, start_char, end_char) in enumerate(
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
                    "char_start": start_char,
                    "char_end": end_char,
                    "chunk_size": chunk_size,
                    "chunk_overlap": chunk_overlap,
                }
                if parsed.metadata:
                    chunk_metadata["document_metadata"] = parsed.metadata
                citation: dict[str, object] = {"page_number": page.number}
                page_hash = None
                image_path: str | None = None
                if page.metadata:
                    chunk_metadata["page_metadata"] = page.metadata
                    image_path = page.metadata.get("image_path")  # type: ignore[assignment]
                    if isinstance(image_path, str) and image_path.strip():
                        citation["image_path"] = image_path.strip()
                    raw_hash = page.metadata.get("docling_hash")
                    if isinstance(raw_hash, str) and raw_hash.strip():
                        page_hash = raw_hash.strip()
                if page_hash is None and isinstance(parsed.metadata, Mapping):
                    raw_hash = parsed.metadata.get("docling_hash")
                    if isinstance(raw_hash, str) and raw_hash.strip():
                        page_hash = raw_hash.strip()
                if page_hash:
                    citation["docling_hash"] = page_hash
                if image_path or page_hash:
                    citation["image_url"] = f"/ingestion/documents/{document_id}/pages/{page.number}/preview"
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
            return [candidate for candidate in path.rglob("*") if candidate.is_file() and self._is_supported(candidate)]
        raise IngestionError(f"Source {source} does not exist")

    def _is_supported(self, path: Path) -> bool:
        return path.suffix.lower() in self.allowed_extensions

    def _chunk_text(self, text: str, *, chunk_size: int, chunk_overlap: int) -> list[tuple[str, int, int]]:
        if not text:
            return []
        chunk_size = max(chunk_size, 1)
        chunk_overlap = max(chunk_overlap, 0)
        if chunk_overlap >= chunk_size:
            chunk_overlap = chunk_size - 1
        step = max(chunk_size - chunk_overlap, 1)
        chunks: list[tuple[str, int, int]] = []
        length = len(text)
        start = 0
        while start < length:
            end = min(start + chunk_size, length)
            chunk_text = text[start:end]
            if chunk_text.strip():
                chunks.append((chunk_text, start, end))
            if end == length:
                break
            start += step
        return chunks


__all__ = [
    "ChunkPayload",
    "DocumentIngestionPipeline",
    "DoclingParser",
    "ParsedDocument",
    "ParsedPage",
]
