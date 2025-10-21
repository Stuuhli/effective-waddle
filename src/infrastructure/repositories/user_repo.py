"""User repository implementation."""
from __future__ import annotations

from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import Role, User, UserRole
from .base import AsyncRepository


class UserRepository(AsyncRepository[User]):
    """Repository for user specific queries."""

    model = User

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_by_email(self, email: str) -> Optional[User]:
        stmt = select(User).where(User.email == email)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_user(
        self,
        *,
        email: str,
        hashed_password: str,
        full_name: str | None = None,
        roles: Sequence[Role] | None = None,
    ) -> User:
        user = User(email=email, hashed_password=hashed_password, full_name=full_name)
        if roles:
            user.roles.extend(roles)
        await self.add(user)
        await self.commit()
        await self.session.refresh(user)
        return user

    async def assign_role(self, user: User, role: Role) -> None:
        if role not in user.roles:
            user.roles.append(role)
            await self.session.flush()
            await self.commit()

    async def get_role_by_name(self, name: str) -> Optional[Role]:
        stmt = select(Role).where(Role.name == name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_roles(self) -> list[Role]:
        result = await self.session.execute(select(Role))
        return list(result.scalars())

    async def ensure_role(self, name: str, description: str | None = None) -> Role:
        role = await self.get_role_by_name(name)
        if role is None:
            role = Role(name=name, description=description)
            await self.add(role)  # type: ignore[arg-type]
            await self.commit()
            await self.session.refresh(role)
        return role


__all__ = ["UserRepository"]
