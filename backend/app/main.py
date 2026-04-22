"""FastAPI application factory and top-level configuration."""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI Reservation API",
        version="0.1.0",
        docs_url="/docs" if settings.ENVIRONMENT == "dev" else None,
        redoc_url="/redoc" if settings.ENVIRONMENT == "dev" else None,
    )

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
