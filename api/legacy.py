from fastapi import APIRouter, File, HTTPException, UploadFile
from api import dependencies as deps
from api.v1.endpoints.query import query_pipeline
from schemas import (
    FileIndexResponse,
    FileUploadItem,
    FileUploadResponse,
    QueryRequest,
    QueryResponse,
)

legacy_router = APIRouter(tags=["Legacy (v0.1/v0.3)"])


def _require(service, name: str):
    if service is None:
        raise HTTPException(
            status_code=503,
            detail=(
                f"{name} is unavailable in this environment "
                "(missing optional infrastructure dependency). "
                "Run the full docker-compose stack for RAG ingestion."
            ),
        )
    return service


@legacy_router.post(
    "/upload",
    response_model=FileUploadResponse,
    deprecated=True,
    summary="[Legacy] Upload multiple files",
)
async def legacy_upload(files: list[UploadFile] = File(...)) -> FileUploadResponse:
    uploader = _require(deps.uploader, "Uploader")
    uploaded = uploader.upload_files(files)
    return FileUploadResponse(
        message="Files uploaded successfully",
        count=len(uploaded),
        files=[
            FileUploadItem(
                file_id=item["file_id"],
                filename=item["filename"],
                size_bytes=item["size_bytes"],
            )
            for item in uploaded
        ],
    )


@legacy_router.post(
    "/chunk-and-embed/{file_id}",
    response_model=FileIndexResponse,
    deprecated=True,
    summary="[Legacy] Chunk and embed one uploaded file",
)
async def legacy_chunk_and_embed(file_id: str) -> FileIndexResponse:
    uploader = _require(deps.uploader, "Uploader")
    parser = _require(deps.parser, "Parser")
    chunker = _require(deps.chunker, "Chunker")
    embeddings = _require(deps.embeddings, "Embeddings")
    retriever = _require(deps.retriever, "Retriever")
    content, filename = uploader.download_file(file_id)
    pages = parser.parse(content, filename)
    chunks, metadatas, chunk_ids = chunker.split(pages, file_id, filename)
    vectors = embeddings.embed(chunks)
    retriever.upsert(
        ids=chunk_ids,
        documents=chunks,
        metadatas=metadatas,
        embeddings=vectors,
    )
    return FileIndexResponse(
        file_id=file_id,
        filename=filename,
        collection=retriever.collection_name,
        total_chunks=len(chunks),
        indexed_chunks=len(chunks),
    )


@legacy_router.post(
    "/generate",
    response_model=QueryResponse,
    deprecated=True,
    summary="[Legacy] Answer question using indexed documents",
)
async def legacy_generate(request: QueryRequest) -> QueryResponse:
    return await query_pipeline(request=request)
