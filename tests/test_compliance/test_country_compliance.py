"""
tests/test_compliance/test_country_compliance.py — Country compliance engine.

Verifies: grounding on approved requirements only, verdict taxonomy,
severity + transparent scoring, gaps vs violations distinction,
missing-information honesty, NOT_APPLICABLE scoping, and chat context.
"""
import pytest

from services.country_compliance import (
    analyze_country_compliance,
    answer_compliance_question,
    detect_topics,
)


class FakeReq:
    def __init__(self, **kw):
        self.rule_id = kw.get("rule_id", "req-1")
        self.jurisdiction = kw.get("jurisdiction", "Brazil")
        self.regulator = kw.get("regulator", "CVM / BCB")
        self.topic = kw.get("topic", "leverage")
        self.rule_data = kw.get("rule_data", {
            "obligation_or_restriction": kw.get("obligation", "Retail leverage capped at 1:20."),
            "supporting_quote": kw.get("quote", "leverage shall not exceed 1:20."),
        })
        self.evidence_tag = kw.get("evidence_tag", "Verified Fact")
        self.leverage_cap = kw.get("leverage_cap")
        self.required_capital = kw.get("required_capital")
        self.review_status = kw.get("review_status", "approved")
        self.reviewed_at = kw.get("reviewed_at")
        self.source_id = kw.get("source_id", "src-br")


class FakeSource:
    def __init__(self, **kw):
        self.source_id = kw.get("source_id", "src-br")
        self.regulator = kw.get("regulator", "CVM / BCB")
        self.title = kw.get("title", "CVM Resolution 4.924")
        self.source_url = kw.get("source_url", "https://example.gov.br/norm")


def br_requirements():
    return [
        FakeReq(rule_id="br-lev", topic="leverage", leverage_cap="1:20",
                obligation="Retail customer margin leverage capped at 1:20."),
        FakeReq(rule_id="br-cap", topic="capital", required_capital=600000.0,
                leverage_cap=None,
                obligation="Derivative dealers must maintain capital of BRL 3,000,000.",
                quote="Dealers must maintain capital of BRL 3,000,000."),
    ]


def sources():
    return {"src-br": FakeSource()}


def test_compliant_leverage_within_cap():
    rep = analyze_country_compliance(
        "Brazil", ["Our retail leverage offering is capped at 1:10."],
        br_requirements(), sources())
    assert rep["rules"][0]["status"] == "COMPLIANT"
    assert rep["compatibility"]["score"] == 100
    assert rep["compatibility"]["label"] == "Highly compatible"


def test_non_compliant_leverage_breach_has_severity_and_source():
    rep = analyze_country_compliance(
        "Brazil", ["We offer clients leverage of up to 1:50."],
        br_requirements(), sources())
    item = rep["rules"][0]
    assert item["status"] == "NON_COMPLIANT"
    assert item["severity"] == "HIGH"
    assert "1:20" in (item["country_requirement"] or "")
    assert item["required_action"]
    assert item["sources"] and item["sources"][0]["authority"] == "CVM / BCB"
    assert rep["violations"] and rep["violations"][0]["rule_id"] == 1
    assert any(c["kind"] == "regulatory" for c in rep["conflicts"])
    assert rep["compatibility"]["score"] == 85  # 100 - 15 (HIGH)
    assert "100" in rep["compatibility"]["methodology"]


def test_waiver_of_required_license_is_critical():
    reqs = br_requirements() + [
        FakeReq(rule_id="br-lic", topic="license", leverage_cap=None,
                obligation="Broker-dealer license is mandatory before operating."),
    ]
    rep = analyze_country_compliance(
        "Brazil", ["No license is required to operate."], reqs, sources())
    item = rep["rules"][0]
    assert item["status"] == "NON_COMPLIANT"
    assert item["severity"] == "CRITICAL"
    assert rep["compatibility"]["score"] == 75  # 100 - 25


def test_partially_compliant_missing_mechanism():
    reqs = br_requirements() + [
        FakeReq(rule_id="br-cert", topic="certification", leverage_cap=None,
                obligation="Products must hold the applicable conformity certification."),
    ]
    rep = analyze_country_compliance(
        "Brazil", ["Product must be certified."], reqs, sources())
    item = rep["rules"][0]
    assert item["status"] == "PARTIALLY_COMPLIANT"
    assert item["required_action"]
    assert rep["compatibility"]["score"] == 96  # 100 - 4


def test_no_identified_requirement_is_undetermined_not_guessed():
    rep = analyze_country_compliance(
        "Brazil", ["No import license is required."],
        br_requirements(), sources())
    item = rep["rules"][0]
    assert item["status"] == "UNDETERMINED"
    assert item["severity"] is None
    assert item["missing_information"]
    assert rep["compatibility"]["score"] == 100  # undetermined never subtracts


