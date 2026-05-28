"""FastAPI application factory and top-level configuration."""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers.admin.business import router as admin_business_router
from app.routers.admin.faqs import router as admin_faqs_router
from app.routers.admin.hours import router as admin_hours_router
from app.routers.admin.services import router as admin_services_router
from app.routers.auth import router as auth_router

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI Reservation API",
        version="0.1.0",
        docs_url="/docs" if settings.ENVIRONMENT == "dev" else None,
        redoc_url="/redoc" if settings.ENVIRONMENT == "dev" else None,
    )

    # Mount routers. Public, business-admin, and super-admin routers will follow
    # the same /api/v1 prefix per docs/03-api.md.
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(admin_business_router, prefix="/api/v1")
    app.include_router(admin_services_router, prefix="/api/v1")
    app.include_router(admin_hours_router, prefix="/api/v1")
    app.include_router(admin_faqs_router, prefix="/api/v1")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.FRONTEND_ORIGIN],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["utility"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
