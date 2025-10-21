"""Ingestion API lifecycle tests."""
from __future__ import annotations

import asyncio

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.infrastructure.database import IngestionStatus
from src.infrastructure.repositories.document_repo import DocumentRepository


def test_ingestion_job_lifecycle(app: FastAPI, session_factory: async_sessionmaker) -> None:
    async def _run() -> None:
        async with app.router.lifespan_context(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                user_payload = {"email": "eve@example.com", "password": "EveSecret5!", "full_name": "Eve"}
                register = await client.post("/auth/register", json=user_payload)
                assert register.status_code == 201
                login = await client.post(
                    "/auth/jwt/login",
                    data={"username": user_payload["email"], "password": user_payload["password"]},
                )
                assert login.status_code == 200
                token = login.json()["access_token"]
                headers = {"Authorization": f"Bearer {token}"}

                create_job_1 = await client.post(
                    "/ingestion/jobs",
                    json={"source": "s3://bucket/doc1.pdf", "collection_name": "alpha"},
                    headers=headers,
                )
                assert create_job_1.status_code == 201
                job_one = create_job_1.json()
                assert job_one["status"] == IngestionStatus.pending.value

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
                assert job_one_status.json()["status"] == IngestionStatus.success.value

                create_job_2 = await client.post(
                    "/ingestion/jobs",
                    json={"source": "s3://bucket/doc2.pdf", "collection_name": "beta"},
                    headers=headers,
                )
                assert create_job_2.status_code == 201
                job_two = create_job_2.json()

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

    asyncio.run(_run())
