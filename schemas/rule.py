"""
schemas/rule.py — Pydantic schema for candidate regulatory rules.

CandidateRule is the central data contract between:
  - The LLM extractor (services/extractor.py) — produces CandidateRule instances.
  - The compliance rule store (models/rule.py) — persists them as JSON.
  - The evaluator (services/evaluator.py) — reads approved rules.

Every candidate must include:
  - A verbatim supporting_quote from the source text.
  - A source_id linking it to a SourceRegistry record.
  - An evidence_tag assigned by the LLM judge.
  - review_status="draft" on creation; changed to "approved" or "rejected" by a reviewer.

The TOPSIS market ranker feed fields (leverage_cap_retail, required_capital_usd,
presence_friction_summary) are denormalized onto the ORM model for fast queries.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class CandidateRule(BaseModel):
    """A single extracted regulatory rule — candidate for human review.

    All fields with ``...`` (no default) are mandatory.
    Fields with ``None`` default may be genuinely unknown — represent them as
    null, never fabricate a value.
    """

    # -----------------------------------------------------------------------
    # Jurisdiction scope
    # -----------------------------------------------------------------------
    jurisdiction: str = Field(
        ..., description="Country or market e.g. 'UAE', 'Brazil', 'Indonesia'."
    )
    regulator: str = Field(
        ..., description="Issuing authority e.g. 'VARA', 'BCB', 'OJK'."
    )
    topic: str = Field(
        ..., description="Regulatory topic e.g. 'leverage', 'AML', 'KYC', 'capital'."
    )
    obligation_or_restriction: str = Field(
        ..., description="Human-readable summary of the rule or obligation."
    )
    applicability_conditions: Optional[str] = Field(
        None, description="Conditions under which the rule applies (or null if universal)."
    )
    exceptions: Optional[str] = Field(
        None, description="Stated exceptions or exemptions to the rule."
    )

    # -----------------------------------------------------------------------
    # TOPSIS market ranker feed fields (denormalized for fast query access)
    # -----------------------------------------------------------------------
    leverage_cap_retail: Optional[str] = Field(
        None,
        description="Statutory retail leverage cap e.g. '1:5', '1:300'. TOPSIS C4.",
    )
    required_capital_usd: Optional[float] = Field(
        None,
        description="Minimum statutory paid-up capital expressed in USD. TOPSIS C6.",
    )
    presence_friction_summary: Optional[str] = Field(
        None,
        description="Summary of physical presence, resident director, or data-localisation "
                    "mandates. TOPSIS C7.",
    )

    # -----------------------------------------------------------------------
    # Effective dates
    # -----------------------------------------------------------------------
    effective_from: Optional[str] = Field(None, description="ISO date string or null.")
    effective_to:   Optional[str] = Field(None, description="ISO date string or null.")

    # -----------------------------------------------------------------------
    # Traceability (mandatory — every rule must cite its source)
    # -----------------------------------------------------------------------
    supporting_quote: str = Field(
        ...,
        description=(
            "Verbatim passage from the source text. "
            "Must be an exact substring of the ingested source chunk. "
            "Programmatically validated — hallucinated quotes are rejected."
        ),
    )
    source_id: str = Field(
        ..., description="FK to SourceRegistry.source_id."
    )
    source_chunk_id: Optional[str] = Field(
        None, description="Chunk ID from the chunker output (for precise re-anchoring)."
    )
    page_number: Optional[int] = Field(
        None, description="Zero-based page index where the rule was found."
    )
    section_heading: Optional[str] = Field(
        None, description="Nearest section heading (for human context in the review UI)."
    )

    # -----------------------------------------------------------------------
    # Extraction provenance
    # -----------------------------------------------------------------------
    extraction_model: str = Field(
        ..., description="LLM used for extraction e.g. 'llama3.2:3b', 'gemini-2.0-flash'."
    )
    prompt_version: str = Field(
        ..., description="Prompt version string e.g. 'v1.0' for reproducibility."
    )
    evidence_tag: Literal[
        "Verified Fact",
        "Analyst Estimate",
        "Unresolved Policy / Draft",
    ] = Field(
        ...,
        description=(
            "Assigned by the LLM judge. Controls Monte Carlo variance in the "
            "TOPSIS SMAA engine: 'Verified Fact' → tight Gaussian; "
            "'Analyst Estimate' → wider; 'Unresolved Policy / Draft' → bimodal."
        ),
    )

    # -----------------------------------------------------------------------
    # Workflow state
    # -----------------------------------------------------------------------
    validation_status: str = Field(
        default="pending",
        description="'pending' | 'pass' | 'fail' — set by the schema + evidence validator.",
    )
    review_status: str = Field(
        default="draft",
        description="'draft' | 'approved' | 'rejected' — set by the human reviewer.",
    )


class RuleReviewRequest(BaseModel):
    action: Literal["approve", "reject", "edit"] = Field(
        ..., description="'approve', 'reject', or 'edit'."
    )
    reviewer_id: str = Field(..., description="ID or email of human compliance officer.")
    edited_rule_data: Optional[dict] = Field(
        None, description="Updated rule JSON dict if action is 'edit'."
    )


class RuleResponse(BaseModel):
    rule_id: str
    rule_version: int
    source_id: str
    jurisdiction: str
    regulator: Optional[str]
    topic: Optional[str]
    rule_data: Optional[dict]
    evidence_tag: Optional[str]
    leverage_cap: Optional[str]
    required_capital: Optional[float]
    review_status: str
    reviewer_id: Optional[str]
    reviewed_at: Optional[str]
    created_at: Optional[str]


class RuleListResponse(BaseModel):
    total: int
    rules: list[RuleResponse]


class EvaluateProfileRequest(BaseModel):
    jurisdiction: str = Field(..., description="Target market jurisdiction.")
    product_type: Optional[str] = Field(
        None, description="Offered product type e.g. 'leveraged_derivatives'."
    )
    capital_available_usd: Optional[float] = Field(
        None, description="Available paid-up capital in USD (null -> UNKNOWN)."
    )
    leverage_offered: Optional[str] = Field(
        None, description="Offered retail leverage ratio e.g. '1:20'."
    )
    has_local_presence: Optional[bool] = Field(
        None, description="Whether a local presence is established."
    )


class EvaluationResultItem(BaseModel):
    rule_id: str
    rule_version: int = 1
    topic: str = "general"
    status: Literal["PASS", "CONFLICT", "UNKNOWN"]
    reason: str = ""
    supporting_quote: str = ""


class EvaluateProfileResponse(BaseModel):
    jurisdiction: str
    total: int
    results: list[EvaluationResultItem]

