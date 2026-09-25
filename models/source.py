"""
models/source.py — SQLAlchemy ORM model for the regulatory source registry.

Tracks every official regulatory document/webpage ingested by MochaTrade.
Provides full provenance: who issued it, when retrieved, content hash for
deduplication, and current processing/source status.

This is the authoritative source of truth — ChromaDB is supplementary only.
"""
import datetime
import uuid

from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for all MochaTrade ORM models."""
    pass


class SourceRegistry(Base):
    """Regulatory document / source entry.

    Every field marked nullable=True may legitimately be unknown at ingestion
    time. Unknown values must remain NULL — never guessed or fabricated.
    """
    __tablename__ = "source_registry"

    # Primary identity
    source_id = Column(
        String(64),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        doc="Internal stable identifier (UUIDv4).",
    )

    # Provenance
    jurisdiction = Column(String(64),  nullable=False, index=True,
                          doc="Country / market e.g. 'UAE', 'Brazil'.")
    regulator    = Column(String(128), nullable=False,
                          doc="Issuing authority e.g. 'VARA', 'BCB'.")
    title        = Column(String(256), nullable=False,
                          doc="Official document title.")
    source_url   = Column(Text, nullable=True,
                          doc="Canonical source URL from the regulator domain.")

    # Format / classification
    source_type     = Column(String(16), nullable=False,
                             doc="'PDF', 'HTML', 'DOCX', etc.")
    instrument_type = Column(String(32), nullable=True,
                             doc="'Act', 'Regulation', 'Circular', 'Guidance', etc.")

    # Content integrity
    content_hash = Column(String(64), nullable=True, index=True,
                          doc="SHA-256 hex digest of original file bytes. "
                              "Used for deduplication and change detection.")
    storage_uri  = Column(Text, nullable=True,
                          doc="MinIO object key where original bytes are preserved.")

    # Temporal metadata (nullable — unknown dates stay NULL)
    published_at = Column(DateTime, nullable=True)
    effective_at = Column(DateTime, nullable=True)
    retrieved_at = Column(DateTime, default=datetime.datetime.utcnow,
                          doc="When MochaTrade fetched / uploaded the source.")

    # Status
    source_status = Column(
        String(32),
        default="active",
        doc="'active', 'superseded', 'repealed', 'unknown'.",
    )
    processing_status = Column(
        String(32),
        default="discovered",
        doc="'discovered' → 'fetched' → 'parsed' → 'reviewed' | 'failed'.",
    )

    # Parser metadata
    parser_warnings = Column(
        Text, nullable=True,
        doc="JSON-encoded list of parser warnings or error messages.",
    )

    def __repr__(self) -> str:
        return (
            f"<SourceRegistry source_id={self.source_id!r} "
            f"jurisdiction={self.jurisdiction!r} "
            f"processing_status={self.processing_status!r}>"
        )
