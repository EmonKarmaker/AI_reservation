"""Integration tests for the auth endpoints.

Four tests:
1. register happy path → 201
2. login happy path → 200 with cookies set
3. /auth/me without cookies → 401
4. require_super_admin invoked as a business_admin → 403
"""

from __future__ import annotations

import uuid as _uuid

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import ACCESS_TOKEN_COOKIE, require_super_admin


PASSWORD = "testpass1234"


async def test_register_creates_business_and_admin(
    client: AsyncClient,
    unique_slug: object,
    unique_email: object,
) -> None:
    slug = unique_slug()  # type: ignore[operator]
    email = unique_email()  # type: ignore[operator]
    body = {
        "business_name": "Test Co",
        "business_slug": slug,
        "industry": "test",
        "timezone": "Asia/Dhaka",
        "admin_email": email,
        "admin_password": PASSWORD,
        "admin_full_name": "Test Owner",
    }

    response = await client.post("/api/v1/auth/register", json=body)

    assert response.status_code == 201, response.text
    payload = response.json()
    assert "business_id" in payload
    assert "user_id" in payload
    assert payload["message"]


async def test_login_returns_user_and_sets_cookies(
    client: AsyncClient,
    unique_slug: object,
    unique_email: object,
) -> None:
    slug = unique_slug()  # type: ignore[operator]
    email = unique_email()  # type: ignore[operator]
    await client.post("/api/v1/auth/register", json={
        "business_name": "Login Test Co",
        "business_slug": slug,
        "industry": "test",
        "timezone": "Asia/Dhaka",
        "admin_email": email,
        "admin_password": PASSWORD,
        "admin_full_name": "Login Tester",
    })

    response = await client.post("/api/v1/auth/login", json={
        "email": email,
        "password": PASSWORD,
    })

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["user"]["email"] == email
    assert payload["user"]["role"] == "business_admin"
    assert payload["user"]["business_id"] is not None

    cookies = response.cookies
    assert ACCESS_TOKEN_COOKIE in cookies
    assert "refresh_token" in cookies


async def test_protected_route_without_auth_returns_401(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


async def test_require_super_admin_rejects_business_admin(
    db_session: AsyncSession,
    unique_email: object,
) -> None:
    """Directly exercise require_super_admin with a business_admin User object."""
    from app.core.security import hash_password
    from app.models.business import Business
    from app.models.business_setting import BusinessSetting
    from app.models.enums import BusinessStatus, UserRole
    from app.models.user import User

    business = Business(
        slug=f"sec-{_uuid.uuid4().hex[:8]}",
        name="Security Test",
        timezone="UTC",
        status=BusinessStatus.ACTIVE,
    )
    db_session.add(business)
    await db_session.flush()
    db_session.add(BusinessSetting(business_id=business.id))

    user = User(
        email=unique_email(),  # type: ignore[operator]
        password_hash=hash_password("ignored"),
        full_name="Biz Admin",
        role=UserRole.BUSINESS_ADMIN,
        business_id=business.id,
    )
    db_session.add(user)
    await db_session.flush()

    with pytest.raises(HTTPException) as exc:
        require_super_admin(user)
    assert exc.value.status_code == 403
