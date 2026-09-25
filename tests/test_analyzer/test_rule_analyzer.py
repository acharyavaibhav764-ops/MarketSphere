"""
tests/test_analyzer/test_rule_analyzer.py — AI Rule Analyzer engine tests.

Covers: every-rule-analyzed guarantee, all six statuses, cross-rule
conflicts/duplicates/overlaps, summary counts, splitter behavior,
LLM-path validation, and the follow-up chat responder.
"""
import pytest

from services.rule_analyzer import (
    analyze_rules,
    analyze_with_llm,
    answer_followup,
    split_rules,
)


def statuses_of(result):
    return {r["number"]: r["status"] for r in result["rules"]}


# --- Guarantee: every rule analyzed, none skipped --------------------------

def test_every_rule_receives_a_result():
    rules = [f"Revenue must exceed ₹{i} crore." for i in range(1, 11)]
    result = analyze_rules(rules)
    assert result["total"] == 10
    assert len(result["rules"]) == 10
    assert [r["number"] for r in result["rules"]] == list(range(1, 11))
    assert all(r["original"] for r in result["rules"])
    assert all(r["status"] for r in result["rules"])
    assert all(r["explanation"] for r in result["rules"])


def test_empty_input_raises():
    with pytest.raises(ValueError):
        analyze_rules([])
    with pytest.raises(ValueError):
        analyze_rules(["   ", ""])


# --- Statuses ----------------------------------------------------------------

def test_valid_rule():
    result = analyze_rules(["Revenue must exceed ₹10 crore."])
    assert statuses_of(result) == {1: "VALID"}


def test_incorrect_self_contradiction():
    result = analyze_rules(
        ["Revenue must be less than ₹5 crore while requiring ₹10+ crore revenue."]
    )
    assert statuses_of(result) == {1: "INCORRECT"}
    assert result["rules"][0]["suggested_correction"]


def test_incorrect_impossible_percentage():
    result = analyze_rules(["Market share must exceed 150%."])
    assert statuses_of(result) == {1: "INCORRECT"}


def test_needs_clarification_ambiguous():
    result = analyze_rules(["The company must be profitable."])
    assert statuses_of(result) == {1: "NEEDS_CLARIFICATION"}
    assert result["rules"][0]["missing_information"]
    assert result["rules"][0]["suggested_correction"]


def test_incomplete_missing_threshold():
    result = analyze_rules(["Revenue must exceed the prescribed limit."])
    assert statuses_of(result) == {1: "INCOMPLETE"}
    assert result["rules"][0]["missing_information"]


def test_undetermined_garbled():
    result = analyze_rules(["asdf qwerty"])
    assert statuses_of(result) == {1: "UNDETERMINED"}


# --- Cross-rule analysis -----------------------------------------------------

def test_direct_conflict_detected():
    result = analyze_rules([
        "Revenue must exceed ₹100 crore.",
        "Revenue must be below ₹50 crore.",
    ])
    assert statuses_of(result) == {1: "CONFLICTING", 2: "CONFLICTING"}
    assert len(result["cross_rule_conflicts"]) == 1
    conflict = result["cross_rule_conflicts"][0]
    assert conflict["kind"] == "contradiction"
    assert conflict["rules"] == [1, 2]
    assert result["summary"]["conflicting"] == 2
    assert result["critical_issues"]


def test_no_invented_conflict_across_currencies():
    result = analyze_rules([
        "Revenue must exceed ₹100 crore.",
        "Revenue must be below $50 million.",
    ])
    kinds = [c["kind"] for c in result["cross_rule_conflicts"]]
    assert "contradiction" not in kinds
    assert statuses_of(result)[1] == "VALID"


def test_duplicate_detected():
    result = analyze_rules([
        "EBITDA must be positive for the latest financial year.",
        "EBITDA must be positive for the latest financial year.",
    ])
    kinds = [c["kind"] for c in result["cross_rule_conflicts"]]
    assert "duplicate" in kinds


def test_overlap_detected():
    result = analyze_rules([
        "Revenue must exceed ₹10 crore.",
        "Revenue must exceed ₹50 crore.",
    ])
    kinds = [c["kind"] for c in result["cross_rule_conflicts"]]
    assert "overlap" in kinds
    assert "contradiction" not in kinds


