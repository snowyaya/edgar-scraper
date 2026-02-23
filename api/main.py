# FastAPI app
"""
FastAPI application factory.

- Registers all routers
- Configures middleware
- Manages the async database engine lifecycle via FastAPI's lifespan context manager

Startup sequence:
  1. Alembic migrations applied
  2. This module imported → engine created (lazy, no connection yet)
  3. First request → connection pool warmed up

Available at:
  http://localhost:8000/api/...      — REST endpoints
  http://localhost:8000/docs         — Swagger UI
  http://localhost:8000/redoc        — ReDoc UI
  http://localhost:8000/openapi.json — OpenAPI schema
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from api.routers import analytics, documents, runs
from scraper.config import settings
from scraper.db import engine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage async engine lifecycle.
    Note: Alembic migrations are running inside the app lifespan; would
    cause issues if multiple workers ever ran concurrently.
    """
    logger.info(
        f"SEC EDGAR API starting up | "
        f"DB: {settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
    )
    yield
    # Shutdown: close all connections in the pool
    await engine.dispose()
    logger.info("Database engine disposed. Shutdown complete.")


def create_app() -> FastAPI:
    app = FastAPI(
        title="SEC EDGAR AI Scraping Pipeline",
        description=(
            "REST API for querying the SEC EDGAR financial filing corpus. "
            "It provides paginated document access, full-text search, section-level "
            "RAG chunking, aggregate analytics, and JSONL export."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # --- CORS ---
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost",
            "http://localhost:80",
            "http://localhost:5173", # run the frontend locally with hot reload during development
            "http://ui", # for container-to-container requests
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Gzip compression
    # Compresses responses > 1KB — important for large document bodies and especially for the JSONL export stream.
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # routers
    app.include_router(runs.router)
    app.include_router(documents.router)
    app.include_router(documents.export_router)
    app.include_router(analytics.router)

    # health check
    @app.get("/health", tags=["system"])
    async def health_check():
        """
        Verify Docker health checks and load balancers.
        Returns 200 if the API process is running.
        Does NOT check DB connectivity (/health/db is used for that).
        """
        return {"status": "ok", "version": "1.0.0"}

    @app.get("/health/db", tags=["system"])
    async def db_health_check():
        """
        Verify DB connectivity.
        Returns 200 if the DB is reachable, 503 otherwise.
        """
        from fastapi import Response
        from sqlalchemy import text as sa_text
        try:
            async with engine.connect() as conn:
                await conn.execute(sa_text("SELECT 1"))
            return {"status": "ok", "db": "connected"}
        except Exception as e:
            logger.error(f"DB health check failed: {e}")
            return Response(
                content='{"status":"error","db":"unreachable"}',
                status_code=503,
                media_type="application/json",
            )

    return app


# module-level app instance
app = create_app()
