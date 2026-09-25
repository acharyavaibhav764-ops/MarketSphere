from fastapi import APIRouter, File, HTTPException, UploadFile, status

from api import dependencies as deps
from schemas.document import (
    DocumentIngestItem,
    DocumentIngestResponse,
)

router = APIRouter(prefix="/documents", tags=["Documents"])


def _require(service, name: str):
    if service is None:
        raise HTTPException(
            status_code=503,
            detail=(
                f"{name} is unavailable in this environment "
                "(missing optional infrastructure dependency). "
                "Run the full docker-compose stack for document ingestion."
            ),
        )
    return service


# POST /api/v1/documents/
@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=DocumentIngestResponse,
    summary="Upload and ingest documents",
    description=(
        "Upload one or more documents, parse text, chunk, generate embeddings, "
        "and index them in ChromaDB synchronously."
    ),
)
async def ingest_documents(
    files: list[UploadFile] = File(...),
) -> DocumentIngestResponse:
    if not files:
        raise HTTPException(status_code=400, detail="At least one file is required")

    uploader = _require(deps.uploader, "Uploader")
    parser_router = _require(deps.parser_router, "ParserRouter")
    chunker = _require(deps.chunker, "Chunker")
    embeddings = _require(deps.embeddings, "Embeddings")
    retriever = _require(deps.retriever, "Retriever")

    # Upload files to MinIO
    uploaded_documents = uploader.upload_files(files)

    ingested_items = []
    for item in uploaded_documents:
        doc_id = item["document_id"]
        filename = item["filename"]
        size_bytes = item["size_bytes"]

        # Download and parse text pages using the new parser router
        content, _ = uploader.download_file(doc_id)
        docling_doc = parser_router.parse(content, filename=filename)

        # Chunk text and attach metadata using HybridChunker (or legacy chunker)
        chunk_result = chunker.split(docling_doc, doc_id, filename)

        # Handle both the new list[TextChunk] and the legacy tuple format in case HybridChunker is not fully implemented
        if isinstance(chunk_result, tuple) and len(chunk_result) == 3:
            chunks, metadatas, chunk_ids = chunk_result
        else:
            chunks = [c.text for c in chunk_result]
            metadatas = [c.metadata for c in chunk_result]
            chunk_ids = [c.chunk_id for c in chunk_result]

        # Generate vector embeddings
        vectors = embeddings.embed(chunks)

        # Persist to ChromaDB
        retriever.upsert(
            ids=chunk_ids,
            documents=chunks,
            metadatas=metadatas,
            embeddings=vectors,
        )

        # Append to list of ingested items
        ingested_items.append(
            DocumentIngestItem(
                document_id=doc_id,
                filename=filename,
                size_bytes=size_bytes,
                collection=retriever.collection_name,
                total_chunks=len(chunks),
                status="indexed",
            )
        )

    return DocumentIngestResponse(
        message="Documents uploaded and indexed successfully",
        count=len(ingested_items),
        documents=ingested_items,
    )
