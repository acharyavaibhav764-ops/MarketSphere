"""
tests/compliance/test_rule_schema.py

Phase 3 tests — CandidateRule Pydantic schema validation.

Tests:
  1. Valid CandidateRule instantiates cleanly.
  2. Missing required fields (supporting_quote, evidence_tag, source_id, etc.) raise ValidationError.
  3. Invalid evidence_tag literals are rejected.
  4. Default values for validation_status ('pending') and review_status ('draft') are preserved.
  5. Denormalized TOPSIS fields (leverage_cap_retail, required_capital_usd, presence_friction_summary)
     accept valid types and optional None.
"""
import pytest
from pydantic import ValidationError

from schemas.rule import CandidateRule


def test_valid_candidate_rule():
    rule = CandidateRule(
        jurisdiction="UAE",
        regulator="VARA",
        topic="capital",
        obligation_or_restriction="Licensees must hold USD 500,000 capital",
        supporting_quote="Licensees must hold USD 500,000 capital",
        source_id="src-12345",
        extraction_model="llama3.2:3b",
        prompt_version="v1.0",
        evidence_tag="Verified Fact",
        leverage_cap_retail="1:5",
        required_capital_usd=500000.0,
        presence_friction_summary="Local office required",
    )
    assert rule.jurisdiction == "UAE"
    assert rule.regulator == "VARA"
    assert rule.topic == "capital"
    assert rule.validation_status == "pending"
    assert rule.review_status == "draft"
    assert rule.required_capital_usd == 500000.0
    assert rule.evidence_tag == "Verified Fact"


def test_missing_mandatory_fields_raises_validation_error():
    # Missing supporting_quote, source_id, extraction_model, prompt_version, evidence_tag, etc.
    with pytest.raises(ValidationError):
        CandidateRule(
            jurisdiction="UAE",
            regulator="VARA",
            topic="capital",
            obligation_or_restriction="Some restriction",
        )


def test_invalid_evidence_tag_raises_error():
    with pytest.raises(ValidationError):
        CandidateRule(
            jurisdiction="UAE",
            regulator="VARA",
            topic="capital",
            obligation_or_restriction="Capital rule",
            supporting_quote="Capital rule quote",
            source_id="src-001",
            extraction_model="llama3.2:3b",
            prompt_version="v1.0",
            evidence_tag="NonExistentTag",  # Invalid
        )


def test_allowed_evidence_tags():
    allowed_tags = ["Verified Fact", "Analyst Estimate", "Unresolved Policy / Draft"]
    for tag in allowed_tags:
        rule = CandidateRule(
            jurisdiction="Brazil",
            regulator="BCB",
            topic="licensing",
            obligation_or_restriction="Must obtain VASP license",
            supporting_quote="Must obtain VASP license",
            source_id="src-br-1",
            extraction_model="llama3.2:3b",
            prompt_version="v1.0",
            evidence_tag=tag,
        )
        assert rule.evidence_tag == tag


def test_topsis_fields_optional_none():
    rule = CandidateRule(
        jurisdiction="Indonesia",
        regulator="OJK",
        topic="reporting",
        obligation_or_restriction="Submit monthly report",
        supporting_quote="Submit monthly report",
        source_id="src-id-1",
        extraction_model="llama3.2:3b",
        prompt_version="v1.0",
        evidence_tag="Verified Fact",
    )
    assert rule.leverage_cap_retail is None
    assert rule.required_capital_usd is None
    assert rule.presence_friction_summary is None
