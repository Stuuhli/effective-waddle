"""Ingestion API lifecycle tests."""
from __future__ import annotations

import asyncio
import json
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.config import load_settings

from src.infrastructure.database import (
    Chunk,
    Document,
    IngestionEvent,
    IngestionEventStatus,
    IngestionStatus,
    IngestionStep,
)
from src.infrastructure.repositories.document_repo import DocumentRepository
from src.ingestion.pipeline import DocumentIngestionPipeline, ParsedDocument, ParsedPage, IngestionError


def test_ingestion_job_lifecycle(app: FastAPI, session_factory: async_sessionmaker) -> None:
    async def _run() -> None:
        async with app.router.lifespan_context(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                settings = load_settings()
                login = await client.post(
                    "/auth/jwt/login",
                    data={
                        "username": settings.bootstrap.admin_email,
                        "password": settings.bootstrap.admin_password,
                    },
                )
                assert login.status_code == 200
                token = login.json()["access_token"]
                headers = {"Authorization": f"Bearer {token}"}

                create_job_1 = await client.post(
                    "/ingestion/jobs",
                    json={"source": "s3://bucket/doc1.pdf", "collection_name": "compliance"},
                    headers=headers,
                )
                assert create_job_1.status_code == 201
                job_one = create_job_1.json()
                assert job_one["status"] == IngestionStatus.pending.value
                assert job_one["chunk_size"] == 1200
                assert job_one["chunk_overlap"] == 150
                assert job_one["metadata"] is None
                assert job_one["collection_name"] == "compliance"
                assert job_one["events"] == []

                async with session_factory() as session:
                    repo = DocumentRepository(session)
                    job = await repo.get_job(job_one["id"])
                    assert job is not None
                    await repo.update_job_status(job, status=IngestionStatus.running)
                    await repo.commit()
                    await repo.update_job_status(job, status=IngestionStatus.success)
                    await repo.commit()

                job_one_status = await client.get(f"/ingestion/jobs/{job_one['id']}", headers=headers)
                assert job_one_status.status_code == 200
                job_one_payload = job_one_status.json()
                assert job_one_payload["status"] == IngestionStatus.success.value
                assert job_one_payload["events"] == []

                create_job_2 = await client.post(
                    "/ingestion/jobs",
                    json={
                        "source": "s3://bucket/doc2.pdf",
                        "collection_name": "compliance",
                        "chunk_size": 800,
                        "chunk_overlap": 120,
                        "metadata": {"department": "finance"},
                    },
                    headers=headers,
                )
                assert create_job_2.status_code == 201
                job_two = create_job_2.json()
                assert job_two["chunk_size"] == 800
                assert job_two["chunk_overlap"] == 120
                assert job_two["metadata"] == {"department": "finance"}

                async with session_factory() as session:
                    repo = DocumentRepository(session)
                    job = await repo.get_job(job_two["id"])
                    assert job is not None
                    await repo.update_job_status(job, status=IngestionStatus.running)
                    await repo.commit()
                    await repo.update_job_status(job, status=IngestionStatus.failed, error_message="parser error")
                    await repo.commit()

                job_two_status = await client.get(f"/ingestion/jobs/{job_two['id']}", headers=headers)
                assert job_two_status.status_code == 200
                job_two_payload = job_two_status.json()
                assert job_two_payload["status"] == IngestionStatus.failed.value
                assert job_two_payload["error_message"] == "parser error"
                assert job_two_payload["collection_name"] == "compliance"

    asyncio.run(_run())


def test_pipeline_raises_when_no_chunks(session_factory: async_sessionmaker, tmp_path) -> None:
    class EmptyParser:
        async def parse(self, source: str) -> ParsedDocument:
            metadata = {
                "docling_hash": "hash-empty",
                "docling_output": str(tmp_path / "hash-empty.json"),
                "image_dir": str(tmp_path / "images"),
                "source_path": source,
                "page_count": 1,
            }
            page = ParsedPage(number=1, content="   ", metadata={"docling_hash": "hash-empty"})
            return ParsedDocument(title="Empty", pages=[page], metadata=metadata, docling_document=None)

    class GuardedEmbedder:
        async def embed(self, texts):  # pragma: no cover - should not be called
            raise AssertionError("Embedding should not run when no chunks are produced.")

    async def _run() -> None:
        async with session_factory() as session:
            repo = DocumentRepository(session)
            collection = await repo.ensure_collection("compliance", "Compliance collection")
            empty_file = tmp_path / "empty.pdf"
            empty_file.write_text("", encoding="utf-8")
            job = await repo.create_ingestion_job(
                user_id=None,
                source=str(empty_file),
                chunk_size=1200,
                chunk_overlap=150,
                parameters=None,
                collection=collection,
            )
            await repo.commit()
            await session.refresh(job, attribute_names=["collection"])

            pipeline = DocumentIngestionPipeline(
                repo,
                EmptyParser(),
                GuardedEmbedder(),
                chunk_size=1200,
                chunk_overlap=150,
            )
            try:
                await pipeline.run(job)
            except IngestionError as exc:
                assert "No chunks produced" in str(exc)
            else:  # pragma: no cover - safety
                pytest.fail("Expected pipeline to raise IngestionError when no chunks are produced.")

    asyncio.run(_run())


def test_delete_ingestion_job_removes_artifacts(app: FastAPI, session_factory: async_sessionmaker) -> None:
    async def _run() -> None:
        async with app.router.lifespan_context(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                settings = load_settings()
                login = await client.post(
                    "/auth/jwt/login",
                    data={
                        "username": settings.bootstrap.admin_email,
                        "password": settings.bootstrap.admin_password,
                    },
                )
                assert login.status_code == 200
                token = login.json()["access_token"]
                headers = {"Authorization": f"Bearer {token}"}

                upload_path = settings.storage.upload_dir / "deletion-target.pdf"
                upload_path.parent.mkdir(parents=True, exist_ok=True)
                upload_path.write_bytes(b"%PDF-1.4\n%test\n")

                create_job = await client.post(
                    "/ingestion/jobs",
                    json={"source": str(upload_path), "collection_name": "compliance"},
                    headers=headers,
                )
                assert create_job.status_code == 201
                job_payload = create_job.json()
                job_id = job_payload["id"]

                docling_dir = settings.storage.docling_output_dir / "hash-delete"
                docling_dir.mkdir(parents=True, exist_ok=True)
                docling_json = docling_dir / "hash-delete.json"
                docling_json.write_text("{}", encoding="utf-8")

                index_path = settings.storage.docling_hash_index
                index_path.parent.mkdir(parents=True, exist_ok=True)
                index_path.write_text(
                    json.dumps({str(upload_path): {"hash": "hash-delete"}}, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

                async with session_factory() as session:
                    repo = DocumentRepository(session)
                    job = await repo.get_job(job_id)
                    assert job is not None
                    document = await repo.create_document(
                        title="To be deleted",
                        source_path=str(upload_path),
                        collection_name=job.collection.name if job.collection else "compliance",
                        metadata={
                            "source_path": str(upload_path),
                            "docling_hash": "hash-delete",
                            "docling_output": str(docling_json),
                            "image_dir": str(docling_dir),
                        },
                        job=job,
                    )
                    chunk = await repo.add_chunk(document_id=document.id, content="chunk", metadata={"page": 1})
                    event = await repo.create_event(
                        job_id=job.id,
                        step=IngestionStep.docling_parse,
                        status=IngestionEventStatus.success,
                        document_id=document.id,
                        document_title=document.title,
                        document_path=str(upload_path),
                    )
                    await repo.commit()
                    document_id = document.id
                    chunk_id = chunk.id
                    event_id = event.id

                delete_response = await client.delete(f"/ingestion/jobs/{job_id}", headers=headers)
                assert delete_response.status_code == 204

                assert not upload_path.exists()
                assert not docling_json.exists()
                assert not docling_dir.exists()
                assert not index_path.exists()

                async with session_factory() as session:
                    job_repo = DocumentRepository(session)
                    assert await job_repo.get_job(job_id) is None
                    assert await session.get(Document, document_id) is None
                    assert await session.get(Chunk, chunk_id) is None
                    assert await session.get(IngestionEvent, event_id) is None

    asyncio.run(_run())
