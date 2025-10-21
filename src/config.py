"""Application configuration objects based on Pydantic settings."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
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


class MilvusSettings(BaseModel):
    """Milvus vector store configuration."""

    host: str = "localhost"
    port: int = 19530
    username: str | None = None
    password: str | None = None
    secure: bool = False
    collection: str = "documents"


class LLMSettings(BaseModel):
    """LLM provider configuration for Ollama and vLLM."""

    provider: Literal["ollama", "vllm"] = "ollama"
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama2"
    vllm_host: str = "http://localhost:8000"
    vllm_model: str = "llama2"
    request_timeout: int = 60


class GraphRAGSettings(BaseModel):
    """Configuration for the GraphRAG adapter."""

    root_dir: Path = Path("./graphrag_workspace")
    config_path: Path | None = None
    default_mode: Literal["local", "global", "drift", "basic"] = "local"
    response_type: str = "Multiple Paragraphs"
    community_level: int = 2
    verbose: bool = False


class Settings(BaseSettings):
    """Aggregate settings for the application."""

    fastapi: FastAPISettings = Field(default_factory=FastAPISettings)
    postgres: PostgresSettings = Field(default_factory=PostgresSettings)
    milvus: MilvusSettings = Field(default_factory=MilvusSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    graphrag: GraphRAGSettings = Field(default_factory=GraphRAGSettings)

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
    "MilvusSettings",
    "LLMSettings",
    "GraphRAGSettings",
    "load_settings",
]
