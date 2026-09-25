"""
parsers/pdf_page_router.py — v5 per-page PDF parser.

Replaces PdfStubParser (v4) as the handler for .pdf files.

Routing decision (per page, not per document):
  ┌──────────────────────────────────────────────────────────┐
  │  PyMuPDF cheap triage (milliseconds, no model loaded)   │
  │  signals: text token count, image area ratio, tables    │
  └──────────────────────────────────────────────────────────┘
         │                    │                   │
   has_text=True         has_text=True      no text OR
   no tables             table detected     image_ratio > 0.5
   low image ratio
         │                    │                   │
   PYMUPDF4LLM           DOCLING            DEEPSEEK_OCR2
   (fast markdown)     (structure-aware)   (HF Transformers)
                                           NOT vLLM — v6 excluded

All pages are re-assembled in (page_number, y-position) order into a single
DoclingDocument before returning, so the downstream chunker receives one flat
ordered block list regardless of which backend touched each page.

Hardware note: DEEPSEEK_OCR2 requires ≥8 GB VRAM. The route is silently
skipped (logged as WARNING) unless ENABLE_DEEPSEEK_OCR2=true in environment.
v6 (vLLM serving) is explicitly out of scope per parsing_architecture_plan.md.
"""
import io
import logging
import tempfile
from pathlib import Path
from typing import Literal

import fitz  # PyMuPDF
from docling_core.types.doc import DoclingDocument

from config import settings
from .base import BaseParser

logger = logging.getLogger(__name__)

# Type alias for triage routing decision
Route = Literal["PYMUPDF4LLM", "DOCLING", "DEEPSEEK_OCR2"]


# ---------------------------------------------------------------------------
# Per-page triage — cheap, no models, just PyMuPDF signals
# ---------------------------------------------------------------------------

def _triage_page(page: fitz.Page) -> tuple[Route, bool]:
    """Classify a single fitz.Page to determine its parse route.

    Three cheap signals are extracted from the page without loading any model:
    - text_tokens: word count from the embedded text layer.
    - image_ratio: fraction of page area covered by embedded images.
    - has_table:   PyMuPDF geometric table detector (no ML).

    Args:
        page: An open ``fitz.Page`` object.

    Returns:
        tuple[Route, bool]: ``(route, is_front_matter)``.
            route:           One of ``"PYMUPDF4LLM"``, ``"DOCLING"``,
                             ``"DEEPSEEK_OCR2"``.
            is_front_matter: True when the page looks like a cover or title page
                             that should be skipped (not chunked).

    Note:
        Threshold values (pdf_triage_text_threshold, pdf_triage_image_ratio_threshold)
        are sourced from config.py and should be tuned against a real corpus sample
        before shipping (see RAG_PARSING_ARCHITECTURE_FINAL.md §7).
    """
    text_tokens = len(page.get_text().split())
    has_text = text_tokens > settings.pdf_triage_text_threshold

    # Image area ratio: sum bounding-box areas of all embedded images
    page_area = page.rect.width * page.rect.height
    if page_area > 0:
        image_area = sum(
            abs((img["bbox"][2] - img["bbox"][0]) * (img["bbox"][3] - img["bbox"][1]))
            for img in page.get_image_info()
        )
        image_ratio = image_area / page_area
    else:
        image_ratio = 0.0

    # Geometric table detection (no external model)
    has_table = len(page.find_tables().tables) > 0

    # Front matter heuristic: page 0 or 1, very few words, mostly image
    is_front_matter = (
        page.number <= 1
        and text_tokens < 30
        and image_ratio > 0.6
    )

    # Route decision
    if not has_text or image_ratio > settings.pdf_triage_image_ratio_threshold:
        return "DEEPSEEK_OCR2", is_front_matter
    elif has_table:
        return "DOCLING", is_front_matter
    else:
        return "PYMUPDF4LLM", is_front_matter


# ---------------------------------------------------------------------------
# Per-route parsers
# ---------------------------------------------------------------------------

def _parse_with_pymupdf4llm(page: fitz.Page, page_number: int) -> list[dict]:
    """Fast markdown extraction from a clean digital page using pymupdf4llm.

    Args:
        page:        The ``fitz.Page`` object.
        page_number: Zero-based page index (used for block ordering).

    Returns:
        list[dict]: One block dict with text, page, source_backend, block_type.
    """
    import pymupdf4llm
    # to_markdown accepts the parent Document and a pages list (0-indexed)
    text = pymupdf4llm.to_markdown(page.parent, pages=[page_number])
    if not text.strip():
        return []
    return [
        {
            "text": text,
            "page": page_number,
            "source_backend": "pymupdf4llm",
            "block_type": "paragraph",
        }
    ]


