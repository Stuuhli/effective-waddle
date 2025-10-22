"""Ingestion API lifecycle tests."""
from __future__ import annotations

import asyncio

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.config import load_settings
from src.infrastructure.database import IngestionStatus
from src.infrastructure.repositories.document_repo import DocumentRepository


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
