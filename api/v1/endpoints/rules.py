"""
api/v1/endpoints/rules.py — Regulatory rule management and human review API.

Provides:
  GET  /api/v1/rules                 — List regulatory rules filtered by review_status and jurisdiction.
  POST /api/v1/rules/evaluate        — Deterministic evaluation of a broker profile.
  GET  /api/v1/rules/{rule_id}       — Retrieve a single rule with complete provenance and evidence_tag.
  POST /api/v1/rules                 — Ingest new draft candidate rules from extraction pipeline.
  POST /api/v1/rules/{rule_id}/review — Human reviewer action: approve, reject, or edit with version increment.
"""
from datetime import datetime
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from models.rule import ComplianceRule
from schemas.rule import (
    CandidateRule,
    EvaluateProfileRequest,
    EvaluateProfileResponse,
    EvaluationResultItem,
    RuleListResponse,
    RuleResponse,
    RuleReviewRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rules", tags=["Regulatory Rules"])


def _to_rule_response(rule: ComplianceRule) -> RuleResponse:
    return RuleResponse(
        rule_id=rule.rule_id,
        rule_version=rule.rule_version,
        source_id=rule.source_id,
        jurisdiction=rule.jurisdiction,
        regulator=rule.regulator,
        topic=rule.topic,
        rule_data=rule.rule_data,
        evidence_tag=rule.evidence_tag,
        leverage_cap=rule.leverage_cap,
        required_capital=rule.required_capital,
        review_status=rule.review_status,
        reviewer_id=rule.reviewer_id,
        reviewed_at=rule.reviewed_at.isoformat() if rule.reviewed_at else None,
        created_at=rule.created_at.isoformat() if rule.created_at else None,
    )


@router.post(
    "/evaluate",
    response_model=EvaluateProfileResponse,
    summary="Deterministically evaluate a broker profile",
    description=(
        "Evaluates a broker/product profile against approved regulatory rules "
        "for the given jurisdiction. No LLM in the hot path; missing facts "
        "evaluate strictly to UNKNOWN."
    ),
)
async def evaluate_broker_profile(
    profile: EvaluateProfileRequest,
    db: AsyncSession = Depends(get_db),
) -> EvaluateProfileResponse:
    from services.evaluator import evaluate_profile

    try:
        result = await db.execute(
            select(ComplianceRule).where(
                ComplianceRule.jurisdiction == profile.jurisdiction,
                ComplianceRule.review_status == "approved",
            )
        )
        approved_rules = list(result.scalars().all())
    except Exception as exc:
        logger.exception("Rule evaluation failed while loading approved rules")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Rule store unavailable: {exc}",
        )

    profile_dict = {
        "jurisdiction": profile.jurisdiction,
        "product_type": profile.product_type,
        "capital_available_usd": profile.capital_available_usd,
        "leverage_offered": profile.leverage_offered,
        "has_local_presence": profile.has_local_presence,
    }
    raw_results = evaluate_profile(profile_dict, approved_rules)
    return EvaluateProfileResponse(
        jurisdiction=profile.jurisdiction,
        total=len(raw_results),
        results=[EvaluationResultItem(**r) for r in raw_results],
    )


@router.get(
    "",
    response_model=RuleListResponse,
    summary="List regulatory rules",
    description="Retrieve rules filtered by review_status ('draft', 'approved', 'rejected') and jurisdiction.",
)
async def list_rules(
    status: Optional[str] = Query(None, description="Filter by review_status (e.g. 'draft', 'approved')"),
    jurisdiction: Optional[str] = Query(None, description="Filter by jurisdiction (e.g. 'UAE')"),
    db: AsyncSession = Depends(get_db),
) -> RuleListResponse:
    query = select(ComplianceRule)
    if status:
        query = query.where(ComplianceRule.review_status == status)
    if jurisdiction:
        query = query.where(ComplianceRule.jurisdiction == jurisdiction)

    result = await db.execute(query)
    rules = result.scalars().all()
    return RuleListResponse(
        total=len(rules),
        rules=[_to_rule_response(r) for r in rules],
    )


@router.get(
    "/{rule_id}",
    response_model=RuleResponse,
    summary="Get a single rule",
)
async def get_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
) -> RuleResponse:
    result = await db.execute(select(ComplianceRule).where(ComplianceRule.rule_id == rule_id))
    rule = result.scalars().first()
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule with id '{rule_id}' not found.",
        )
    return _to_rule_response(rule)


@router.post(
    "",
    response_model=RuleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a draft rule candidate",
)
async def create_rule(
    candidate: CandidateRule,
    db: AsyncSession = Depends(get_db),
) -> RuleResponse:
    rule_record = ComplianceRule(
        source_id=candidate.source_id,
        jurisdiction=candidate.jurisdiction,
        regulator=candidate.regulator,
        topic=candidate.topic,
        rule_data=candidate.model_dump(),
        evidence_tag=candidate.evidence_tag,
        leverage_cap=candidate.leverage_cap_retail,
        required_capital=candidate.required_capital_usd,
        review_status="draft",
    )
    db.add(rule_record)
    await db.commit()
    await db.refresh(rule_record)
    return _to_rule_response(rule_record)


@router.post(
    "/{rule_id}/review",
    response_model=RuleResponse,
    summary="Review a regulatory rule (approve, reject, edit)",
    description=(
        "Enforces the human-in-the-loop review workflow:\n"
        "- 'approve': Marks the rule approved for use by deterministic evaluator.\n"
        "- 'reject': Marks the rule rejected with reviewer attribution.\n"
        "- 'edit': Updates rule content, increments rule_version, and marks approved."
    ),
)
async def review_rule(
    rule_id: str,
    review_req: RuleReviewRequest,
    db: AsyncSession = Depends(get_db),
) -> RuleResponse:
    result = await db.execute(select(ComplianceRule).where(ComplianceRule.rule_id == rule_id))
    rule = result.scalars().first()
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule with id '{rule_id}' not found.",
        )

    if not review_req.reviewer_id or not review_req.reviewer_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="reviewer_id must be a non-empty string representing the human reviewer signature.",
        )

    now = datetime.utcnow()
    rule.reviewer_id = review_req.reviewer_id.strip()
    rule.reviewed_at = now

    if review_req.action == "approve":
        rule.review_status = "approved"
    elif review_req.action == "reject":
        rule.review_status = "rejected"
    elif review_req.action == "edit":
        if not review_req.edited_rule_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="edited_rule_data must be provided when action is 'edit'.",
            )
        rule.rule_version += 1
        rule.rule_data = review_req.edited_rule_data
        rule.review_status = "approved"

        # Update denormalized fields if provided in edited data
        if "leverage_cap_retail" in review_req.edited_rule_data:
            rule.leverage_cap = review_req.edited_rule_data["leverage_cap_retail"]
        if "required_capital_usd" in review_req.edited_rule_data:
            rule.required_capital = review_req.edited_rule_data["required_capital_usd"]
        if "topic" in review_req.edited_rule_data:
            rule.topic = review_req.edited_rule_data["topic"]

    await db.commit()
    await db.refresh(rule)
    return _to_rule_response(rule)
