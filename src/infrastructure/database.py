"""Database configuration and ORM models."""
from __future__ import annotations

from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    JSON,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from pgvector.sqlalchemy import Vector

from ..config import Settings
from .embeddings.base import EMBEDDING_DIMENSION


NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Base(DeclarativeBase):
    metadata = metadata


class TimestampMixin:
    """Common timestamp columns."""

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Role(TimestampMixin, Base):
    """User role entity."""

    __tablename__ = "roles"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255))

    users: Mapped[list["User"]] = relationship(
        secondary=lambda: UserRole.__table__, back_populates="roles", lazy="selectin"
    )


class User(TimestampMixin, Base):
    """Application user entity."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(255))

    roles: Mapped[list[Role]] = relationship(
        secondary=lambda: UserRole.__table__, back_populates="users", lazy="selectin"
    )
    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )


class UserRole(Base):
    """Association table for many-to-many relation between users and roles."""

    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_role"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role_id: Mapped[str] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)


class Conversation(TimestampMixin, Base):
    """Represents a user conversation/session."""

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(255))

    user: Mapped[User] = relationship(back_populates="conversations", lazy="selectin")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", lazy="selectin"
    )


class Message(TimestampMixin, Base):
    """Messages exchanged in a conversation."""

    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class Document(TimestampMixin, Base):
    """Stored document metadata."""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    ingestion_job_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("ingestion_jobs.id", ondelete="SET NULL"), nullable=True
    )
    metadata_json: Mapped[dict[str, object] | None] = mapped_column(JSON)

    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", lazy="selectin"
    )


class Chunk(TimestampMixin, Base):
    """Document chunk metadata."""

    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    vector_id: Mapped[Optional[str]] = mapped_column(String(255))
    embedding_model: Mapped[Optional[str]] = mapped_column(String(128))
    metadata_json: Mapped[dict[str, object] | None] = mapped_column(JSON)
    embedding: Mapped[Optional[list[float]]] = mapped_column(Vector(EMBEDDING_DIMENSION))

    document: Mapped[Document] = relationship(back_populates="chunks")


class IngestionStatus(str, PyEnum):
    pending = "pending"
    running = "running"
    success = "success"
    failed = "failed"


class IngestionJob(TimestampMixin, Base):
    """Ingestion job metadata."""

    __tablename__ = "ingestion_jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[IngestionStatus] = mapped_column(
        SAEnum(IngestionStatus, name="ingestion_status"), default=IngestionStatus.pending, nullable=False
    )
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    collection_name: Mapped[str] = mapped_column(String(255), nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    documents: Mapped[list[Document]] = relationship(backref="ingestion_job", lazy="selectin")


AsyncSessionFactory = async_sessionmaker[AsyncSession]

_engine: AsyncEngine | None = None
_session_factory: AsyncSessionFactory | None = None


def configure_engine(settings: Settings) -> AsyncSessionFactory:
    """Configure the database engine and session factory."""

    global _engine, _session_factory
    if _engine is None:
        _engine = create_async_engine(
            settings.sqlalchemy_database_uri(),
            echo=settings.postgres.echo,
            future=True,
        )
    if _session_factory is None:
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _session_factory


def get_engine() -> AsyncEngine:
    """Return the configured async engine."""

    if _engine is None:
        raise RuntimeError("Database engine has not been configured")
    return _engine


__all__ = [
    "Base",
    "User",
    "Role",
    "UserRole",
    "Conversation",
    "Message",
    "Document",
    "Chunk",
    "IngestionJob",
    "IngestionStatus",
    "configure_engine",
    "get_engine",
    "AsyncSessionFactory",
]