def test_summary_counts_add_up():
    result = analyze_rules([
        "Profit must exceed ₹10 crore for FY2024.",  # VALID
        "The company must be profitable.",           # NEEDS_CLARIFICATION
        "Market share must exceed 150%.",            # INCORRECT
        "Revenue must exceed the limit.",            # INCOMPLETE
        "Revenue must exceed ₹100 crore.",           # CONFLICTING (vs rule 6)
        "Revenue must be below ₹50 crore.",          # CONFLICTING (vs rule 5)
        "asdf qwerty",                               # UNDETERMINED
    ])
    s = result["summary"]
    assert s["total"] == 7
    assert (s["valid"] + s["needs_clarification"] + s["incorrect"]
            + s["conflicting"] + s["incomplete"] + s["undetermined"]) == 7
    assert s["valid"] == 1
    assert s["needs_clarification"] == 1
    assert s["incorrect"] == 1
    assert s["incomplete"] == 1
    assert s["undetermined"] == 1
    assert s["conflicting"] == 2  # rules 5 and 6


# --- Splitter -----------------------------------------------------------------

def test_split_numbered_and_bullets():
    text = "1. Revenue must exceed ₹10 crore.\n2. EBITDA must be positive.\n- Keep staff below 20."
    rules = split_rules(text)
    assert len(rules) == 3
    assert rules[0]["text"] == "Revenue must exceed ₹10 crore."
    assert rules[2]["text"] == "Keep staff below 20."


def test_split_continuation_lines_merge():
    text = "1. Revenue must exceed\n₹10 crore in total."
    rules = split_rules(text)
    assert len(rules) == 1
    assert "₹10 crore" in rules[0]["text"]


def test_split_never_discards_content():
    text = "Just a paragraph about revenue exceeding ten crore widely."
    rules = split_rules(text)
    assert len(rules) == 1


# --- LLM path -----------------------------------------------------------------

class _FakeLLM:
    def __init__(self, payload):
        self._payload = payload

    def chat(self, messages):
        assert messages[0]["role"] == "system"
        assert "RULES:" in messages[1]["content"]
        return {"message": {"content": self._payload}}


def _llm_payload():
    import json
    return json.dumps({
        "total": 1,
        "rules": [{
            "number": 1, "original": "Revenue must exceed ₹10 crore.",
            "status": "VALID", "explanation": "Measurable threshold.",
            "reasoning": [], "missing_information": [],
            "suggested_correction": None,
        }],
        "cross_rule_conflicts": [],
        "summary": {"total": 1, "valid": 1, "needs_clarification": 0,
                    "incorrect": 0, "conflicting": 0, "incomplete": 0,
                    "undetermined": 0},
        "critical_issues": [], "recommended_corrections": [],
    })


def test_llm_path_accepts_valid_structured_output():
    result = analyze_with_llm(["Revenue must exceed ₹10 crore."], _FakeLLM(_llm_payload()))
    assert result["rules"][0]["status"] == "VALID"


def test_llm_path_rejects_malformed_json():
    with pytest.raises(ValueError):
        analyze_with_llm(["Revenue must exceed ₹10 crore."], _FakeLLM("not json"))


def test_llm_path_rejects_skipped_rules():
    import json
    payload = json.loads(_llm_payload())
    payload["rules"] = []
    payload["total"] = 0
    with pytest.raises(ValueError):
        analyze_with_llm(["Rule one.", "Rule two."], _FakeLLM(json.dumps(payload)))


# --- Follow-up chat -------------------------------------------------------------

def _sample_analysis():
    return analyze_rules([
        "Revenue must exceed ₹100 crore.",
        "Revenue must be below ₹50 crore.",
    ])


def test_chat_explain_rule():
    out = answer_followup(
        ["Revenue must exceed ₹100 crore.", "Revenue must be below ₹50 crore."],
        _sample_analysis(), "Why does Rule 1 conflict?",
    )
    assert "Rule 1" in out["content"]
    assert out["action"] is None


def test_chat_rewrite_rule():
    out = answer_followup(["The company must be profitable."],
                          analyze_rules(["The company must be profitable."]),
                          "Rewrite rule 1")
    assert out["content"]
    assert out["action"] is None


def test_chat_rewrite_conflicting_rule_suggests_resolution():
    out = answer_followup(
        ["Revenue must exceed ₹100 crore.", "Revenue must be below ₹50 crore."],
        _sample_analysis(), "Rewrite rule 2",
    )
    assert "Rule 1" in out["content"]
    assert out["action"] is None


def test_chat_reanalyze_action():
    out = answer_followup(["Revenue must exceed ₹10 crore."],
                          analyze_rules(["Revenue must exceed ₹10 crore."]),
                          "Analyze the revised rules again")
    assert out["action"] == "reanalyze"


def test_chat_summary():
    out = answer_followup(
        ["Revenue must exceed ₹100 crore.", "Revenue must be below ₹50 crore."],
        _sample_analysis(), "Give me a summary",
    )
    assert "2" in out["content"]
