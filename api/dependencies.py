import logging

from config import settings
from core import (
    Chunker,
    Embeddings,
    Generator,
    Parser,
    Retriever,
    Uploader,
)

logger = logging.getLogger(__name__)

try:
    from parsers.router import ParserRouter
except ImportError:
    class ParserRouter:
        """Fallback for ParserRouter until v1-v3 are implemented."""
        def parse(self, file_bytes, filename, **kwargs):
            raise NotImplementedError("ParserRouter not yet fully implemented")


def _safe_init(label, factory):
    try:
        return factory()
    except Exception as exc:  # missing optional deps / infra in lightweight envs
        logger.warning("Optional service '%s' unavailable: %s", label, exc)
        return None


# Global shared singletons (None when optional infra deps are unavailable;
# endpoints that need them return 503 with a clear message instead of crashing import).
uploader = _safe_init("uploader", Uploader) if Uploader is not None else None
parser = _safe_init("parser", Parser)
parser_router = _safe_init("parser_router", ParserRouter)
chunker = _safe_init(
    "chunker",
    lambda: Chunker(chunk_size=settings.chunk_size, chunk_overlap=settings.chunk_overlap),
)
embeddings = _safe_init("embeddings", Embeddings) if Embeddings is not None else None


def _init_retriever():
    if Retriever is None or embeddings is None:
        raise RuntimeError("Retriever unavailable (chromadb not installed)")
    return Retriever(embeddings=embeddings)


retriever = _safe_init("retriever", _init_retriever)
generator = _safe_init(
    "generator",
    lambda: Generator(
        ollama_host=settings.ollama_host,
        ollama_port=settings.ollama_port,
        model=settings.ollama_model,
    ),
) if Generator is not None else None
