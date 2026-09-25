"""
tests/parsing_arch/v5/test_pdf_page_router.py

Phase 2 tests — PdfPageRouter end-to-end behaviour.

Tests:
  1. Returns a DoclingDocument for a simple text-only PDF.
  2. Correctly handles .pdf extension (can_handle).
  3. Rejects non-PDF extensions.
  4. Returns a DoclingDocument (not None, not an error) for an empty PDF.
  5. Router registration: ParserRouter now uses PdfPageRouter, not PdfStubParser.
  6. Regression: ParserRouter still handles .txt, .docx, etc.
"""
import io
import pytest
import fitz

from docling_core.types.doc import DoclingDocument
from parsers.pdf_page_router import PdfPageRouter
from parsers.router import ParserRouter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def simple_text_pdf() -> bytes:
    """In-memory single-page PDF with dense regulatory text."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (50, 100),
        "Section 1. All licensees shall maintain a minimum paid-up capital of "
        "USD 500,000. Retail leverage is capped at 1:5 for leveraged derivatives. " * 8,
    )
    return doc.write()


@pytest.fixture
def empty_pdf() -> bytes:
    """In-memory PDF with one completely blank page."""
    doc = fitz.open()
    doc.new_page()
    return doc.write()


@pytest.fixture
def multipage_text_pdf() -> bytes:
    """In-memory 3-page PDF each with substantial text."""
    doc = fitz.open()
    for i in range(3):
        page = doc.new_page()
        page.insert_text(
            (50, 100),
            f"Chapter {i + 1}. Regulatory requirements for licensed entities. " * 10,
        )
    return doc.write()


# ---------------------------------------------------------------------------
# PdfPageRouter unit tests
# ---------------------------------------------------------------------------

class TestPdfPageRouterCanHandle:
    def test_handles_pdf(self):
        assert PdfPageRouter().can_handle(".pdf") is True

    def test_case_insensitive(self):
        assert PdfPageRouter().can_handle(".PDF") is True

    def test_rejects_docx(self):
        assert PdfPageRouter().can_handle(".docx") is False

    def test_rejects_txt(self):
        assert PdfPageRouter().can_handle(".txt") is False

    def test_rejects_html(self):
        assert PdfPageRouter().can_handle(".html") is False


class TestPdfPageRouterParse:
    def test_returns_docling_document_for_text_pdf(self, simple_text_pdf):
        """PdfPageRouter must return a DoclingDocument for a valid text PDF."""
        router = PdfPageRouter()
        result = router.parse(simple_text_pdf, "regulation.pdf")
        assert isinstance(result, DoclingDocument)

    def test_returns_docling_document_for_empty_pdf(self, empty_pdf):
        """An empty/blank PDF must not raise — returns an empty DoclingDocument."""
        router = PdfPageRouter()
        result = router.parse(empty_pdf, "blank.pdf")
        assert isinstance(result, DoclingDocument)

    def test_multipage_pdf_produces_document(self, multipage_text_pdf):
        """A multi-page text PDF must return a populated DoclingDocument."""
        router = PdfPageRouter()
        result = router.parse(multipage_text_pdf, "multipage.pdf")
        assert isinstance(result, DoclingDocument)

    def test_invalid_bytes_returns_empty_document_not_exception(self):
        """Corrupt or non-PDF bytes must return an empty document gracefully."""
        router = PdfPageRouter()
        result = router.parse(b"not a valid pdf", "corrupt.pdf")
        assert isinstance(result, DoclingDocument)


# ---------------------------------------------------------------------------
# ParserRouter integration tests
# ---------------------------------------------------------------------------

class TestParserRouterV5Integration:
    def test_parser_router_uses_pdf_page_router_for_pdf(self, simple_text_pdf):
        """ParserRouter must dispatch .pdf to PdfPageRouter (v5), not PdfStubParser."""
        router = ParserRouter()
        parser = router.get_parser("regulation.pdf")
        assert isinstance(parser, PdfPageRouter), (
            f"Expected PdfPageRouter, got {type(parser).__name__}"
        )

    def test_parser_router_pdf_parse_returns_docling_document(self, simple_text_pdf):
        """ParserRouter.parse() for PDF must return a DoclingDocument."""
        router = ParserRouter()
        result = router.parse(simple_text_pdf, "test.pdf")
        assert isinstance(result, DoclingDocument)

    def test_parser_router_still_handles_txt(self):
        """Regression: .txt files must still be handled by TextParser."""
        from parsers.text import TextParser
        router = ParserRouter()
        parser = router.get_parser("document.txt")
        assert isinstance(parser, TextParser)

    def test_parser_router_still_handles_docx(self):
        """Regression: .docx files must still be handled by DoclingParser."""
        from parsers.docling_parser import DoclingParser
        router = ParserRouter()
        parser = router.get_parser("document.docx")
        assert isinstance(parser, DoclingParser)