def test_gap_for_unaddressed_requirement():
    rep = analyze_country_compliance(
        "Brazil", ["Our leverage offering is capped at 1:10."],
        br_requirements(), sources())
    topics = [g["topic"] for g in rep["gaps"]]
    assert "capital" in topics
    gap = next(g for g in rep["gaps"] if g["topic"] == "capital")
    assert gap["why_it_matters"] and gap["sources"]
    assert rep["required_actions"]


def test_not_applicable_for_other_jurisdiction():
    rep = analyze_country_compliance(
        "Brazil", ["This product follows United States CFTC rules only."],
        br_requirements(), sources())
    assert rep["rules"][0]["status"] == "NOT_APPLICABLE"


def test_internal_user_conflict_detected():
    rep = analyze_country_compliance(
        "Brazil",
        ["Revenue must exceed Rs.100 crore.", "Revenue must be below Rs.50 crore."],
        br_requirements(), sources())
    kinds = [c["kind"] for c in rep["conflicts"]]
    assert "internal" in kinds


def test_context_triggers_missing_information():
    rep = analyze_country_compliance(
        "Brazil", ["Product must be certified.", "Import tax is 10%."],
        br_requirements() + [
            FakeReq(rule_id="br-cert", topic="certification", leverage_cap=None,
                    obligation="Certification applies per product category."),
        ],
        sources(), context={})
    needed = " ".join(rep["missing_information"])
    assert "NCM" in needed
    assert "Product description" in needed or "product" in needed.lower()


def test_every_rule_gets_a_verdict():
    rules = [
        "Our leverage is capped at 1:10.",
        "The product must be certified somehow.",
        "Blah blah nothing verifiable here at all xyz.",
    ]
    rep = analyze_country_compliance("Brazil", rules, br_requirements(), sources())
    assert rep["summary"]["total_rules"] == 3
    assert len(rep["rules"]) == 3
    assert all(r["status"] and r["explanation"] for r in rep["rules"])


def test_bare_ratio_statement_is_tested():
    rep = analyze_country_compliance(
        "Brazil", ["We offer 1:30 leverage on FX."],
        br_requirements(), sources())
    assert rep["rules"][0]["status"] == "NON_COMPLIANT"


def test_foreign_currency_capital_not_converted():
    reqs = [FakeReq(rule_id="sg-cap", jurisdiction="Singapore", regulator="MAS",
                    topic="capital", required_capital=750000.0, leverage_cap=None,
                    obligation="Maintain base capital of SGD 1,000,000.",
                    quote="base capital of SGD 1,000,000.")]
    rep = analyze_country_compliance(
        "Singapore", ["We hold SGD 2 million in base capital."],
        reqs, {"s": FakeSource()})
    item = rep["rules"][0]
    assert item["status"] == "PARTIALLY_COMPLIANT"
    assert "USD" in " ".join(item["missing_information"])


def test_country_without_requirements_is_insufficient_data():
    rep = analyze_country_compliance("Atlantis", ["We offer 1:50 leverage."], [], {})
    assert rep["rules"][0]["status"] == "UNDETERMINED"
    assert rep["compatibility"]["score"] == 0
    assert rep["compatibility"]["label"] == "Insufficient data"


def test_empty_rules_raise():
    with pytest.raises(ValueError):
        analyze_country_compliance("Brazil", [], br_requirements(), {})


def test_topic_detection():
    assert "capital" in detect_topics("Maintain paid-up capital of USD 1M.")
    assert "tax" in detect_topics("Import duty must be paid.")
    assert detect_topics("The sky is blue.") == []


# --- Chat --------------------------------------------------------------------

def _report():
    return analyze_country_compliance(
        "Brazil",
        ["We offer clients leverage of up to 1:50.", "Product must be certified."],
        br_requirements() + [
            FakeReq(rule_id="br-cert", topic="certification", leverage_cap=None,
                    obligation="Products must hold the applicable conformity certification."),
        ],
        sources())


def test_chat_why_non_compliant():
    out = answer_compliance_question(
        "Brazil", ["We offer clients leverage of up to 1:50."], _report(), {},
        "Why is Rule 1 non-compliant?")
    assert "1:20" in out["content"]
    assert out["action"] is None


def test_chat_violations_only():
    out = answer_compliance_question(
        "Brazil", ["We offer clients leverage of up to 1:50."], _report(), {},
        "Show only critical violations")
    assert out["content"]


def test_chat_missing_information():
    out = answer_compliance_question(
        "Brazil", ["Product must be certified."], _report(), {},
        "What information are you missing?")
    assert out["content"]


def test_chat_sources():
    out = answer_compliance_question(
        "Brazil", ["We offer clients leverage of up to 1:50."], _report(), {},
        "What source supports this finding for Rule 1?")
    assert "CVM / BCB" in out["content"]


def test_chat_reanalyze_action():
    out = answer_compliance_question(
        "Brazil", ["We offer clients leverage of up to 1:50."], _report(), {},
        "Recalculate after changing Rule 1")
    assert out["action"] == "reanalyze"
