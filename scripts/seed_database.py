#!/usr/bin/env python
"""Reset the database schema and seed initial roles plus an admin account."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Dict
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from fastapi_users.password import PasswordHelper

from src.auth.constants import (
    ADMIN_ROLE_DESCRIPTION,
    ADMIN_ROLE_NAME,
    DEFAULT_ROLE_DESCRIPTION,
    DEFAULT_ROLE_NAME,
    GRAPH_RAG_ROLE_DESCRIPTION,
    GRAPH_RAG_ROLE_NAME,
    RAG_ROLE_DESCRIPTION,
    RAG_ROLE_NAME,
)
from src.config import load_settings
from src.infrastructure.database import Base, configure_engine, get_engine
from src.infrastructure.repositories.user_repo import UserRepository
from src.infrastructure.repositories.document_repo import DocumentRepository

ROLE_DESCRIPTIONS: Dict[str, str] = {
    DEFAULT_ROLE_NAME: DEFAULT_ROLE_DESCRIPTION,
    ADMIN_ROLE_NAME: ADMIN_ROLE_DESCRIPTION,
    RAG_ROLE_NAME: RAG_ROLE_DESCRIPTION,
    GRAPH_RAG_ROLE_NAME: GRAPH_RAG_ROLE_DESCRIPTION,
}


async def reset_schema() -> None:
    """Drop and recreate all tables defined in the ORM metadata."""

    settings = load_settings()
    configure_engine(settings)
    engine = get_engine()
    async with engine.begin() as connection:
        # Drop all objects and recreate them to ensure a clean slate.
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)


async def seed_admin() -> None:
    """Populate the database with core roles and an initial admin user."""

    settings = load_settings()
    session_factory = configure_engine(settings)

    async with session_factory() as session:  # type: ignore[call-arg]
        user_repo = UserRepository(session)
        document_repo = DocumentRepository(session)

        roles = {
            name: await user_repo.ensure_role(name, description)
            for name, description in ROLE_DESCRIPTIONS.items()
        }

        admin_capability = settings.bootstrap.admin_capability
        if admin_capability not in (RAG_ROLE_NAME, GRAPH_RAG_ROLE_NAME):
            raise ValueError(
                f"Invalid admin capability '{admin_capability}'. Expected '{RAG_ROLE_NAME}' or '{GRAPH_RAG_ROLE_NAME}'."
            )

        password_helper = PasswordHelper()
        compliance_collection = await document_repo.ensure_collection(
            "compliance", "Compliance document collection"
        )
        await document_repo.assign_collection_to_role(compliance_collection, roles[ADMIN_ROLE_NAME])

        password_hash = password_helper.hash(settings.bootstrap.admin_password)
        await user_repo.create_user(
            email=settings.bootstrap.admin_email,
            hashed_password=password_hash,
            full_name=settings.bootstrap.admin_full_name,
            roles=[roles[ADMIN_ROLE_NAME], roles[admin_capability]],
            is_active=True,
            is_superuser=True,
            is_verified=True,
        )

        await session.commit()

        print(
            f"Seeded admin user '{settings.bootstrap.admin_email}' "
            f"with roles '{ADMIN_ROLE_NAME}' and '{admin_capability}'."
        )


async def main() -> None:
    """Entrypoint that resets the schema and seeds initial data."""

    await reset_schema()
    await seed_admin()


if __name__ == "__main__":
    asyncio.run(main())
