"""Authentication API tests."""
from __future__ import annotations

import asyncio

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


def test_register_login_and_me_flow(app: FastAPI) -> None:
    async def _run() -> None:
        async with app.router.lifespan_context(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                payload = {"email": "alice@example.com", "password": "SuperSecret1!", "full_name": "Alice"}

                register_response = await client.post("/auth/register", json=payload)
                assert register_response.status_code == 201
                registered = register_response.json()
                assert registered["email"] == payload["email"]
                assert "user" in registered["roles"]

                login_response = await client.post(
                    "/auth/login", json={"email": payload["email"], "password": payload["password"]}
                )
                assert login_response.status_code == 200
                tokens = login_response.json()
                assert "access_token" in tokens and tokens["access_token"]
                assert "refresh_token" in tokens and tokens["refresh_token"]

                headers = {"Authorization": f"Bearer {tokens['access_token']}"}
                me_response = await client.get("/auth/me", headers=headers)
                assert me_response.status_code == 200
                current_user = me_response.json()
                assert current_user["email"] == payload["email"]
                assert "user" in current_user["roles"]

    asyncio.run(_run())
