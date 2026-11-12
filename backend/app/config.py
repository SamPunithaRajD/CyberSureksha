"""
DocuShield AI — Application Configuration

Centralized configuration management using pydantic-settings.
All settings are loaded from environment variables with sensible defaults.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings


class RiskThresholds(BaseSettings):
    """Risk scoring tier boundaries (0–100 scale)."""

    low: int = 25
    medium: int = 70
    high: int = 100


class Settings(BaseSettings):
    """
    Global application settings.

    Values are sourced from environment variables first, then fall back to the
    defaults defined here.  Use an ``.env`` file during local development.
    """

    # ── Application ──────────────────────────────────────────────────────
    APP_NAME: str = "SecureDocXAI"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    # ── MongoDB ──────────────────────────────────────────────────────────
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "securedocxai"

    # ── File Storage ─────────────────────────────────────────────────────
    UPLOAD_DIR: str = "./uploads"
    MAX_FILE_SIZE_MB: int = 50
    ALLOWED_EXTENSIONS: list[str] = Field(
        default=[".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".bmp"],
    )

    # ── Risk Engine ──────────────────────────────────────────────────────
    RISK_THRESHOLDS: RiskThresholds = Field(default_factory=RiskThresholds)

    # ── CORS ─────────────────────────────────────────────────────────────
    CORS_ORIGINS: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:5173", "http://localhost:5174", "http://localhost:5175", "http://127.0.0.1:5173", "http://127.0.0.1:5174"],
    )

    # ── Helpers ──────────────────────────────────────────────────────────
    @property
    def max_file_size_bytes(self) -> int:
        """Return *MAX_FILE_SIZE_MB* converted to bytes."""
        return self.MAX_FILE_SIZE_MB * 1024 * 1024

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }


# Singleton — import this everywhere.
settings = Settings()
