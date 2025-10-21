"""Base repository helpers."""
from __future__ import annotations

from typing import Generic, Iterable, Optional, Sequence, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from ..database import Base

ModelT = TypeVar("ModelT", bound=Base)


class AsyncRepository(Generic[ModelT]):
    """Shared repository base class."""

    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, entity: ModelT) -> ModelT:
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def get(self, entity_id: str) -> Optional[ModelT]:
        stmt = select(self.model).where(getattr(self.model, "id") == entity_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list(self) -> Sequence[ModelT]:
        stmt = select(self.model)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def delete(self, entity: ModelT) -> None:
        await self.session.delete(entity)

    async def commit(self) -> None:
        await self.session.commit()

    async def filter_by(self, **filters: object) -> Sequence[ModelT]:
        stmt = select(self.model)
        for key, value in filters.items():
            column: InstrumentedAttribute = getattr(self.model, key)
            stmt = stmt.where(column == value)
        result = await self.session.execute(stmt)
        return result.scalars().all()
