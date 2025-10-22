# Document Processing Pipeline Overview

This document summarizes how the repository ingests, parses, chunks, embeds, and enriches documents using Docling and the ingestion pipeline. It is based on commit 959c97fce908b268f34dfaa128062f7d0a80eed4.

## High-level flow

1. **Job creation** – Ingestion jobs are queued via the API/UI and persisted in the database. Each job records the file system source, desired collection, chunk parameters, and status.
2. **Worker execution** – The asynchronous worker (`src/ingestion/worker.py`) dequeues jobs and instantiates a `DocumentIngestionPipeline` with a `DoclingParser`, repository, and embedding client.
3. **Per-file processing** – The pipeline iterates over every supported file discovered at the job source, running the following steps for each file while emitting progress events recorded in the `ingestion_events` table.

## Parsing with Docling

* `DoclingParser` (defined in `src/ingestion/pipeline.py`) is responsible for PDF/structured parsing. When Docling is enabled in `DoclingSettings`, it configures `PdfPipelineOptions` to control OCR, table extraction, accelerator usage, and page-image generation before instantiating a `DocumentConverter`.
* Every source file is hashed (`_create_file_hash`) and cached under `storage/docling/<hash>/`. The cache holds the Docling JSON output, conversion metadata, and derived page images. Re-ingesting the same file reuses the cached artefacts.
* The parser extracts document-level metadata (title, Docling hash, cache paths, markdown serialization, section summaries) and page-level metadata (page number, inline metadata/attributes, generated image path). Raw text is sanitized to remove data URIs and image placeholders.
* The parser yields a `ParsedDocument` containing ordered `ParsedPage` entries, each with cleaned text content and normalized metadata.

## Chunk assembly

* `_prepare_chunks` slides a fixed-size window (default 1200 characters with 150 character overlap) over each page’s text to build sequential chunks. Each chunk stores:
  * Identifiers (`document_id`, `chunk_index`, per-page indices).
  * Source pointers (collection, ingestion job, source path).
  * Character offsets within the page.
  * Captured document/page metadata, including Docling provenance and any extracted page image path for later citations.
* Chunk counts and indices are tracked so downstream embedding/citation steps know the total volume.

## Embedding & storage

* After chunking, the pipeline calls the configured embedding client (`EmbeddingClient`) with the ordered chunk texts and stores the resulting vectors alongside chunk metadata via `DocumentRepository.add_chunk`.
* Each ingestion step emits status updates (`pending → running → success/failed`) recorded through `_ensure_event` and `update_event_status`, allowing the UI to stream progress for docling parsing, chunk assembly, embedding, and citation enrichment.

## Citation enrichment

* Citations are lightweight metadata structures derived from chunk metadata. For each chunk, the pipeline records the chunk index, originating page number, and associated Docling image (if present). These entries are attached to the ingestion event for use by the retrieval & UI layer. When Docling images exist, an authenticated preview endpoint (`GET /ingestion/documents/{document_id}/pages/{page_number}/preview`) streams the cached page render so downstream consumers can show the full page alongside the citation.

## Configuration touchpoints

* `DoclingSettings` (in `src/config.py`) toggles Docling usage and exposes knobs for OCR, table extraction, accelerator selection, and image scaling.
* Storage paths for cached Docling outputs and the hash index live under `StorageSettings` (`storage/docling/` by default).
* Chunk size/overlap defaults live on the `DocumentIngestionPipeline` but can be overridden per job via the ingestion request.

## Where to inspect results

* **Docling artefacts**: `storage/docling/<hash>/` contains the raw Docling JSON plus extracted page images. The hash index in `storage/docling/index.json` maps original source paths to hashes.
* **Database**: Parsed documents, ingestion events, and chunks (including metadata, embedding vectors, and citation payloads) are persisted via `DocumentRepository`. Inspecting the corresponding tables reveals the textual chunks that power retrieval.

This architecture allows fast re-ingestion (thanks to caching), consistent metadata propagation, and precise citations tied back to Docling’s structured output.
