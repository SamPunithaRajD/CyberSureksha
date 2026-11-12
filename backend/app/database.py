"""
DocuShield AI — Async MongoDB Connection Manager

Uses Motor (async driver for MongoDB) to manage the database lifecycle.
Provides helpers to obtain database and collection handles.
"""

from __future__ import annotations

from loguru import logger
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING

from app.config import settings

# ── Module-level client reference ────────────────────────────────────────────
db_client: AsyncIOMotorClient | None = None


async def connect_db() -> None:
    """
    Establish the MongoDB connection and create required indexes.

    Called once during application startup.
    """
    global db_client

    logger.info("Connecting to MongoDB at {}", settings.MONGODB_URL)
    db_client = AsyncIOMotorClient(
        settings.MONGODB_URL,
        maxPoolSize=50,
        minPoolSize=10,
        serverSelectionTimeoutMS=5000,
    )

    # Verify connectivity
    try:
        await db_client.admin.command("ping")
        logger.success("MongoDB connection established")
    except Exception as exc:
        logger.error("MongoDB connection failed: {}", exc)
        raise

    db = db_client[settings.MONGODB_DB_NAME]

    # ── Create indexes ───────────────────────────────────────────────────
    documents_col = db["documents"]
    await documents_col.create_index(
        [("file_hash_sha256", ASCENDING)],
        unique=True,
        name="idx_file_hash_sha256",
    )
    await documents_col.create_index(
        [("status", ASCENDING)],
        name="idx_status",
    )
    await documents_col.create_index(
        [("uploaded_at", DESCENDING)],
        name="idx_uploaded_at",
    )

    analyses_col = db["analyses"]
    await analyses_col.create_index(
        [("document_id", ASCENDING)],
        unique=True,
        name="idx_document_id",
    )
    await analyses_col.create_index(
        [("risk_score.tier", ASCENDING)],
        name="idx_risk_tier",
    )

    cases_col = db["cases"]
    await cases_col.create_index(
        [("case_id", ASCENDING)],
        unique=True,
        name="idx_case_id",
    )
    await cases_col.create_index(
        [("status", ASCENDING)],
        name="idx_case_status",
    )

    logger.info("Database indexes ensured on 'documents', 'analyses', and 'cases'")

    # ── Seed Default Users ────────────────────────────────────────────────
    users_col = db["users"]
    user_count = await users_col.count_documents({})
    if user_count == 0:
        logger.info("No users found in database. Seeding default role accounts...")
        from app.utils.auth_helper import hash_password
        default_users = [
            {"email": "underwriter@bank.com", "username": "Vikram Nair", "role": "Underwriting Officer", "branch": "Canara Bank"},
            {"email": "analyst@bank.com", "username": "Rahul Sharma", "role": "Fraud Analyst", "branch": "Canara Bank"},
            {"email": "manager@bank.com", "username": "Priya Iyer", "role": "Branch Manager", "branch": "Canara Bank"},
            {"email": "auditor@bank.com", "username": "Amit Patel", "role": "Compliance Auditor", "branch": "Canara Bank"},
            {"email": "admin@bank.com", "username": "System Admin", "role": "System Admin", "branch": "Canara Bank"},
        ]
        hashed_pw = hash_password("Password123")
        for u in default_users:
            u["password_hash"] = hashed_pw
            await users_col.insert_one(u)
        logger.success("Default user accounts seeded successfully with password: Password123")


async def close_db() -> None:
    """Close the MongoDB connection pool.  Called during application shutdown."""
    global db_client

    if db_client is not None:
        db_client.close()
        db_client = None
        logger.info("MongoDB connection closed")


def get_database() -> AsyncIOMotorDatabase:
    """Return the application database handle.

    Raises
    ------
    RuntimeError
        If called before ``connect_db()`` has run.
    """
    if db_client is None:
        raise RuntimeError(
            "Database client is not initialised. "
            "Ensure connect_db() is awaited before accessing the database."
        )
    return db_client[settings.MONGODB_DB_NAME]


def get_collection(name: str):
    """Shortcut to obtain a Motor collection by *name*."""
    return get_database()[name]
