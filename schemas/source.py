"""
schemas/source.py — Pydantic request/response schemas for source ingestion.

Separate from the ORM models in models/source.py.  The API layer uses these
for serialization/validation; the ORM layer handles DB persistence.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class SourceIngestResponse(BaseModel):
    """Returned by POST /api/v1/sources/ingest."""

    status: Literal["created", "duplicate"]
    source_id: Optional[str] = Field(
        None, description="Populated when status='created'."
    )
    content_hash: Optional[str] = Field(
        None, description="SHA-256 of the uploaded bytes."
    )
    existing_source_id: Optional[str] = Field(
        None, description="Populated when status='duplicate'."
    )


class SourceDetailResponse(BaseModel):
    """Returned by GET /api/v1/sources/{source_id}."""

    source_id: str
    jurisdiction: str
    regulator: str
    title: str
    source_url: Optional[str] = None
    source_type: str
    instrument_type: Optional[str] = None
    content_hash: Optional[str] = None
    storage_uri: Optional[str] = None
    source_status: str
    processing_status: str

    class Config:
        from_attributes = True
