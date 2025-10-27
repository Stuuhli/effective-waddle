import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from src.admin.dependencies import get_admin_service
from src.admin.schemas import (
    GraphRAGCommandResponse,
    GraphRAGIndexRequest,
    GraphRAGPromptTuneRequest,
)
from src.admin.service import AdminService
from src.config import Settings


class DummyProcess:
    def __init__(self, stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0) -> None:
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._stdout, self._stderr


@pytest.mark.asyncio
async def test_prompt_tune_command_arguments(tmp_path: Path) -> None:
    settings = Settings()
    settings.graphrag.root_dir = tmp_path / "workspace"
    settings.graphrag.config_path = tmp_path / "settings.yaml"
    captured: dict[str, Any] = {}

    async def _fake_subprocess(*args: str, **kwargs: Any) -> DummyProcess:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return DummyProcess(stdout=b"ok", stderr=b"", returncode=0)

    service = AdminService(
        MagicMock(),
        MagicMock(),
        settings=settings,
        subprocess_factory=_fake_subprocess,
    )

    payload = GraphRAGPromptTuneRequest(domain="ISO 270xx Governance", limit=5, verbose=True)
    response = await service.run_graphrag_prompt_tune(payload)

    assert response.success is True
    assert captured["args"][0] == "graphrag"
    assert "--root" in captured["args"]
    assert "--config" in captured["args"]
    assert "--domain" in captured["args"]
    assert "--limit" in captured["args"]
    assert "--verbose" in captured["args"]


@pytest.mark.asyncio
async def test_prompt_tune_limit_validation(tmp_path: Path) -> None:
    settings = Settings()
    settings.graphrag.root_dir = tmp_path / "workspace"

    service = AdminService(MagicMock(), MagicMock(), settings=settings)

    with pytest.raises(HTTPException):
        await service.run_graphrag_prompt_tune(GraphRAGPromptTuneRequest(limit=0))


@pytest.mark.asyncio
async def test_index_command_arguments(tmp_path: Path) -> None:
    settings = Settings()
    settings.graphrag.root_dir = tmp_path / "workspace"
    settings.graphrag.config_path = None
    captured: dict[str, Any] = {}

    async def _fake_subprocess(*args: str, **kwargs: Any) -> DummyProcess:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return DummyProcess(stdout=b"indexed", stderr=b"", returncode=0)

    service = AdminService(
        MagicMock(),
        MagicMock(),
        settings=settings,
        subprocess_factory=_fake_subprocess,
    )

    payload = GraphRAGIndexRequest(verbose=True)
    response = await service.run_graphrag_index(payload)

    assert response.success is True
    assert captured["args"][0] == (sys.executable or "python3")
    assert captured["args"][1:5] == ("-m", "graphrag", "index", "--root")
    assert "--config" not in captured["args"]
    assert "--verbose" in captured["args"]


class _StubAdminService:
    def __init__(self) -> None:
        self.prompt_tune_payload: GraphRAGPromptTuneRequest | None = None
        self.index_payload: GraphRAGIndexRequest | None = None

    async def run_graphrag_prompt_tune(self, payload: GraphRAGPromptTuneRequest) -> GraphRAGCommandResponse:
        self.prompt_tune_payload = payload
        return GraphRAGCommandResponse(
            command="graphrag prompt-tune --root /tmp", exit_code=0, stdout="ok", stderr="", success=True
        )

    async def run_graphrag_index(self, payload: GraphRAGIndexRequest) -> GraphRAGCommandResponse:
        self.index_payload = payload
        return GraphRAGCommandResponse(
            command="python -m graphrag index --root /tmp", exit_code=0, stdout="done", stderr="", success=True
        )


async def _admin_headers(client: AsyncClient) -> dict[str, str]:
    login_response = await client.post(
        "/auth/jwt/login",
        data={"username": "admin@example.com", "password": "ChangeMe123!"},
    )
    token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_admin_endpoints_trigger_commands(app: FastAPI) -> None:
    stub_service = _StubAdminService()
    app.dependency_overrides[get_admin_service] = lambda: stub_service
    try:
        async with app.router.lifespan_context(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                headers = await _admin_headers(client)

                prompt_response = await client.post(
                    "/admin/graphrag/prompt-tune",
                    headers=headers,
                    json={"domain": "ISO 270xx Governance", "limit": 5, "verbose": True},
                )
                assert prompt_response.status_code == 200
                assert prompt_response.json()["success"] is True
                assert stub_service.prompt_tune_payload is not None
                assert stub_service.prompt_tune_payload.domain == "ISO 270xx Governance"

                index_response = await client.post(
                    "/admin/graphrag/index",
                    headers=headers,
                    json={"verbose": True},
                )
                assert index_response.status_code == 200
                assert index_response.json()["command"].startswith("python")
                assert stub_service.index_payload is not None
    finally:
        app.dependency_overrides.pop(get_admin_service, None)