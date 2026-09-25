"""
schemas/compliance.py — Contracts for country-specific compliance analysis.

A compliance report compares the USER's rules against the MarketSphere
requirement store (approved ComplianceRule rows + SourceRegistry provenance)
for one selected country. Nothing is guessed: findings without an identified
requirement are UNDETERMINED, and missing context is requested explicitly.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

RuleVerdict = Literal[
    "COMPLIANT",
    "PARTIALLY_COMPLIANT",
    "NON_COMPLIANT",
    "MISSING_REQUIREMENT",
    "CONTRADICTORY",
    "NOT_APPLICABLE",
    "UNDETERMINED",
]

Severity = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]


class AnalysisContext(BaseModel):
    product: Optional[str] = None
    operation: Optional[str] = Field(
        None, description="'import' | 'export' | 'domestic' (when known)."
    )
    ncm: Optional[str] = Field(None, description="NCM / HS product classification.")
    destination: Optional[str] = None
    origin: Optional[str] = None
    industry: Optional[str] = None


class SourceEvidence(BaseModel):
    authority: str = ""
    title: str = ""
    url: Optional[str] = None
    reviewed_at: Optional[str] = None
    evidence_tag: Optional[str] = None
    verified: bool = False


class ComplianceRuleResult(BaseModel):
    id: int
    user_rule: str
    status: RuleVerdict
    severity: Optional[Severity] = None
    country_requirement: Optional[str] = None
    explanation: str = ""
    required_action: Optional[str] = None
    missing_information: list[str] = Field(default_factory=list)
    sources: list[SourceEvidence] = Field(default_factory=list)


class ViolationItem(BaseModel):
    rule_id: int
    severity: Severity
    user_rule: str = ""
    country_requirement: str = ""
    explanation: str = ""
    required_action: str = ""
    sources: list[SourceEvidence] = Field(default_factory=list)


class GapItem(BaseModel):
    topic: str = ""
    requirement: str = ""
    why_it_matters: str = ""
    sources: list[SourceEvidence] = Field(default_factory=list)


class ConflictItem(BaseModel):
    kind: Literal["regulatory", "internal"] = "regulatory"
    rules: list[int] = Field(default_factory=list)
    explanation: str = ""
    sources: list[SourceEvidence] = Field(default_factory=list)


class CompatibilityScore(BaseModel):
    score: int = 0
    label: str = ""
    methodology: str = ""


class ComplianceSummary(BaseModel):
    total_rules: int = 0
    compliant: int = 0
    partially_compliant: int = 0
    non_compliant: int = 0
    undetermined: int = 0


class CountryInfo(BaseModel):
    country: str
    regulators: list[str] = Field(default_factory=list)
    approved_requirements: int = 0
    sources: int = 0


class ComplianceAnalyzeRequest(BaseModel):
    country: str = Field(..., min_length=1)
    rules: list[str] = Field(..., description="User's rules in display order.")
    context: AnalysisContext = Field(default_factory=AnalysisContext)


class ComplianceReport(BaseModel):
    country: str
    analysis_date: str = ""
    context: AnalysisContext = Field(default_factory=AnalysisContext)
    compatibility: CompatibilityScore = Field(default_factory=CompatibilityScore)
    summary: ComplianceSummary = Field(default_factory=ComplianceSummary)
    rules: list[ComplianceRuleResult] = Field(default_factory=list)
    violations: list[ViolationItem] = Field(default_factory=list)
    gaps: list[GapItem] = Field(default_factory=list)
    conflicts: list[ConflictItem] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    required_actions: list[str] = Field(default_factory=list)
    sources: list[SourceEvidence] = Field(default_factory=list)


class ComplianceChatRequest(BaseModel):
    country: str = Field(..., min_length=1)
    rules: list[str] = Field(default_factory=list)
    context: AnalysisContext = Field(default_factory=AnalysisContext)
    report: Optional[ComplianceReport] = None
    question: str = Field(..., min_length=1)


class ComplianceChatResponse(BaseModel):
    content: str
    action: Optional[Literal["reanalyze"]] = None