def _parse_with_docling(
    page_bytes: bytes, filename: str, page_number: int
) -> list[dict]:
    """Structure-aware extraction for table-detected pages using Docling.

    The single-page PDF bytes are passed to Docling's DocumentConverter so that
    TableFormer can extract table structure without being confused by surrounding
    pages parsed differently.

    Args:
        page_bytes:  Raw bytes of a single-page PDF (created by fitz.open().write()).
        filename:    Original filename (used for DocumentStream name).
        page_number: Zero-based page index for block ordering metadata.

    Returns:
        list[dict]: One block dict per extracted text item.
    """
    from docling.document_converter import DocumentConverter
    from docling_core.types.io import DocumentStream

    stream = DocumentStream(name=filename, stream=io.BytesIO(page_bytes))
    try:
        result = DocumentConverter().convert(stream)
    except Exception as exc:
        logger.warning(
            "Docling failed on page %d of %s: %s. Skipping page.",
            page_number, filename, exc,
        )
        return []

    blocks = []
    for item, _ in result.document.iterate_items():
        text = getattr(item, "text", "").strip()
        if text:
            blocks.append(
                {
                    "text": text,
                    "page": page_number,
                    "source_backend": "docling",
                    "block_type": str(item.label),
                }
            )
    return blocks


def _parse_with_deepseek(image_path: str, page_number: int) -> list[dict]:
    """OCR a scanned/image-heavy page using DeepSeek-OCR2 (HF Transformers).

    This function uses HuggingFace ``transformers`` only.
    vLLM serving (v6) is explicitly excluded per parsing_architecture_plan.md.

    Args:
        image_path:  Path to a PNG image of the page (rendered at 200 DPI).
        page_number: Zero-based page index for block ordering metadata.

    Returns:
        list[dict]: One block dict with the OCR'd markdown text.

    Side effects:
        Loads the DeepSeek-OCR-2 model weights on first call if
        ``ENABLE_DEEPSEEK_OCR2=true``.
    """
    if not settings.enable_deepseek_ocr2:
        logger.warning(
            "Page %d routed to DEEPSEEK_OCR2 but ENABLE_DEEPSEEK_OCR2=false. "
            "Skipping page — enable on production hardware with ≥8 GB VRAM.",
            page_number,
        )
        return []

    # Lazy import — only pulled in when the route is actually needed
    try:
        from transformers import AutoModel, AutoTokenizer
        import torch
    except ImportError as exc:
        logger.error("transformers/torch not installed: %s. Cannot run DeepSeek-OCR2.", exc)
        return []

    tokenizer = AutoTokenizer.from_pretrained(
        settings.deepseek_model_id, trust_remote_code=True
    )
    model = AutoModel.from_pretrained(
        settings.deepseek_model_id,
        trust_remote_code=True,
        _attn_implementation="flash_attention_2",
        use_safetensors=True,
    ).eval().cuda().to(torch.bfloat16)

    prompt = "<image>\n<|grounding|>Convert the document to markdown. "
    try:
        res = model.infer(
            tokenizer,
            prompt=prompt,
            image_file=image_path,
            output_path=None,
            base_size=1024,
            image_size=768,
            crop_mode=True,
        )
        text = str(res).strip()
    except Exception as exc:
        logger.error("DeepSeek-OCR2 inference failed on page %d: %s", page_number, exc)
        return []

    if not text:
        return []
    return [
        {
            "text": text,
            "page": page_number,
            "source_backend": "deepseek_ocr2",
            "block_type": "paragraph",
        }
    ]


# ---------------------------------------------------------------------------
# Assembly — blocks → DoclingDocument
# ---------------------------------------------------------------------------

