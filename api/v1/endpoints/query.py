from fastapi import APIRouter, HTTPException

from config import settings
from api import dependencies as deps
from schemas.query import QueryRequest, QueryResponse, SourceItem

router = APIRouter(tags=["Query"])


# POST /api/v1/query
@router.post(
    "/query",
    response_model=QueryResponse,
    summary="Query RAG pipeline",
    description="Retrieve relevant ChromaDB chunks and generate an answer using Ollama.",
)
async def query_pipeline(request: QueryRequest) -> QueryResponse:
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question must not be empty")

    if deps.retriever is None or deps.generator is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "RAG pipeline is unavailable in this environment "
                "(ChromaDB/Ollama not configured). "
                "Run the full docker-compose stack for live retrieval."
            ),
        )

    # Retrieve relevant chunks
    retrieved = deps.retriever.retrieve(question, k=settings.retrieval_k)
    documents = retrieved.get("documents", [[]])[0]
    metadatas = retrieved.get("metadatas", [[]])[0]
    distances = retrieved.get("distances", [[]])[0]
    if not documents:
        raise HTTPException(status_code=400, detail="No indexed document chunks were found")

    # Build prompt and generate response with local Ollama
    prompt = deps.generator.build_prompt(question, documents, metadatas)
    answer = deps.generator.generate(prompt)

    # Return response
    return QueryResponse(
        question=question,
        answer=answer,
        model=deps.generator.model,
        sources=[
            SourceItem(metadata=metadata, distance=distance)
            for metadata, distance in zip(metadatas, distances)
        ],
    )
