import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Central application configuration with environment variable fallbacks."""

    # MinIO
    minio_endpoint: str = os.getenv("MINIO_ENDPOINT", "minio:9000")
    minio_bucket: str = os.getenv("MINIO_BUCKET", "honeywell-documents")
    minio_access_key: str = os.getenv("MINIO_ACCESS_KEY", os.getenv("MINIO_ROOT_USER", ""))
    minio_secret_key: str = os.getenv("MINIO_SECRET_KEY", os.getenv("MINIO_ROOT_PASSWORD", ""))

    # ChromaDB
    chroma_host: str | None = os.getenv("CHROMA_HOST")
    chroma_port: int = int(os.getenv("CHROMA_PORT", "8000"))
    chroma_path: str = os.getenv("CHROMA_PATH", "./chroma_data")
    chroma_collection: str = os.getenv("CHROMA_COLLECTION", "my_documents")

    # Ollama
    ollama_host: str = os.getenv("OLLAMA_HOST", "ollama")
    ollama_port: str = os.getenv("OLLAMA_PORT", "11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.2:3b")

    # RAG & Ingestion Parameters
    chunk_size: int = int(os.getenv("CHUNK_SIZE", "1000"))
    chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", "200"))
    retrieval_k: int = int(os.getenv("RETRIEVAL_K", "5"))

    # Parsing Architecture — HybridChunker tokenizer
    chunker_tokenizer: str = os.getenv(
        "CHUNKER_TOKENIZER", "sentence-transformers/all-MiniLM-L6-v2"
    )

    # Parsing Architecture v2 — local lightweight picture description (DOCX/PPTX)
    # Primary preset: smolvlm (HuggingFaceTB/SmolVLM-256M-Instruct, ~256MB VRAM, runs in-process).
    # Escalation preset: granite_vision (Granite-Vision-3.3-2B via Ollama).
    # DeepSeek-OCR2 is NOT used here — it requires ≥8GB VRAM (GTX 1650 = 4GB).
    # DeepSeek-OCR2 integration is planned for v5 (PDF branch) on production hardware.
    # See parsing_architecture_plan.md for the v6 vLLM migration note.
    picture_description_preset: str = os.getenv("PICTURE_DESCRIPTION_PRESET", "smolvlm")
    picture_description_prompt: str = os.getenv(
        "PICTURE_DESCRIPTION_PROMPT",
        "Describe this image in 2-3 sentences. Be concise and accurate.",
    )
    enable_picture_description: bool = (
        os.getenv("ENABLE_PICTURE_DESCRIPTION", "false").lower() == "true"
    )

    # Parsing Architecture v3 — LibreOffice headless converter (.doc / .ppt)
    libreoffice_binary: str = os.getenv("LIBREOFFICE_BINARY", "")
    libreoffice_timeout_seconds: int = int(os.getenv("LIBREOFFICE_TIMEOUT_SECONDS", "60"))

    # Parsing Architecture v5 — PDF per-page triage (PdfPageRouter)
    # DeepSeek-OCR2 requires ≥8 GB VRAM; disabled by default.
    # Do NOT enable on the GTX 1650 dev machine.
    # vLLM serving (v6) is explicitly NOT implemented — HF Transformers only.
    enable_deepseek_ocr2: bool = (
        os.getenv("ENABLE_DEEPSEEK_OCR2", "false").lower() == "true"
    )
    deepseek_model_id: str = os.getenv("DEEPSEEK_MODEL_ID", "deepseek-ai/DeepSeek-OCR-2")

    # Tunable triage thresholds — calibrate against your own PDF corpus before production
    # (see RAG_PARSING_ARCHITECTURE_FINAL.md §7 for guidance)
    pdf_triage_text_threshold: int = int(os.getenv("PDF_TRIAGE_TEXT_THRESHOLD", "10"))
    pdf_triage_image_ratio_threshold: float = float(
        os.getenv("PDF_TRIAGE_IMAGE_RATIO", "0.5")
    )

    # MochaTrade regulatory source registry
    regulatory_bucket: str = os.getenv("REGULATORY_BUCKET", "mocha-regulatory-sources")
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql+asyncpg://user:pass@localhost/mocha"
    )


settings = Settings()
