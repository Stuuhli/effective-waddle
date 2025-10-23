"""User repository implementation."""
from __future__ import annotations

from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import Role, RoleCategory, User, UserRole
from .base import AsyncRepository
from ...auth.constants import ROLE_EXCLUSIVE_GROUPS


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
        is_active: bool = True,
        is_superuser: bool = False,
        is_verified: bool = False,
    ) -> User:
        user = User(
            email=email,
            hashed_password=hashed_password,
            full_name=full_name,
            is_active=is_active,
            is_superuser=is_superuser,
            is_verified=is_verified,
        )
        await self.add(user)
        if roles:
            await self._assign_roles(user, roles)
        await self.commit()
        await self.session.refresh(user)
        return user

    async def _assign_roles(self, user: User, roles: Sequence[Role]) -> None:
        """Assign roles, removing mutually exclusive ones eagerly."""

        await self.session.flush()
        role_lookup = {role.name for role in roles}
        for group in ROLE_EXCLUSIVE_GROUPS:
            if not role_lookup.intersection(group):
                continue
            group_role_ids = select(Role.id).where(Role.name.in_(group)).scalar_subquery()
            await self.session.execute(
                UserRole.__table__
                .delete()
                .where(UserRole.user_id == user.id)
                .where(UserRole.role_id.in_(group_role_ids))
            )

        existing = await self.session.execute(
            select(UserRole.role_id).where(UserRole.user_id == user.id)
        )
        existing_role_ids = set(existing.scalars().all())

        for role in roles:
            if role.id in existing_role_ids:
                continue
            self.session.add(UserRole(user_id=user.id, role_id=role.id))
        await self.session.flush()

    async def assign_role(self, user: User, role: Role) -> None:
        await self._assign_roles(user, [role])
        await self.session.flush()
        await self.commit()

    async def set_user_roles(self, user: User, roles: Sequence[Role]) -> None:
        """Replace the roles assigned to a user."""

        await self.session.execute(
            UserRole.__table__.delete().where(UserRole.user_id == user.id)
        )
        await self._assign_roles(user, roles)
        await self.session.flush()
        await self.commit()

    async def get_role_by_name(self, name: str) -> Optional[Role]:
        stmt = select(Role).where(Role.name == name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_roles(self) -> list[Role]:
        result = await self.session.execute(select(Role).order_by(Role.category, Role.name))
        return list(result.scalars())

    async def ensure_role(
        self,
        name: str,
        description: str | None = None,
        category: RoleCategory | None = None,
    ) -> Role:
        role = await self.get_role_by_name(name)
        if role is None:
            role = Role(
                name=name,
                description=description,
                category=category or RoleCategory.workspace,
            )
            await self.add(role)  # type: ignore[arg-type]
        else:
            updated = False
            if description is not None and role.description != description:
                role.description = description
                updated = True
            if category is not None and role.category != category:
                role.category = category
                updated = True
            if updated:
                await self.session.flush()
        await self.commit()
        await self.session.refresh(role)
        return role


__all__ = ["UserRepository"]
