"""Application configuration objects based on Pydantic settings."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, EmailStr, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class FastAPISettings(BaseModel):
    """Settings that control FastAPI specific behaviour."""

    title: str = "RAG Platform"
    description: str = "Retrieval augmented generation platform."
    version: str = "0.1.0"
    docs_url: str | None = "/docs"
    redoc_url: str | None = "/redoc"
    openapi_url: str = "/openapi.json"
    cors_allow_origins: list[str] = Field(default_factory=lambda: ["*"])
    cors_allow_credentials: bool = True
    cors_allow_methods: list[str] = Field(default_factory=lambda: ["*"])
    cors_allow_headers: list[str] = Field(default_factory=lambda: ["*"])
    gzip_minimum_size: int = 1024
    secret_key: str = Field(default="change-me", description="JWT signing secret")
    access_token_expire_minutes: int = 30
    refresh_token_expire_minutes: int = 60 * 24 * 7
    token_algorithm: str = "HS256"
    enable_voyager: bool = True


class PostgresSettings(BaseModel):
    """PostgreSQL connection settings."""

    host: str = "localhost"
    port: int = 5432
    user: str = "postgres"
    password: str = "postgres"
    database: str = "rag_platform"
    echo: bool = False

    @property
    def dsn(self) -> str:
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


class LLMSettings(BaseModel):
    """LLM provider configuration for Ollama and vLLM."""

    provider: Literal["ollama", "vllm"] = "ollama"
    ollama_host: str = "http://localhost:11434"
    ollama_binary: str = "/usr/local/bin/ollama"
    ollama_model: str = "qwen3:4b"
    embedding_model: str = "qwen3-embedding:0.6b"
    vllm_host: str = "http://localhost:8000"
    vllm_model: str = "qwen3:12b"
    request_timeout: int = 60


class GraphRAGSettings(BaseModel):
    """Configuration for the GraphRAG adapter."""

    root_dir: Path = Path("./graphrag_workspace")
    config_path: Path | None = None
    default_mode: Literal["local", "global", "drift", "basic"] = "local"
    response_type: str = "Multiple Paragraphs"
    community_level: int = 2
    verbose: bool = False


class BootstrapSettings(BaseModel):
    """Bootstrap configuration for initial database seeding."""

    admin_email: EmailStr = "admin@example.com"
    admin_password: str = "ChangeMe123!"
    admin_full_name: str = "Administrator"
    admin_capability: Literal["rag", "graphrag"] = "rag"


class ChunkingSettings(BaseModel):
    """Defaults for document chunking."""

    default_size: int = 1200
    default_overlap: int = 150


class StorageSettings(BaseModel):
    """File-system storage configuration for ingestion artefacts."""

    upload_dir: Path = Path("storage/uploads")
    docling_output_dir: Path = Path("storage/docling")
    docling_hash_index: Path = Path("storage/docling/index.json")


class DoclingSettings(BaseModel):
    """Configuration for Docling PDF parsing behaviour."""

    enabled: bool = True
    do_ocr: bool = False
    do_table_structure: bool = True
    table_mode: Literal["accurate", "fast"] = "accurate"
    table_cell_matching: bool = True
    generate_page_images: bool = True
    image_scale: float = 2.0
    accelerator_device: Literal["cpu", "cuda"] = "cpu"
    accelerator_num_threads: int = 0


class Settings(BaseSettings):
    """Aggregate settings for the application."""

    fastapi: FastAPISettings = Field(default_factory=FastAPISettings)
    postgres: PostgresSettings = Field(default_factory=PostgresSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    graphrag: GraphRAGSettings = Field(default_factory=GraphRAGSettings)
    bootstrap: BootstrapSettings = Field(default_factory=BootstrapSettings)
    chunking: ChunkingSettings = Field(default_factory=ChunkingSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    docling: DoclingSettings = Field(default_factory=DoclingSettings)

    model_config = SettingsConfigDict(env_file=".env", env_nested_delimiter="__", case_sensitive=False)

    def sqlalchemy_database_uri(self) -> str:
        """Return SQLAlchemy DSN."""

        return self.postgres.dsn


@lru_cache()
def load_settings() -> Settings:
    """Load application settings with caching."""

    return Settings()


__all__ = [
    "Settings",
    "FastAPISettings",
    "PostgresSettings",
    "LLMSettings",
    "GraphRAGSettings",
    "BootstrapSettings",
    "ChunkingSettings",
    "StorageSettings",
    "DoclingSettings",
    "load_settings",
]
