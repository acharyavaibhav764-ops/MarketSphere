"""
tests/compliance/test_extractor.py

Phase 3 tests — AI-Assisted Rule Extractor and LLM Judge pipeline.

Tests:
  1. Verbatim quote in source text is accepted and validated.
  2. Hallucinated quote (not an exact substring) is unconditionally rejected.
  3. Non-JSON generator output is handled gracefully without crashing.
  4. Judge evidence_tag assignment and passthrough.
  5. Correct mapping of source_id, chunk_id, and page_number.
"""
import json
import pytest

from services.extractor import extract_candidate_rules


SAMPLE_TEXT = (
    "Pursuant to Article 4, licensees shall maintain a minimum paid-up capital of USD 500,000. "
    "Retail leverage is strictly capped at 1:5 for all cryptocurrency derivatives."
)


class MockGenerator:
    """Simulates LLM response for extraction and judging."""
    def __init__(self, hallucinate_quote: bool = False, bad_json: bool = False):
        self.hallucinate_quote = hallucinate_quote
        self.bad_json = bad_json

    def generate(self, prompt: str, system: str = "") -> str:
        if self.bad_json:
            return "I am an AI and here are some rules: not a valid json"

        if "Extract rules as JSON array" in prompt or "Extract rules" in prompt:
            quote = (
                "HALLUCINATED QUOTE THAT DOES NOT EXIST IN DOCUMENT"
                if self.hallucinate_quote
                else "minimum paid-up capital of USD 500,000"
            )
            return json.dumps([
                {
                    "jurisdiction": "UAE",
                    "regulator": "VARA",
                    "topic": "capital",
                    "obligation_or_restriction": "Maintain minimum capital of USD 500k",
                    "leverage_cap_retail": "1:5",
                    "required_capital_usd": 500000.0,
                    "supporting_quote": quote,
                    "extraction_model": "test-llm",
                    "prompt_version": "v1.0",
                }
            ])

        # Judge stage: prompt has EXTRACTED:
        if "EXTRACTED:" in prompt:
            extracted_json = prompt.split("EXTRACTED:\n")[1]
            data = json.loads(extracted_json)
            for r in data:
                r["evidence_tag"] = "Verified Fact"
            return json.dumps(data)

        return "[]"


def test_verbatim_quote_is_accepted():
    generator = MockGenerator(hallucinate_quote=False)
    rules = extract_candidate_rules(
        chunk_text=SAMPLE_TEXT,
        source_id="src-uae-vara",
        chunk_id="chk-001",
        page_number=1,
        generator=generator,
    )
    assert len(rules) == 1
    rule = rules[0]
    assert rule.jurisdiction == "UAE"
    assert rule.regulator == "VARA"
    assert rule.topic == "capital"
    assert rule.source_id == "src-uae-vara"
    assert rule.source_chunk_id == "chk-001"
    assert rule.page_number == 1
    assert rule.evidence_tag == "Verified Fact"
    assert "500,000" in rule.supporting_quote
    assert rule.supporting_quote in SAMPLE_TEXT


def test_hallucinated_quote_is_rejected():
    generator = MockGenerator(hallucinate_quote=True)
    rules = extract_candidate_rules(
        chunk_text=SAMPLE_TEXT,
        source_id="src-uae-vara",
        chunk_id="chk-002",
        page_number=2,
        generator=generator,
    )
    assert len(rules) == 0  # Rejection by deterministic check


def test_bad_json_returns_empty_list():
    generator = MockGenerator(bad_json=True)
    rules = extract_candidate_rules(
        chunk_text=SAMPLE_TEXT,
        source_id="src-uae-vara",
        chunk_id="chk-003",
        page_number=1,
        generator=generator,
    )
    assert rules == []
