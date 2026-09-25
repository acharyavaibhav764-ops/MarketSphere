"""
tests/test_compliance/test_compliance_api.py — /compliance endpoint tests.

In-memory SQLite store via dependency override, seeded with one approved
and one draft Brazil requirement. Proves drafts are invisible to analysis
and the report endpoint works end to end.
"""
import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession, create_async_engine

from core.database import get_db
from main import app
from models.rule import ComplianceRule
from models.source import Base, SourceRegistry


@pytest.fixture()
def client():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(bind=eng, class_=AsyncSession, expire_on_commit=False)

    async def seed():
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with sessions() as db:
            db.add(SourceRegistry(
                source_id="src-br", jurisdiction="Brazil", regulator="CVM / BCB",
                title="CVM Resolution", source_type="TXT",
                source_status="active", processing_status="parsed"))
            db.add(ComplianceRule(
                rule_id="br-lev", source_id="src-br", jurisdiction="Brazil",
                regulator="CVM / BCB", topic="leverage",
                rule_data={"obligation_or_restriction": "Retail leverage capped at 1:20.",
                           "supporting_quote": "leverage shall not exceed 1:20."},
                evidence_tag="Verified Fact", leverage_cap="1:20",
                required_capital=None, review_status="approved"))
            db.add(ComplianceRule(
                rule_id="br-cap", source_id="src-br", jurisdiction="Brazil",
                regulator="CVM / BCB", topic="capital",
                rule_data={"obligation_or_restriction": "Maintain capital of BRL 3M.",
                           "supporting_quote": "capital of BRL 3M required."},
                evidence_tag="Verified Fact", leverage_cap=None,
                required_capital=600000.0, review_status="draft"))
            db.add(ComplianceRule(
                rule_id="br-pres", source_id="src-br", jurisdiction="Brazil",
                regulator="CVM / BCB", topic="presence",
                rule_data={"obligation_or_restriction": "Maintain a local office.",
                           "supporting_quote": "local office required."},
                evidence_tag="Verified Fact", leverage_cap=None,
                required_capital=None, review_status="approved"))
            await db.commit()

    asyncio.run(seed())

    async def override():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_db] = override
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


def test_countries_lists_brazil(client):
    res = client.get("/api/v1/compliance/countries")
    assert res.status_code == 200
    brazil = next((c for c in res.json() if c["country"] == "Brazil"), None)
    assert brazil is not None
    assert brazil["approved_requirements"] == 2
    assert "CVM / BCB" in brazil["regulators"]


def test_analyze_uses_approved_only(client):
    res = client.post("/api/v1/compliance/analyze", json={
        "country": "Brazil",
        "rules": ["We offer leverage up to 1:50."],
        "context": {},
    })
    assert res.status_code == 200
    body = res.json()
    assert body["rules"][0]["status"] == "NON_COMPLIANT"
    # Draft capital requirement is invisible: neither matched nor a gap.
    assert not any(g["topic"] == "capital" for g in body["gaps"])
    # The approved (but unaddressed) presence requirement surfaces as a gap.
    assert any(g["topic"] == "presence" for g in body["gaps"])
    assert body["compatibility"]["score"] == 85


def test_analyze_empty_rules_rejected(client):
    res = client.post("/api/v1/compliance/analyze", json={
        "country": "Brazil", "rules": [], "context": {},
    })
    assert res.status_code == 400


def test_chat_over_report(client):
    res = client.post("/api/v1/compliance/chat", json={
        "country": "Brazil",
        "rules": ["We offer leverage up to 1:50."],
        "question": "Why is Rule 1 non-compliant?",
    })
    assert res.status_code == 200
    assert "1:20" in res.json()["content"]
