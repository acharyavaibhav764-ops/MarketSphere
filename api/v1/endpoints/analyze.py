"""
api/v1/endpoints/analyze.py — AI Rule Analyzer API.

  POST /api/v1/analyze/extract — Upload a document (PDF/DOCX/TXT/MD), extract
                                 normalized text via the existing parser, and
                                 split it into editable candidate rules.
  POST /api/v1/analyze          — Analyze every rule (deterministic engine by
                                 default; optional LLM path with ?mode=llm).
  POST /api/v1/analyze/chat     — Context-aware follow-up Q&A over the current
                                 rule set and its latest analysis.

Documents are treated strictly as DATA: they are parsed to text and never
executed, and their contents never override system instructions.
"""
import logging
from pathlib import PurePath
from typing import Literal, Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status

from schemas.analysis import (
    AnalyzeRequest,
    AnalysisResponse,
    ChatRequest,
    ChatResponse,
    ExtractResponse,
)
from services.rule_analyzer import (
    MAX_RULE_CHARS,
    MAX_RULES,
    analyze_rules,
    analyze_with_llm,
    answer_followup,
    split_rules,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analyze", tags=["AI Rule Analyzer"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".md"}


@router.post(
    "/extract",
    response_model=ExtractResponse,
    summary="Upload a document and extract candidate rules",
)
async def extract_rules_from_document(
    file: UploadFile = File(..., description="PDF, DOCX, TXT, or Markdown file."),
) -> ExtractResponse:
    filename = PurePath(file.filename or "").name
    if not filename:
        raise HTTPException(status_code=400, detail="A filename is required.")
    ext = PurePath(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file type '{ext or 'unknown'}'. "
                "Please upload a PDF, DOCX, or TXT document."
            ),
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=400,
            detail="The document exceeds the 10 MB limit. Please upload a smaller file.",
        )

    # Extraction layer: normalized text (never raw bytes to LLM).
    # Plain-text files are decoded directly to preserve line structure
    # (the generic parser collapses whitespace); binary formats go through
    # the existing parser infrastructure.
    full_text = ""
    if ext in (".txt", ".md"):
        for encoding in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
            try:
                full_text = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            full_text = content.decode("utf-8", errors="replace")
    else:
        try:
            from core.parser import Parser

            # parse_raw keeps line breaks so numbered/bulleted rules survive.
            pages = Parser().parse_raw(content, filename)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception as exc:
            logger.exception("Document parsing failed for %s", filename)
            raise HTTPException(
                status_code=400,
                detail=f"Unable to read this document ({exc}). It may be corrupted or scanned without text.",
            )
        full_text = "\n\n".join(t for _, t in pages)
    full_text = full_text.strip()
    if not full_text:
        raise HTTPException(
            status_code=400,
            detail="Unable to read this document — no text could be extracted. "
                   "Scanned images without an OCR text layer are not supported.",
        )

    all_rules = split_rules(full_text, max_rules=10**6)
    if not all_rules:
        raise HTTPException(
            status_code=400,
            detail="No identifiable rules were found in this document. "
                   "Try pasting the rules as text instead.",
        )
    truncated = len(all_rules) > MAX_RULES
    return ExtractResponse(
        filename=filename,
        size_bytes=len(content),
        total=len(all_rules),
        truncated=truncated,
        text_preview=full_text[:500],
        rules=[
            {"number": r["number"], "text": r["text"][:MAX_RULE_CHARS]}
            for r in all_rules[:MAX_RULES]
        ],
    )


@router.post(
    "",
    response_model=AnalysisResponse,
    summary="Analyze every rule and detect cross-rule conflicts",
)
async def analyze_rule_set(
    request: AnalyzeRequest,
    mode: Literal["deterministic", "llm"] = Query(
        "deterministic", description="'deterministic' (instant) or 'llm' (model-backed).",
    ),
) -> AnalysisResponse:
    cleaned = [(r or "").strip() for r in (request.rules or [])]
    cleaned = [r for r in cleaned if r]
    if not cleaned:
        raise HTTPException(
            status_code=400,
            detail="No rules were provided. Type, paste, or upload rules first.",
        )
    if len(cleaned) > MAX_RULES:
        raise HTTPException(
            status_code=400,
            detail=f"Too many rules ({len(cleaned)}). The limit is {MAX_RULES} per analysis.",
        )
    too_long = [i + 1 for i, r in enumerate(cleaned) if len(r) > MAX_RULE_CHARS]
    if too_long:
        raise HTTPException(
            status_code=400,
            detail=f"Rule(s) {too_long} exceed {MAX_RULE_CHARS} characters. Please shorten them.",
        )

    if mode == "llm":
        return _analyze_via_llm(cleaned)
    try:
        return AnalysisResponse(**analyze_rules(cleaned))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


def _analyze_via_llm(cleaned: list[str]) -> AnalysisResponse:
    """Model-backed path: only when explicitly enabled and reachable."""
    import os
    import socket

    if os.getenv("ANALYZER_LLM", "false").lower() != "true":
        raise HTTPException(
            status_code=503,
            detail="LLM analysis is disabled. Run the deterministic analysis instead — "
                   "it needs no model server.",
        )
    from config import settings
    from api import dependencies as deps

    generator = getattr(deps, "generator", None)
    if generator is None:
        raise HTTPException(
            status_code=503,
            detail="No language model is configured in this environment.",
        )
    try:
        sock = socket.create_connection(
            (settings.ollama_host, int(settings.ollama_port)), timeout=3
        )
        sock.close()
    except OSError:
        raise HTTPException(
            status_code=503,
            detail="The model server is unreachable. Use deterministic analysis instead.",
        )
    try:
        return AnalysisResponse(**analyze_with_llm(cleaned, generator))
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=502, detail=f"Model output could not be used: {exc}"
        )


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Ask a follow-up question about the analyzed rules",
)
async def analyzer_chat(request: ChatRequest) -> ChatResponse:
    question = (request.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Please type a question first.")
    if len(question) > 2000:
        raise HTTPException(status_code=400, detail="The question is too long.")

    rules = [(r or "").strip() for r in (request.rules or [])]
    rules = [r for r in rules if r][:MAX_RULES]

    analysis: Optional[dict] = None
    if request.analysis is not None:
        analysis = request.analysis.model_dump()
    elif rules:
        # No prior analysis supplied: analyze server-side so chat has context.
        analysis = analyze_rules(rules)

    result = answer_followup(rules, analysis, question)
    return ChatResponse(content=result["content"], action=result.get("action"))
