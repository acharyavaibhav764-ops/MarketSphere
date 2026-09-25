"""
schemas/analysis.py — Pydantic contracts for the AI Rule Analyzer feature.

Structured JSON contract between:
  - The analyzer engine (services/rule_analyzer.py) — produces AnalysisResponse.
  - The optional LLM path (services/analyzer_prompts.py) — must conform to it.
  - The frontend (frontend/analyzer.js) — renders it as a ChatGPT-style reply.

Every analyzed rule keeps its number and original wording; no rule is dropped.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

RuleStatus = Literal[
    "VALID",
    "NEEDS_CLARIFICATION",
    "INCORRECT",
    "CONFLICTING",
    "INCOMPLETE",
    "UNDETERMINED",
]


class ExtractedRule(BaseModel):
    number: int
    text: str


class RuleAnalysisItem(BaseModel):
    number: int
    original: str
    status: RuleStatus
    explanation: str
    reasoning: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    suggested_correction: Optional[str] = None


class CrossRuleConflict(BaseModel):
    kind: Literal["contradiction", "duplicate", "overlap"] = "contradiction"
    rules: list[int]
    explanation: str


class AnalysisSummary(BaseModel):
    total: int = 0
    valid: int = 0
    needs_clarification: int = 0
    incorrect: int = 0
    conflicting: int = 0
    incomplete: int = 0
    undetermined: int = 0


class CriticalIssue(BaseModel):
    text: str


class AnalyzeRequest(BaseModel):
    rules: list[str] = Field(..., description="Rule texts in display order.")


class AnalysisResponse(BaseModel):
    total: int
    rules: list[RuleAnalysisItem]
    cross_rule_conflicts: list[CrossRuleConflict] = Field(default_factory=list)
    summary: AnalysisSummary
    critical_issues: list[CriticalIssue] = Field(default_factory=list)
    recommended_corrections: list[str] = Field(default_factory=list)


class ExtractResponse(BaseModel):
    filename: str
    size_bytes: int
    total: int
    truncated: bool = False
    text_preview: str = ""
    rules: list[ExtractedRule]


class ChatRequest(BaseModel):
    rules: list[str] = Field(default_factory=list)
    analysis: Optional[AnalysisResponse] = None
    question: str = Field(..., min_length=1)


class ChatResponse(BaseModel):
    content: str
    action: Optional[Literal["reanalyze"]] = None
