"""Integration tests for admin business + services CRUD.

Each test registers a fresh business (via /auth/register) so it has an
isolated tenant + an authenticated session, then exercises the admin
endpoints. Auth cookies are carried automatically by the AsyncClient.
"""

from __future__ import annotations

from httpx import AsyncClient

PASSWORD = "testpass1234"


async def _register_and_login(client: AsyncClient, slug: str, email: str) -> None:
    await client.post("/api/v1/auth/register", json={
        "business_name": "Admin Test Co",
        "business_slug": slug,
        "industry": "test",
        "timezone": "Asia/Dhaka",
        "admin_email": email,
        "admin_password": PASSWORD,
        "admin_full_name": "Admin Tester",
    })
    resp = await client.post("/api/v1/auth/login", json={
        "email": email, "password": PASSWORD,
    })
    assert resp.status_code == 200, resp.text


async def test_get_business_returns_own_business(client, unique_slug, unique_email):
    slug = unique_slug()
    await _register_and_login(client, slug, unique_email())

    resp = await client.get("/api/v1/admin/business")
    assert resp.status_code == 200, resp.text
    assert resp.json()["slug"] == slug


async def test_patch_business_updates_fields(client, unique_slug, unique_email):
    await _register_and_login(client, unique_slug(), unique_email())

    resp = await client.patch("/api/v1/admin/business", json={"phone": "+880123456789"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["phone"] == "+880123456789"


async def test_services_crud_full_cycle(client, unique_slug, unique_email):
    await _register_and_login(client, unique_slug(), unique_email())

    # Initially empty
    resp = await client.get("/api/v1/admin/services")
    assert resp.status_code == 200, resp.text
    assert resp.json() == []

    # Create
    resp = await client.post("/api/v1/admin/services", json={
        "name": "Consultation", "duration_minutes": 30, "price": 500,
    })
    assert resp.status_code == 201, resp.text
    service_id = resp.json()["id"]

    # List shows 1
    resp = await client.get("/api/v1/admin/services")
    assert len(resp.json()) == 1

    # Get one
    resp = await client.get(f"/api/v1/admin/services/{service_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Consultation"

    # Update
    resp = await client.patch(f"/api/v1/admin/services/{service_id}", json={"price": 750})
    assert resp.status_code == 200
    assert float(resp.json()["price"]) == 750.0

    # Delete (soft)
    resp = await client.delete(f"/api/v1/admin/services/{service_id}")
    assert resp.status_code == 204

    # List back to empty
    resp = await client.get("/api/v1/admin/services")
    assert resp.json() == []


async def test_services_require_auth(client):
    resp = await client.get("/api/v1/admin/services")
    assert resp.status_code == 401


async def test_business_scope_isolation(client, unique_slug, unique_email):
    """A service created by business A must not be visible to business B."""
    # Business A creates a service
    await _register_and_login(client, unique_slug(), unique_email())
    resp = await client.post("/api/v1/admin/services", json={
        "name": "A-only Service", "duration_minutes": 30, "price": 500,
    })
    service_id = resp.json()["id"]

    # Log out, register + login as Business B (same client = new cookies)
    await client.post("/api/v1/auth/logout")
    await _register_and_login(client, unique_slug(), unique_email())

    # Business B tries to fetch A's service → 404
    resp = await client.get(f"/api/v1/admin/services/{service_id}")
    assert resp.status_code == 404
