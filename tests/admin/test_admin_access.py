"""Admin access control tests."""
from __future__ import annotations

import asyncio

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


def test_non_admin_cannot_access_admin_routes(app: FastAPI) -> None:
    async def _run() -> None:
        async with app.router.lifespan_context(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                payload = {"email": "bob@example.com", "password": "TopSecret2!", "full_name": "Bob"}

                register_response = await client.post("/auth/register", json=payload)
                assert register_response.status_code == 201

                login_response = await client.post(
                    "/auth/jwt/login",
                    data={"username": payload["email"], "password": payload["password"]},
                )
                assert login_response.status_code == 200
                token = login_response.json()["access_token"]

                headers = {"Authorization": f"Bearer {token}"}
                admin_response = await client.get("/admin/users", headers=headers)
                assert admin_response.status_code == 403

    asyncio.run(_run())
