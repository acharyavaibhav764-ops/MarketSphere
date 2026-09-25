"""
api/v1/endpoints/compliance.py — Country-specific compliance analysis API.

  GET  /api/v1/compliance/countries — Countries with approved requirements.
  POST /api/v1/compliance/analyze   — Compare user rules against the selected
                                      country's approved requirements.
  POST /api/v1/compliance/chat      — Follow-up Q&A over the report context.

Only approved requirements participate. Drafts are invisible to analysis.
User uploads are the *subject* of analysis, never the regulatory source.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from models.rule import ComplianceRule
from models.source import SourceRegistry
from schemas.compliance import (
    ComplianceAnalyzeRequest,
    ComplianceChatRequest,
    ComplianceChatResponse,
    ComplianceReport,
    CountryInfo,
)
from services.country_compliance import (
    MAX_RULE_CHARS,
    MAX_RULES,
    analyze_country_compliance,
    answer_compliance_question,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/compliance", tags=["Country Compliance"])


async def _load_country_data(
    db: AsyncSession, country: str
) -> tuple[list, dict]:
    """Approved requirements + source map for one country (case-insensitive)."""
    wanted = (country or "").strip().lower()
    result = await db.execute(
        select(ComplianceRule).where(ComplianceRule.review_status == "approved")
    )
    approved = [
        r for r in result.scalars().all()
        if (r.jurisdiction or "").lower() == wanted
    ]
    source_map: dict = {}
    if approved:
        src_ids = {r.source_id for r in approved if r.source_id}
        if src_ids:
            srcs = (
                await db.execute(
                    select(SourceRegistry).where(SourceRegistry.source_id.in_(src_ids))
                )
            ).scalars().all()
            source_map = {s.source_id: s for s in srcs}
    return approved, source_map


@router.get(
    "/countries",
    response_model=list[CountryInfo],
    summary="List countries with approved requirements",
)
async def list_countries(db: AsyncSession = Depends(get_db)) -> list[CountryInfo]:
    result = await db.execute(
        select(ComplianceRule).where(ComplianceRule.review_status == "approved")
    )
    approved = list(result.scalars().all())
    srcs = (await db.execute(select(SourceRegistry))).scalars().all()
    src_count: dict[str, int] = {}
    for s in srcs:
        src_count[s.jurisdiction] = src_count.get(s.jurisdiction, 0) + 1

    by_country: dict[str, dict] = {}
    for r in approved:
        entry = by_country.setdefault(
            r.jurisdiction, {"regs": set(), "count": 0}
        )
        entry["count"] += 1
        if r.regulator:
            entry["regs"].add(r.regulator)
    return [
        CountryInfo(
            country=country,
            regulators=sorted(info["regs"]),
            approved_requirements=info["count"],
            sources=src_count.get(country, 0),
        )
        for country, info in sorted(by_country.items())
    ]


@router.post(
    "/analyze",
    response_model=ComplianceReport,
    summary="Analyze user rules against a country's requirements",
)
async def analyze_compliance(
    request: ComplianceAnalyzeRequest,
    db: AsyncSession = Depends(get_db),
) -> ComplianceReport:
    country = (request.country or "").strip()
    if not country:
        raise HTTPException(status_code=400, detail="Select a country first.")
    cleaned = [(r or "").strip() for r in (request.rules or [])]
    cleaned = [r for r in cleaned if r]
    if not cleaned:
        raise HTTPException(
            status_code=400,
            detail="No rules were provided. Type, paste, or upload rules first.",
        )
    if len(cleaned) > MAX_RULES:
        raise HTTPException(
            status_code=400, detail=f"Too many rules ({len(cleaned)}). Limit is {MAX_RULES}."
        )
    too_long = [i + 1 for i, r in enumerate(cleaned) if len(r) > MAX_RULE_CHARS]
    if too_long:
        raise HTTPException(
            status_code=400,
            detail=f"Rule(s) {too_long} exceed {MAX_RULE_CHARS} characters.",
        )

    try:
        approved, source_map = await _load_country_data(db, country)
    except Exception as exc:
        logger.exception("Compliance analysis failed while loading requirements")
        raise HTTPException(status_code=503, detail=f"Requirement store unavailable: {exc}")

    try:
        report = analyze_country_compliance(
            country=country,
            user_rules=cleaned,
            approved_requirements=approved,
            source_map=source_map,
            context=request.context.model_dump(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return ComplianceReport(**report)


@router.post(
    "/chat",
    response_model=ComplianceChatResponse,
    summary="Ask a follow-up question about the compliance report",
)
async def compliance_chat(
    request: ComplianceChatRequest,
    db: AsyncSession = Depends(get_db),
) -> ComplianceChatResponse:
    question = (request.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Please type a question first.")
    if len(question) > 2000:
        raise HTTPException(status_code=400, detail="The question is too long.")
    country = (request.country or "").strip() or "the selected country"

    rules = [(r or "").strip() for r in (request.rules or [])]
    rules = [r for r in rules if r][:MAX_RULES]

    report = request.report.model_dump() if request.report is not None else None
    if report is None and rules:
        try:
            approved, source_map = await _load_country_data(db, country)
            report = analyze_country_compliance(
                country=country,
                user_rules=rules,
                approved_requirements=approved,
                source_map=source_map,
                context=request.context.model_dump(),
            )
        except Exception as exc:
            logger.warning("Chat-context analysis failed: %s", exc)
            report = None

    result = answer_compliance_question(
        country, rules, report, request.context.model_dump(), question
    )
    return ComplianceChatResponse(content=result["content"], action=result.get("action"))
