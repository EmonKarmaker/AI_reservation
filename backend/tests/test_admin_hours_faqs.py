"""Integration tests for admin hours, schedule exceptions, and FAQs."""

from __future__ import annotations

from datetime import date, timedelta

from httpx import AsyncClient

PASSWORD = "testpass1234"


async def _register_and_login(client: AsyncClient, slug: str, email: str) -> None:
    await client.post("/api/v1/auth/register", json={
        "business_name": "HF Test Co",
        "business_slug": slug,
        "industry": "test",
        "timezone": "Asia/Dhaka",
        "admin_email": email,
        "admin_password": PASSWORD,
        "admin_full_name": "HF Tester",
    })
    resp = await client.post("/api/v1/auth/login", json={
        "email": email, "password": PASSWORD,
    })
    assert resp.status_code == 200, resp.text


async def test_put_and_get_hours(client, unique_slug, unique_email):
    await _register_and_login(client, unique_slug(), unique_email())

    resp = await client.put("/api/v1/admin/hours", json={"days": [
        {"day_of_week": "mon", "open_time": "09:00:00", "close_time": "18:00:00", "is_closed": False},
        {"day_of_week": "sun", "open_time": None, "close_time": None, "is_closed": True},
    ]})
    assert resp.status_code == 200, resp.text

    resp = await client.get("/api/v1/admin/hours")
    assert resp.status_code == 200
    days = {d["day_of_week"]: d for d in resp.json()["days"]}
    assert days["mon"]["is_closed"] is False
    assert days["sun"]["is_closed"] is True


async def test_put_hours_rejects_duplicate_day(client, unique_slug, unique_email):
    await _register_and_login(client, unique_slug(), unique_email())
    resp = await client.put("/api/v1/admin/hours", json={"days": [
        {"day_of_week": "mon", "is_closed": True},
        {"day_of_week": "mon", "is_closed": False},
    ]})
    assert resp.status_code == 422, resp.text


async def test_schedule_exception_crud(client, unique_slug, unique_email):
    await _register_and_login(client, unique_slug(), unique_email())

    future = (date.today() + timedelta(days=30)).isoformat()
    resp = await client.post("/api/v1/admin/hours/exceptions", json={
        "exception_date": future, "is_closed": True, "reason": "Holiday",
    })
    assert resp.status_code == 201, resp.text
    exc_id = resp.json()["id"]

    resp = await client.get("/api/v1/admin/hours/exceptions")
    assert any(e["id"] == exc_id for e in resp.json())

    resp = await client.delete(f"/api/v1/admin/hours/exceptions/{exc_id}")
    assert resp.status_code == 204


async def test_faqs_crud_full_cycle(client, unique_slug, unique_email):
    await _register_and_login(client, unique_slug(), unique_email())

    resp = await client.get("/api/v1/admin/faqs")
    assert resp.json() == []

    resp = await client.post("/api/v1/admin/faqs", json={
        "question": "Do you open Sundays?", "answer": "No.", "category": "hours",
    })
    assert resp.status_code == 201, resp.text
    faq_id = resp.json()["id"]

    resp = await client.patch(f"/api/v1/admin/faqs/{faq_id}", json={"answer": "Closed Sundays."})
    assert resp.status_code == 200
    assert resp.json()["answer"] == "Closed Sundays."

    resp = await client.delete(f"/api/v1/admin/faqs/{faq_id}")
    assert resp.status_code == 204

    resp = await client.get("/api/v1/admin/faqs")
    assert resp.json() == []


async def test_faqs_require_auth(client):
    resp = await client.get("/api/v1/admin/faqs")
    assert resp.status_code == 401