def _blocks_to_docling(blocks: list[dict]) -> DoclingDocument:
    """Assemble a flat, ordered list of page blocks into a DoclingDocument.

    Blocks are sorted by page number so the resulting document preserves
    reading order across pages regardless of which backend parsed each page.

    Args:
        blocks: List of dicts with keys: text, page, source_backend, block_type.

    Returns:
        DoclingDocument: Unified document ready for HybridChunker.
    """
    from docling_core.types.doc import DocItemLabel

    doc = DoclingDocument(name="pdf_assembled")
    sorted_blocks = sorted(blocks, key=lambda b: b.get("page", 0))

    for block in sorted_blocks:
        text = block.get("text", "").strip()
        if not text:
            continue
        block_type = block.get("block_type", "paragraph")
        label = (
            DocItemLabel.SECTION_HEADER
            if block_type in ("section_header", "SECTION_HEADER", "DocItemLabel.SECTION_HEADER")
            else DocItemLabel.PARAGRAPH
        )
        doc.add_text(label=label, text=text)

    return doc


# ---------------------------------------------------------------------------
# PdfPageRouter — the v5 BaseParser implementation
# ---------------------------------------------------------------------------

class PdfPageRouter(BaseParser):
    """v5 PDF parser: routes each page to its cheapest adequate backend.

    Extends :class:`BaseParser`. Handles ``.pdf`` files only.
    Replaces ``PdfStubParser`` (v4) in :class:`parsers.router.ParserRouter`.

    Usage::

        router = ParserRouter()   # automatically registers PdfPageRouter (v5)
        doc = router.parse(pdf_bytes, "regulation.pdf")

    Attributes:
        SUPPORTED_EXTENSIONS: Frozenset containing only ``'.pdf'``.
    """

    SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({".pdf"})

    def can_handle(self, ext: str) -> bool:
        """Return True for ``.pdf`` extension only.

        Args:
            ext: Lowercase, dot-prefixed extension e.g. ``'.pdf'``.
        """
        return ext.lower() in self.SUPPORTED_EXTENSIONS

    def parse(self, file_bytes: bytes, filename: str, **kwargs) -> DoclingDocument:
        """Parse a PDF by triaging each page independently.

        Each page is classified with :func:`_triage_page` (no model loaded),
        then dispatched to the appropriate backend. Front-matter pages are
        logged and skipped. All parsed blocks are assembled into one
        :class:`DoclingDocument` ordered by page number.

        Args:
            file_bytes: Raw bytes of the PDF file.
            filename:   Original filename used for DocumentStream naming and logging.
            **kwargs:   Reserved — not currently used.

        Returns:
            DoclingDocument: Unified document ready for chunking.
        """
        try:
            pdf = fitz.open(stream=file_bytes, filetype="pdf")
        except Exception as exc:
            logger.error("Failed to open PDF %s: %s", filename, exc)
            # Return empty document rather than crashing the ingestion pipeline
            return DoclingDocument(name=filename)

        all_blocks: list[dict] = []

        for page in pdf:
            page_number = page.number
            try:
                route, is_front_matter = _triage_page(page)
            except Exception as exc:
                logger.warning(
                    "Triage failed for page %d of %s: %s. Defaulting to PYMUPDF4LLM.",
                    page_number, filename, exc,
                )
                route, is_front_matter = "PYMUPDF4LLM", False

            if is_front_matter:
                logger.info("Page %d of %s: front matter — skipping.", page_number, filename)
                continue

            logger.info("Page %d of %s → route=%s", page_number, filename, route)

            if route == "PYMUPDF4LLM":
                blocks = _parse_with_pymupdf4llm(page, page_number)

            elif route == "DOCLING":
                # Docling receives only the current page as a standalone PDF
                try:
                    single_page_doc = fitz.open()
                    single_page_doc.insert_pdf(
                        pdf, from_page=page_number, to_page=page_number
                    )
                    page_bytes = single_page_doc.write()
                    single_page_doc.close()
                except Exception as exc:
                    logger.warning(
                        "Could not extract page %d from %s for Docling: %s. Skipping.",
                        page_number, filename, exc,
                    )
                    continue
                blocks = _parse_with_docling(page_bytes, filename, page_number)

            else:  # DEEPSEEK_OCR2
                # Render page to PNG for OCR; temp file is cleaned up immediately
                tmp_path: str | None = None
                try:
                    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                        tmp_path = tmp.name
                    pix = page.get_pixmap(dpi=200)
                    pix.save(tmp_path)
                    blocks = _parse_with_deepseek(tmp_path, page_number)
                except Exception as exc:
                    logger.error(
                        "DeepSeek-OCR2 pipeline error on page %d of %s: %s",
                        page_number, filename, exc,
                    )
                    blocks = []
                finally:
                    if tmp_path:
                        Path(tmp_path).unlink(missing_ok=True)

            all_blocks.extend(blocks)

        pdf.close()
        return _blocks_to_docling(all_blocks)
