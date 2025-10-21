"""Background worker for ingestion jobs."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..dependencies import get_session_factory
from ..infrastructure.database import IngestionJob, IngestionStatus
from ..infrastructure.repositories.document_repo import DocumentRepository

LOGGER = logging.getLogger(__name__)


async def _acquire_job(session: AsyncSession) -> IngestionJob | None:
    stmt = (
        select(IngestionJob)
        .where(IngestionJob.status == IngestionStatus.pending)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalars().first()


async def process_job(session: AsyncSession, job: IngestionJob) -> None:
    repo = DocumentRepository(session)
    await repo.update_job_status(job, status=IngestionStatus.running)
    await repo.commit()
    try:
        LOGGER.info("Processing ingestion job %s from %s", job.id, job.source)
        # Placeholder for Docling parsing and vector storage writes.
        await asyncio.sleep(0.1)
        await repo.update_job_status(job, status=IngestionStatus.success)
        await repo.commit()
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("Ingestion job %s failed", job.id)
        await repo.update_job_status(job, status=IngestionStatus.failed, error_message=str(exc))
        await repo.commit()


async def worker_loop(settings: Settings, poll_interval: float = 2.0) -> None:
    session_factory = get_session_factory()
    while True:
        async with session_factory() as session:  # type: ignore[call-arg]
            async with session.begin():
                job = await _acquire_job(session)
                if job is None:
                    await asyncio.sleep(poll_interval)
                    continue
            await process_job(session, job)
        await asyncio.sleep(0)


__all__ = ["worker_loop", "process_job"]
