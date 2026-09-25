"""
services/source_service.py — Business logic for regulatory source ingestion.

Encapsulates MinIO upload, SHA-256 hashing, and PostgreSQL record creation
so that the API endpoint stays thin. Every function is independently testable
without standing up FastAPI.

Deduplication: if the same bytes (same SHA-256 hash) have already been
ingested, the function returns status="duplicate" instead of creating a new
record. A new version record is created when the content changes.
"""
import hashlib
import io
import logging
import uuid

from minio import Minio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.source import SourceRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure helpers — no I/O, fully unit-testable
# ---------------------------------------------------------------------------

def compute_hash(content: bytes) -> str:
    """Return the SHA-256 hex digest of *content*.

    Args:
        content: Raw bytes of the regulatory document.

    Returns:
        str: 64-character lowercase hex string.
    """
    return hashlib.sha256(content).hexdigest()


# ---------------------------------------------------------------------------
# MinIO helpers
# ---------------------------------------------------------------------------

def upload_to_minio(client: Minio | None, content: bytes, filename: str) -> str:
    """Upload *content* bytes to the regulatory MinIO bucket.

    Args:
        client:   Authenticated ``minio.Minio`` instance (or None in tests).
        content:  Raw file bytes to preserve.
        filename: Original filename used to build the object key suffix.

    Returns:
        str: MinIO object key of the uploaded object.

    Raises:
        Exception: Propagates any MinIO S3Error on failure.
    """
    object_key = f"sources/{uuid.uuid4()}/{filename}"
    if client is None:
        logger.warning("MinIO client not provided; skipping MinIO upload for %s", object_key)
        return object_key

    client.put_object(
        bucket_name=settings.regulatory_bucket,
        object_name=object_key,
        data=io.BytesIO(content),
        length=len(content),
        content_type="application/octet-stream",
    )
    logger.info("Uploaded source to MinIO: %s", object_key)
    return object_key



# ---------------------------------------------------------------------------
# Core registration logic
# ---------------------------------------------------------------------------

async def register_source(
    db: AsyncSession,
    minio_client: Minio,
    content: bytes,
    filename: str,
    jurisdiction: str,
    regulator: str,
    source_type: str,
    title: str,
    source_url: str | None = None,
    instrument_type: str | None = None,
) -> dict:
    """Ingest one regulatory document into the source registry.

    Steps:
    1. Compute SHA-256 hash of *content*.
    2. Check for an existing record with the same hash (deduplication).
    3. Upload original bytes to MinIO (regulatory_bucket).
    4. Create a ``SourceRegistry`` row and commit.

    Args:
        db:              Async SQLAlchemy session (injected by FastAPI Depends).
        minio_client:    Authenticated MinIO client.
        content:         Raw file bytes of the regulatory document.
        filename:        Original filename (used for MinIO key and logging).
        jurisdiction:    Country / market code e.g. ``"UAE"``.
        regulator:       Issuing authority e.g. ``"VARA"``.
        source_type:     File type tag: ``"PDF"``, ``"HTML"``, ``"DOCX"``.
        title:           Official document title.
        source_url:      Canonical URL from the regulator domain (optional).
        instrument_type: ``"Act"``, ``"Circular"``, ``"Guidance"``, etc.

    Returns:
        dict: ``{"status": "created", "source_id": str}``
              or ``{"status": "duplicate", "content_hash": str}``.
    """
    content_hash = compute_hash(content)

    # --- Deduplication check ---
    result = await db.execute(
        select(SourceRegistry).where(SourceRegistry.content_hash == content_hash)
    )
    existing = result.scalars().first()
    if existing is not None:
        logger.info(
            "Duplicate source detected (hash=%s, existing source_id=%s).",
            content_hash,
            existing.source_id,
        )
        return {"status": "duplicate", "content_hash": content_hash,
                "existing_source_id": existing.source_id}

    # --- Persist original bytes to MinIO ---
    storage_uri = upload_to_minio(minio_client, content, filename)

    # --- Create DB record ---
    record = SourceRegistry(
        jurisdiction=jurisdiction,
        regulator=regulator,
        title=title,
        source_url=source_url,
        source_type=source_type,
        instrument_type=instrument_type,
        content_hash=content_hash,
        storage_uri=storage_uri,
        processing_status="fetched",
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    logger.info(
        "Registered new source source_id=%s jurisdiction=%s.",
        record.source_id,
        jurisdiction,
    )
    return {"status": "created", "source_id": record.source_id}
