from __future__ import annotations

import asyncio

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


async def _admin_headers(client: AsyncClient) -> dict[str, str]:
    login_response = await client.post(
        "/auth/jwt/login",
        data={"username": "admin@example.com", "password": "ChangeMe123!"},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_admin_role_and_collection_management(app: FastAPI) -> None:
    async def _run() -> None:
        async with app.router.lifespan_context(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                headers = await _admin_headers(client)

                users_response = await client.get("/admin/users", headers=headers)
                assert users_response.status_code == 200
                users = users_response.json()
                assert users
                admin_user = next(user for user in users if user["email"] == "admin@example.com")

                roles_response = await client.get("/admin/roles", headers=headers)
                assert roles_response.status_code == 200
                roles_before = {role["name"] for role in roles_response.json()}
                assert "admin" in roles_before

                create_role_response = await client.post(
                    "/admin/roles",
                    headers=headers,
                    json={"name": "auditor", "description": "Can review collections"},
                )
                assert create_role_response.status_code == 201

                update_roles_response = await client.put(
                    f"/admin/users/{admin_user['id']}/roles",
                    headers=headers,
                    json={"role_names": ["admin", "rag", "auditor"]},
                )
                assert update_roles_response.status_code == 200
                updated_user = update_roles_response.json()
                assert set(updated_user["roles"]) >= {"admin", "rag", "auditor"}

                create_collection_response = await client.post(
                    "/admin/collections",
                    headers=headers,
                    json={"name": "finance", "description": "Finance docs", "role_names": ["admin"]},
                )
                assert create_collection_response.status_code == 201
                created_collection = create_collection_response.json()
                assert created_collection["name"] == "finance"
                assert created_collection["roles"] == ["admin"]

                collections_response = await client.get("/admin/collections", headers=headers)
                assert collections_response.status_code == 200
                collections = collections_response.json()
                target_collection = next(item for item in collections if item["name"] == "finance")

                update_collection_response = await client.put(
                    f"/admin/collections/{target_collection['id']}/roles",
                    headers=headers,
                    json={"role_names": ["admin", "auditor"]},
                )
                assert update_collection_response.status_code == 200
                updated_collection = update_collection_response.json()
                assert set(updated_collection["roles"]) == {"admin", "auditor"}

    asyncio.run(_run())
