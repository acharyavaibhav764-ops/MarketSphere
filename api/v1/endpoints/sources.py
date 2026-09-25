"""
api/v1/endpoints/sources.py — Regulatory source ingestion API.

Provides:
  POST /api/v1/sources/ingest — Upload and register a regulatory document.
  GET  /api/v1/sources        — List all sources and their processing status.
  GET  /api/v1/sources/{id}  — Retrieve a single source record.

These endpoints do NOT touch the existing /documents ingestion pipeline.
All database and MinIO operations are delegated to services/source_service.py.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from models.source import SourceRegistry
from schemas.source import SourceDetailResponse, SourceIngestResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sources", tags=["Regulatory Sources"])


@router.post(
    "/ingest",
    status_code=status.HTTP_201_CREATED,
    response_model=SourceIngestResponse,
    summary="Upload and register an official regulatory document",
    description=(
        "Accepts a regulatory PDF, DOCX, or HTML file along with its metadata. "
        "Computes a SHA-256 hash for deduplication, preserves original bytes in "
        "MinIO, and creates a SourceRegistry record. "
        "Returns status='duplicate' if the same bytes were already registered."
    ),
)
async def ingest_source(
    file: UploadFile = File(..., description="The regulatory document file."),
    jurisdiction: str = Form(..., description="Country / market e.g. 'UAE'."),
    regulator: str = Form(..., description="Issuing authority e.g. 'VARA'."),
    title: str = Form(..., description="Official document title."),
    source_type: str = Form(..., description="'PDF', 'HTML', or 'DOCX'."),
    source_url: str = Form(None, description="Canonical URL from regulator domain."),
    instrument_type: str = Form(
        None, description="'Act', 'Circular', 'Guidance', etc."
    ),
    db: AsyncSession = Depends(get_db),
) -> SourceIngestResponse:
    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    from services.source_service import register_source

    result = await register_source(
        db=db,
        minio_client=None,
        content=content,
        filename=file.filename or "upload",
        jurisdiction=jurisdiction,
        regulator=regulator,
        source_type=source_type,
        title=title,
        source_url=source_url,
        instrument_type=instrument_type,
    )
    return SourceIngestResponse(**result)


@router.get(
    "",
    summary="List regulatory sources",
    description="Returns all source registry entries. Filter by ?processing_status= for processing status.",
)
async def list_sources(
    processing_status: Optional[str] = Query(None, description="Filter by processing status"),
    jurisdiction: Optional[str] = Query(None, description="Filter by jurisdiction"),
    db: AsyncSession = Depends(get_db),
):
    query = select(SourceRegistry)
    if processing_status:
        query = query.where(SourceRegistry.processing_status == processing_status)
    if jurisdiction:
        query = query.where(SourceRegistry.jurisdiction == jurisdiction)

    res = await db.execute(query)
    sources = res.scalars().all()
    return {
        "total": len(sources),
        "sources": [SourceDetailResponse.model_validate(s) for s in sources],
    }


@router.get(
    "/{source_id}",
    response_model=SourceDetailResponse,
    summary="Get a single source record",
)
async def get_source(
    source_id: str,
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(SourceRegistry).where(SourceRegistry.source_id == source_id))
    source = res.scalars().first()
    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source with id '{source_id}' not found.",
        )
    return SourceDetailResponse.model_validate(source)

