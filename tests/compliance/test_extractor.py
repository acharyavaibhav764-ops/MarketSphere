"""
tests/compliance/test_extractor.py

Phase 3 tests — AI-Assisted Rule Extractor and LLM Judge pipeline.

Tests:
  1. Verbatim quote in source text is accepted and validated.
  2. Hallucinated quote (not an exact substring) is unconditionally rejected.
  3. Programmatic verbatim check raises ValueError when raise_on_hallucination=True.
  4. verify_verbatim_quote raises ValueError on fabricated quotes.
  5. LLM client with .chat() interface is supported.
"""
import json
import pytest

from services.extractor import (
    extract_rules,
    verify_verbatim_quote,
)


SAMPLE_TEXT = (
    "Pursuant to Article 4, licensees shall maintain a minimum paid-up capital of USD 500,000. "
    "Retail leverage is strictly capped at 1:5 for all cryptocurrency derivatives."
)


class MockChatClient:
    """Mock LLM client exposing .chat() interface."""
    def __init__(self, hallucinate_quote: bool = False):
        self.hallucinate_quote = hallucinate_quote
        self.model = "mock-chat-model"
        self.call_count = 0

    def chat(self, messages: list[dict]) -> dict:
        self.call_count += 1
        user_msg = next((m["content"] for m in messages if m["role"] == "user"), "")
        
        # Stage 1: Extraction call
        if "Extract rules as a JSON array" in user_msg:
            quote = (
                "FABRICATED HALLUCINATED QUOTE"
                if self.hallucinate_quote
                else "minimum paid-up capital of USD 500,000"
            )
            return {
                "message": {
                    "content": json.dumps([
                        {
                            "jurisdiction": "UAE",
                            "regulator": "VARA",
                            "topic": "capital",
                            "obligation_or_restriction": "Maintain minimum capital of USD 500k",
                            "leverage_cap_retail": "1:5",
                            "required_capital_usd": 500000.0,
                            "supporting_quote": quote,
                        }
                    ])
                }
            }

        # Stage 2: Judge call
        if "EXTRACTED:" in user_msg:
            extracted_json = user_msg.split("EXTRACTED:\n")[1]
            data = json.loads(extracted_json)
            for r in data:
                r["evidence_tag"] = "Verified Fact"
            return {"message": {"content": json.dumps(data)}}

        return {"message": {"content": "[]"}}


def test_verbatim_quote_accepted_via_chat_client():
    client = MockChatClient(hallucinate_quote=False)
    rules = extract_rules(
        chunk_text=SAMPLE_TEXT,
        source_id="src-uae-vara",
        chunk_id="chk-001",
        page_number=1,
        llm_client=client,
    )
    assert len(rules) == 1
    assert rules[0].evidence_tag == "Verified Fact"
    assert "500,000" in rules[0].supporting_quote
    assert client.call_count == 2  # Proves separate Stage 1 and Stage 2 calls!


def test_fabricated_quote_raises_value_error():
    client = MockChatClient(hallucinate_quote=True)
    with pytest.raises(ValueError, match="Hallucination detected"):
        extract_rules(
            chunk_text=SAMPLE_TEXT,
            source_id="src-uae-vara",
            chunk_id="chk-002",
            page_number=1,
            llm_client=client,
            raise_on_hallucination=True,
        )


def test_direct_verify_verbatim_quote_raises():
    with pytest.raises(ValueError, match="Hallucination detected"):
        verify_verbatim_quote(
            supporting_quote="THIS QUOTE DOES NOT EXIST IN DOCUMENT",
            chunk_text=SAMPLE_TEXT,
        )


def test_direct_verify_verbatim_quote_passes():
    # Should not raise
    verify_verbatim_quote(
        supporting_quote="licensees shall maintain a minimum paid-up capital of USD 500,000",
        chunk_text=SAMPLE_TEXT,
    )
