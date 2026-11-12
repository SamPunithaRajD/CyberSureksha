"""
DocuShield AI — File Handling Utilities

Hashing, validation, storage, and human-readable formatting helpers
for uploaded documents.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from app.config import settings


def compute_file_hash(file_bytes: bytes) -> str:
    """Return the SHA-256 hex digest of *file_bytes*."""
    return hashlib.sha256(file_bytes).hexdigest()


def validate_file_type(filename: str) -> bool:
    """Check whether *filename*'s extension is in the allowed list.

    The comparison is case-insensitive.
    """
    ext = get_file_extension(filename).lower()
    return ext in {e.lower() for e in settings.ALLOWED_EXTENSIONS}


def get_file_extension(filename: str) -> str:
    """Extract the file extension (including the leading dot) from *filename*.

    Returns an empty string when no extension is present.
    """
    _, ext = os.path.splitext(filename)
    return ext


def generate_unique_filename(original_filename: str) -> str:
    """Prefix *original_filename* with a UUID4 to guarantee uniqueness.

    Example
    -------
    >>> generate_unique_filename("deed.pdf")
    'a1b2c3d4-...-deed.pdf'
    """
    unique_prefix = uuid.uuid4().hex[:16]
    return f"{unique_prefix}_{original_filename}"


def save_uploaded_file(
    file_bytes: bytes,
    filename: str,
    upload_dir: str | None = None,
) -> str:
    """Persist *file_bytes* to disk and return the saved file path.

    Files are stored under ``<upload_dir>/YYYY-MM-DD/<filename>``.
    The date-based subdirectory is created automatically.

    Parameters
    ----------
    file_bytes:
        Raw bytes of the uploaded file.
    filename:
        Destination filename (usually UUID-prefixed).
    upload_dir:
        Root upload directory.  Falls back to ``settings.UPLOAD_DIR``.

    Returns
    -------
    str
        Absolute path to the saved file.
    """
    if upload_dir is None:
        upload_dir = settings.UPLOAD_DIR

    today = date.today().isoformat()  # e.g. "2024-06-01"
    dest_dir = Path(upload_dir) / today
    dest_dir.mkdir(parents=True, exist_ok=True)

    dest_path = dest_dir / filename
    dest_path.write_bytes(file_bytes)

    return str(dest_path.resolve())


def get_file_size_human(size_bytes: int) -> str:
    """Format *size_bytes* as a human-readable string (e.g. ``"4.2 MB"``).

    Uses binary units (1 KB = 1024 B).
    """
    if size_bytes < 0:
        return "0 B"

    units = ("B", "KB", "MB", "GB", "TB")
    size = float(size_bytes)

    for unit in units:
        if abs(size) < 1024.0:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024.0

    return f"{size:.1f} PB"
