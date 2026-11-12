"""
SecureDocXAI — FastAPI Application Entry-Point

Sets up middleware, lifecycle hooks, and mounts the versioned API router.
"""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.api.router import api_router
from app.config import settings
from app.database import close_db, connect_db

# ── Loguru configuration ─────────────────────────────────────────────────────
# Remove default stderr sink and re-add with a clean format.
logger.remove()
logger.add(
    sys.stderr,
    level="DEBUG" if settings.DEBUG else "INFO",
    format=(
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> — "
        "<level>{message}</level>"
    ),
    colorize=True,
)
logger.add(
    "logs/securedocxai_{time:YYYY-MM-DD}.log",
    rotation="10 MB",
    retention="30 days",
    compression="zip",
    level="DEBUG",
    format=(
        "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
        "{name}:{function}:{line} — {message}"
    ),
)


# ── Lifespan (modern replacement for on_event) ──────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle manager."""
    # ── Startup ──────────────────────────────────────────────────────────
    logger.info("Starting {} v{}", settings.APP_NAME, settings.APP_VERSION)

    # Ensure upload directory exists
    upload_path = Path(settings.UPLOAD_DIR)
    upload_path.mkdir(parents=True, exist_ok=True)
    logger.info("Upload directory ready: {}", upload_path.resolve())

    # Connect to MongoDB
    await connect_db()

    yield  # ← application is running

    # ── Shutdown ─────────────────────────────────────────────────────────
    await close_db()
    logger.info("{} shut down gracefully", settings.APP_NAME)


# ── FastAPI application instance ─────────────────────────────────────────────
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "AI-powered document fraud detection and risk assessment API. "
        "Analyse land records, financial documents, legal contracts, and "
        "identity papers for signs of tampering, forgery, and anomalies."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Versioned API routes ─────────────────────────────────────────────────────
app.include_router(api_router, prefix="/api/v1")

# ── Static File Mounts ───────────────────────────────────────────────────────
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")


# ── Root endpoint ────────────────────────────────────────────────────────────
@app.get("/", tags=["root"])
async def root():
    """Root probe — returns service identity and operational status."""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "operational",
    }
