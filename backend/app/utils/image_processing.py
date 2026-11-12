"""
DocuShield AI — Image Processing Utilities

OpenCV + PyMuPDF helpers for loading, converting, and pre-processing
document images and PDFs.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Sequence

import cv2
import fitz  # PyMuPDF
import numpy as np


# ── Loading ──────────────────────────────────────────────────────────────────

def load_image(path: str) -> np.ndarray:
    """Load an image from disk.

    If *path* points to a PDF, the first page is rasterised at 200 DPI and
    returned as a BGR ``np.ndarray``.  Otherwise the file is loaded directly
    via OpenCV.

    Raises
    ------
    FileNotFoundError
        If *path* does not exist.
    ValueError
        If the file cannot be decoded.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {path}")

    if p.suffix.lower() == ".pdf":
        images = pdf_to_images(path)
        if not images:
            raise ValueError(f"Could not extract images from PDF: {path}")
        return images[0]

    img = cv2.imread(str(p), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"Failed to decode image: {path}")
    return img


def load_image_from_bytes(data: bytes) -> np.ndarray:
    """Decode an in-memory image buffer to a BGR ``np.ndarray``.

    Raises
    ------
    ValueError
        If the buffer cannot be decoded by OpenCV.
    """
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Failed to decode image from bytes")
    return img


# ── Transformations ──────────────────────────────────────────────────────────

def to_grayscale(image: np.ndarray) -> np.ndarray:
    """Convert a BGR image to single-channel grayscale.

    If the image is already single-channel it is returned unchanged.
    """
    if len(image.shape) == 2:
        return image
    if image.shape[2] == 1:
        return image.squeeze(axis=2)
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def resize_image(image: np.ndarray, max_dim: int = 2048) -> np.ndarray:
    """Resize *image* so that its largest dimension is at most *max_dim* pixels.

    Aspect ratio is preserved.  If the image is already within bounds it is
    returned as-is.
    """
    h, w = image.shape[:2]
    if max(h, w) <= max_dim:
        return image

    scale = max_dim / max(h, w)
    new_w = int(w * scale)
    new_h = int(h * scale)
    return cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)


# ── Region Extraction ────────────────────────────────────────────────────────

def extract_regions(
    image: np.ndarray,
    contours: Sequence[np.ndarray],
) -> list[np.ndarray]:
    """Crop rectangular regions from *image* given OpenCV *contours*.

    Each contour is bounded by its axis-aligned bounding rectangle.
    Regions whose area is smaller than 100 px² are skipped.

    Returns
    -------
    list[np.ndarray]
        List of cropped sub-images (BGR).
    """
    regions: list[np.ndarray] = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if w * h < 100:
            continue
        region = image[y : y + h, x : x + w].copy()
        regions.append(region)
    return regions


# ── Encoding ─────────────────────────────────────────────────────────────────

def image_to_base64(image: np.ndarray) -> str:
    """Encode a BGR ``np.ndarray`` as a Base-64 PNG string.

    This is useful for embedding thumbnails in JSON API responses.
    """
    success, buffer = cv2.imencode(".png", image)
    if not success:
        raise ValueError("Failed to encode image to PNG")
    return base64.b64encode(buffer.tobytes()).decode("utf-8")


# ── PDF Conversion ───────────────────────────────────────────────────────────

def pdf_to_images(
    pdf_path: str,
    dpi: int = 200,
) -> list[np.ndarray]:
    """Convert every page of a PDF into BGR ``np.ndarray`` images.

    Uses PyMuPDF (``fitz``) for fast, dependency-light rendering.

    Parameters
    ----------
    pdf_path:
        Path to the PDF file.
    dpi:
        Render resolution (default 200 DPI balances quality and speed).

    Returns
    -------
    list[np.ndarray]
        One BGR image per page.
    """
    images: list[np.ndarray] = []
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)

    with fitz.open(pdf_path) as doc:
        for page in doc:
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            # PyMuPDF returns RGB samples
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                pix.height, pix.width, 3
            )
            # Convert RGB → BGR for OpenCV convention
            img_bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            images.append(img_bgr)

    return images
