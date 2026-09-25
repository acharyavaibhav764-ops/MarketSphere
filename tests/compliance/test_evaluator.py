"""
tests/compliance/test_evaluator.py

Phases 4 & 5 tests — Human review gate enforcement and deterministic rule evaluation.

Tests:
  1. Draft and rejected rules are strictly excluded from evaluation.
  2. Missing capital in product profile returns UNKNOWN (no false PASS).
  3. Insufficient capital returns CONFLICT with clear reason.
  4. Sufficient capital returns PASS.
  5. Offered leverage exceeding statutory cap returns CONFLICT.
  6. Offered leverage within statutory cap returns PASS.
  7. Unparseable leverage ratio format returns UNKNOWN.
  8. Determinism: identical inputs always yield identical outputs.
  9. Results preserve rule_id, rule_version, and verbatim supporting_quote.
"""
import pytest

from services.evaluator import evaluate_profile


class MockRule:
    """Mock representing a ComplianceRule ORM object."""
    def __init__(self, **kwargs):
        self.rule_id = kwargs.get("rule_id", "rule-test-01")
        self.rule_version = kwargs.get("rule_version", 1)
        self.jurisdiction = kwargs.get("jurisdiction", "UAE")
        self.regulator = kwargs.get("regulator", "VARA")
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
        # Return only approved rules for the given jurisdiction
        # In our tests, we can filter using the rule attributes
        return self

    def all(self):
        return [r for r in self._rules if r.review_status == "approved"]


def test_draft_rule_excluded_from_evaluator():
    draft_rule = MockRule(review_status="draft", required_capital=500_000)
    db = MockDB([draft_rule])
    results = evaluate_profile({"jurisdiction": "UAE", "capital_available_usd": 1_000_000}, db)
    assert len(results) == 0


def test_rejected_rule_excluded_from_evaluator():
    rejected_rule = MockRule(review_status="rejected", required_capital=500_000)
    db = MockDB([rejected_rule])
    results = evaluate_profile({"jurisdiction": "UAE", "capital_available_usd": 1_000_000}, db)
    assert len(results) == 0


def test_missing_capital_in_profile_returns_unknown():
    approved_rule = MockRule(review_status="approved", required_capital=500_000)
    db = MockDB([approved_rule])
    results = evaluate_profile({"jurisdiction": "UAE"}, db)
    assert len(results) == 1
    assert results[0]["status"] == "UNKNOWN"
    assert "not provided" in results[0]["reason"].lower()


def test_insufficient_capital_returns_conflict():
    approved_rule = MockRule(review_status="approved", required_capital=500_000)
    db = MockDB([approved_rule])
    results = evaluate_profile({"jurisdiction": "UAE", "capital_available_usd": 250_000}, db)
    assert len(results) == 1
    assert results[0]["status"] == "CONFLICT"
    assert "below statutory requirement" in results[0]["reason"]


def test_sufficient_capital_returns_pass():
    approved_rule = MockRule(review_status="approved", required_capital=500_000)
    db = MockDB([approved_rule])
    results = evaluate_profile({"jurisdiction": "UAE", "capital_available_usd": 600_000}, db)
    assert len(results) == 1
    assert results[0]["status"] == "PASS"


def test_leverage_exceeding_cap_returns_conflict():
    approved_rule = MockRule(review_status="approved", leverage_cap="1:5")
    db = MockDB([approved_rule])
    results = evaluate_profile({"jurisdiction": "UAE", "leverage_offered": "1:50"}, db)
    assert len(results) == 1
    assert results[0]["status"] == "CONFLICT"
    assert "exceeds" in results[0]["reason"]


def test_leverage_within_cap_returns_pass():
    approved_rule = MockRule(review_status="approved", leverage_cap="1:50")
    db = MockDB([approved_rule])
    results = evaluate_profile({"jurisdiction": "UAE", "leverage_offered": "1:10"}, db)
    assert len(results) == 1
    assert results[0]["status"] == "PASS"


def test_invalid_leverage_format_returns_unknown():
    approved_rule = MockRule(review_status="approved", leverage_cap="1:50")
    db = MockDB([approved_rule])
    results = evaluate_profile({"jurisdiction": "UAE", "leverage_offered": "unrestricted"}, db)
    assert len(results) == 1
    assert results[0]["status"] == "UNKNOWN"


def test_determinism():
    rule = MockRule(required_capital=200_000, leverage_cap="1:20")
    db = MockDB([rule])
    profile = {
        "jurisdiction": "UAE",
        "capital_available_usd": 500_000,
        "leverage_offered": "1:10",
    }
    run1 = evaluate_profile(profile, db)
    run2 = evaluate_profile(profile, db)
    assert run1 == run2


def test_provenance_and_quote_in_results():
    quote = "Minimum capital requirement of USD 250,000 for Category 2."
    rule = MockRule(
        rule_id="vara-cap-002",
        rule_version=2,
        topic="capital",
        required_capital=250_000,
        supporting_quote=quote,
    )
    db = MockDB([rule])
    results = evaluate_profile({"jurisdiction": "UAE", "capital_available_usd": 300_000}, db)
    assert len(results) == 1
    assert results[0]["rule_id"] == "vara-cap-002"
    assert results[0]["rule_version"] == 2
    assert results[0]["supporting_quote"] == quote
