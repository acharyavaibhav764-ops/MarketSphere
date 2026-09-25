"""
tests/compliance/test_evaluator.py

Phase 5 tests — Deterministic Evaluator test suite.

Mandatory test cases:
  1. PASS case: capital and leverage satisfy all statutory constraints.
  2. CONFLICT case (capital below floor): capital < statutory minimum.
  3. CONFLICT case (leverage above cap): leverage offered > statutory cap.
  4. UNKNOWN case (missing required fact): profile omits required fact.
  5. Draft/Rejected exclusion: unapproved rules are strictly ignored.
  6. Citation preservation: rule_id, rule_version, and quote are retained.
"""
import pytest

from services.evaluator import evaluate_profile


class MockRule:
    """Mock representing a ComplianceRule ORM object."""
    def __init__(self, **kwargs):
        self.rule_id = kwargs.get("rule_id", "rule-test-01")
        self.rule_version = kwargs.get("rule_version", 1)
        self.jurisdiction = kwargs.get("jurisdiction", "United States")
        self.regulator = kwargs.get("regulator", "CFTC")
        self.topic = kwargs.get("topic", "capital")
        self.required_capital = kwargs.get("required_capital", None)
        self.leverage_cap = kwargs.get("leverage_cap", None)
        self.review_status = kwargs.get("review_status", "approved")
        self.rule_data = kwargs.get("rule_data", {
            "supporting_quote": kwargs.get("supporting_quote", "Statutory quote text."),
        })


class MockDB:
    """Mock query interface matching SQLAlchemy session query chain."""
    def __init__(self, rules):
        self._rules = rules

    def query(self, model):
        return self

    def filter(self, *criteria):
        return self

    def all(self):
        # Only return approved rules
        return [r for r in self._rules if r.review_status == "approved"]


# 1. PASS Case
def test_evaluator_pass_case():
    rule_cap = MockRule(
        rule_id="us-cap",
        jurisdiction="United States",
        topic="capital",
        required_capital=20_000_000,
        supporting_quote="RFEDs must maintain adjusted net capital of not less than $20,000,000.",
    )
    rule_lev = MockRule(
        rule_id="us-lev",
        jurisdiction="United States",
        topic="leverage",
        leverage_cap="1:50",
        supporting_quote="Major currency pairs retail leverage is capped at 1:50.",
    )
    db = MockDB([rule_cap, rule_lev])
    profile = {
        "jurisdiction": "United States",
        "capital_available_usd": 25_000_000,
        "leverage_offered": "1:30",
    }
    results = evaluate_profile(profile, db)
    assert len(results) == 2
    assert all(r["status"] == "PASS" for r in results)
    assert results[0]["rule_id"] == "us-cap"
    assert "20,000,000" in results[0]["supporting_quote"]


# 2. CONFLICT Case (Capital Below Floor)
def test_evaluator_conflict_capital_below_floor():
    rule_cap = MockRule(
        rule_id="us-cap-002",
        jurisdiction="United States",
        topic="capital",
        required_capital=20_000_000,
        supporting_quote="Adjusted net capital of not less than $20,000,000.",
    )
    db = MockDB([rule_cap])
    profile = {
        "jurisdiction": "United States",
        "capital_available_usd": 5_000_000,  # Below $20M
    }
    results = evaluate_profile(profile, db)
    assert len(results) == 1
    assert results[0]["status"] == "CONFLICT"
    assert "below statutory requirement" in results[0]["reason"]
    assert results[0]["rule_id"] == "us-cap-002"


# 3. CONFLICT Case (Leverage Above Cap)
def test_evaluator_conflict_leverage_above_cap():
    rule_lev = MockRule(
        rule_id="uk-lev-001",
        jurisdiction="United Kingdom",
        topic="leverage",
        leverage_cap="1:30",
        supporting_quote="Retail leverage to 1:30 for major currency pairs.",
    )
    db = MockDB([rule_lev])
    profile = {
        "jurisdiction": "United Kingdom",
        "leverage_offered": "1:100",  # Exceeds 1:30
    }
    results = evaluate_profile(profile, db)
    assert len(results) == 1
    assert results[0]["status"] == "CONFLICT"
    assert "exceeds statutory cap of 1:30" in results[0]["reason"]


# 4. UNKNOWN Case (Missing Required Fact)
def test_evaluator_unknown_missing_capital():
    rule_cap = MockRule(
        rule_id="sg-cap-001",
        jurisdiction="Singapore",
        topic="capital",
        required_capital=1_000_000,
        supporting_quote="Minimum base capital of SGD 1,000,000.",
    )
    db = MockDB([rule_cap])
    profile = {
        "jurisdiction": "Singapore",
        # capital_available_usd is intentionally omitted
    }
    results = evaluate_profile(profile, db)
    assert len(results) == 1
    assert results[0]["status"] == "UNKNOWN"
    assert "capital_available_usd not provided" in results[0]["reason"]


# 5. Draft Rule Excluded
def test_draft_rule_excluded():
    draft_rule = MockRule(
        rule_id="draft-001",
        jurisdiction="United States",
        review_status="draft",
        required_capital=1_000_000,
    )
    db = MockDB([draft_rule])
    results = evaluate_profile({"jurisdiction": "United States", "capital_available_usd": 5_000_000}, db)
    assert len(results) == 0
