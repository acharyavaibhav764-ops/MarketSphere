"""
Seed the rule/source store with the curated 15-market demo dataset.

The dataset lives in frontend/app.js (the Demo Mode data). This script copies
it into the real backend database so Live mode shows the same product data
and the hackathon demo can run end-to-end (evaluate, approve, ingest).

Usage:
    set DATABASE_URL=sqlite+aiosqlite:///./marketsphere.db
    python scripts/seed_demo.py

Idempotent: does nothing when rules already exist. A few rules are seeded as
'draft' so the Human Review Queue has items to approve during the demo.
"""
import asyncio
import datetime
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select  # noqa: E402

from config import settings  # noqa: E402
from core.database import engine, AsyncSessionLocal  # noqa: E402
from models.source import Base, SourceRegistry  # noqa: E402
from models.rule import ComplianceRule  # noqa: E402

# Rules seeded as 'draft' so the review-queue approve flow is demoable.
DEMO_DRAFT_RULE_IDS = {"br-cvm-cap-002", "kr-fsc-cap-002", "in-sebi-cap-002"}


def _extract_array(js_text: str, key: str):
    """Bracket-match a top-level `key: [...]` JS array and parse it as JSON."""
    start_token = f"{key}: ["
    start = js_text.find(start_token)
    if start == -1:
        raise ValueError(f"array '{key}' not found in app.js")
    i = js_text.find("[", start)
    depth = 0
    in_str = None
    esc = False
    for j in range(i, len(js_text)):
        ch = js_text[j]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == in_str:
                in_str = None
            continue
        if ch in ("'", '"'):
            in_str = ch
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return json.loads(js_text[i : j + 1])
    raise ValueError(f"array '{key}' is unterminated")


def _parse_dt(value):
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(value.replace("Z", "+00:00")).replace(
            tzinfo=None
        )
    except (ValueError, AttributeError):
        return None


async def main() -> None:
    if engine is None or AsyncSessionLocal is None:
        print("Database engine unavailable — cannot seed.")
        print("Set DATABASE_URL, e.g.: sqlite+aiosqlite:///./marketsphere.db")
        raise SystemExit(1)

    print(f"DATABASE_URL in use: {settings.database_url}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    js_text = (PROJECT_ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    sources = _extract_array(js_text, "sources")
    rules = _extract_array(js_text, "rules")
    print(f"Demo dataset: {len(sources)} sources, {len(rules)} rules")

    async with AsyncSessionLocal() as db:
        existing = (await db.execute(select(ComplianceRule.rule_id))).scalars().all()
        if existing:
            print(f"Already seeded ({len(existing)} rules) — nothing to do.")
            return

        for s in sources:
            db.add(
                SourceRegistry(
                    source_id=s["source_id"],
                    jurisdiction=s["jurisdiction"],
                    regulator=s["regulator"],
                    title=s["title"],
                    source_type=s.get("source_type", "TXT"),
                    instrument_type=s.get("instrument_type"),
                    content_hash=s.get("content_hash"),
                    storage_uri=s.get("storage_uri"),
                    source_status=s.get("source_status", "active"),
                    processing_status=s.get("processing_status", "parsed"),
                )
            )
        await db.commit()

        drafts = 0
        for r in rules:
            is_draft = r["rule_id"] in DEMO_DRAFT_RULE_IDS
            drafts += 1 if is_draft else 0
            db.add(
                ComplianceRule(
                    rule_id=r["rule_id"],
                    rule_version=r.get("rule_version", 1),
                    source_id=r["source_id"],
                    jurisdiction=r["jurisdiction"],
                    regulator=r.get("regulator"),
                    topic=r.get("topic", "general"),
                    rule_data={
                        "obligation_or_restriction": r.get("obligation", ""),
                        "supporting_quote": r.get("supporting_quote", ""),
                        "leverage_cap_retail": r.get("leverage_cap_retail"),
                        "required_capital_usd": r.get("required_capital_usd"),
                        "presence_friction_summary": r.get("presence_friction_summary"),
                        "evidence_tag": r.get("evidence_tag", "Verified Fact"),
                        "source_id": r["source_id"],
                        "page_number": r.get("page_number"),
                        "section_heading": r.get("section_heading", ""),
                        "extraction_model": r.get("extraction_model", "legal-parser-v5"),
                    },
                    evidence_tag=r.get("evidence_tag", "Verified Fact"),
                    leverage_cap=r.get("leverage_cap_retail"),
                    required_capital=r.get("required_capital_usd"),
                    review_status="draft" if is_draft else "approved",
                    reviewer_id=None if is_draft else r.get("reviewer_id"),
                    reviewed_at=None if is_draft else _parse_dt(r.get("reviewed_at")),
                )
            )
        await db.commit()
        print(f"Seeded {len(sources)} sources, {len(rules)} rules ({drafts} drafts).")


if __name__ == "__main__":
    asyncio.run(main())
