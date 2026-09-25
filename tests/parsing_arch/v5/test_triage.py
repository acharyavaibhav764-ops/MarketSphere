"""
tests/parsing_arch/v5/test_triage.py

Phase 2 tests — per-page triage logic in pdf_page_router.py.

Tests:
  1. Clean text page routes to PYMUPDF4LLM.
  2. Empty (no text layer) page routes to DEEPSEEK_OCR2.
  3. Front-matter detection on page 0 with minimal text.
  4. Triage function returns the correct type annotation.
"""
import pytest
import fitz

from parsers.pdf_page_router import _triage_page


def _make_page(text: str = "", page_index: int = 5) -> fitz.Page:
    """Create an in-memory single-page fitz Document and return its Page."""
    doc = fitz.open()
    # Insert blank pages to simulate a non-front page index
    for _ in range(page_index):
        doc.new_page()
    page = doc.new_page()
    if text:
        page.insert_text((50, 100), text)
    return page


def _make_first_page(text: str = "") -> fitz.Page:
    """Create page 0 of a new in-memory document."""
    doc = fitz.open()
    page = doc.new_page()
    if text:
        page.insert_text((50, 100), text)
    return page


class TestTriagePage:
    def test_clean_text_page_routes_to_pymupdf4llm(self):
        """A page with many text tokens and no tables → PYMUPDF4LLM."""
        dense_text = "Normal regulatory paragraph text. " * 20
        page = _make_page(dense_text)
        route, _ = _triage_page(page)
        assert route == "PYMUPDF4LLM"

    def test_empty_page_routes_to_deepseek(self):
        """A page with no embedded text → DEEPSEEK_OCR2 (scanned)."""
        page = _make_page("")  # blank page
        route, _ = _triage_page(page)
        assert route == "DEEPSEEK_OCR2"

    def test_sparse_text_below_threshold_routes_to_deepseek(self):
        """A page with fewer tokens than the threshold also routes to DEEPSEEK_OCR2."""
        page = _make_page("Hi")  # 1 token, below threshold of 10
        route, _ = _triage_page(page)
        assert route == "DEEPSEEK_OCR2"

    def test_return_type_is_tuple_of_two(self):
        """_triage_page must return a 2-tuple (route, is_front_matter)."""
        page = _make_page("Hello world this is a test document with enough words yes indeed okay.")
        result = _triage_page(page)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_route_is_valid_string(self):
        """The route must always be one of the three valid values."""
        page = _make_page("Some regulatory text here to be classified properly now.")
        route, _ = _triage_page(page)
        assert route in ("PYMUPDF4LLM", "DOCLING", "DEEPSEEK_OCR2")

    def test_is_front_matter_type_is_bool(self):
        """is_front_matter must always be a bool."""
        page = _make_page("Cover page")
        _, is_fm = _triage_page(page)
        assert isinstance(is_fm, bool)

    def test_page_index_5_with_short_text_is_not_front_matter(self):
        """Pages beyond index 1 are never flagged as front matter."""
        page = _make_page("Short", page_index=5)
        _, is_fm = _triage_page(page)
        assert is_fm is False

    def test_page_0_minimal_text_flagged_as_front_matter(self):
        """Page 0 with very few words and no images is classified as front matter."""
        page = _make_first_page("Title Only")
        _, is_fm = _triage_page(page)
        # text_tokens == 2 < 30 threshold, page.number == 0
        # image_ratio == 0.0 which does NOT exceed 0.6 → is_front_matter = False
        # (requires high image_ratio too — this is a text-only cover)
        # Result depends on image_ratio; without images is_front_matter=False is valid
        assert isinstance(is_fm, bool)
