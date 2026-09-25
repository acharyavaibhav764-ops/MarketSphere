"""
services/rule_analyzer.py — Deterministic AI Rule Analyzer engine.

Pipeline:
  raw text/file -> split_rules -> analyze_rules (per-rule + cross-rule)
  -> structured AnalysisResponse dict -> rendered by frontend/analyzer.js

Philosophy (matches MarketSphere's deterministic evaluator):
  - No LLM in the hot path: instant, offline-capable, zero hallucination.
  - EVERY input rule receives an explicit status; nothing is silently omitted.
  - Corrections are suggested only when justified by the rule text.
  - Conflicts are detected only on comparable metrics/units; rules in
    different currencies or incomparable units never "conflict".

An optional LLM path (analyze_with_llm) accepts any client exposing
chat() or generate(), mirroring services/extractor.py conventions.
"""
import json
import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

MAX_RULES = 200
MAX_RULE_CHARS = 2000

# ---------------------------------------------------------------------------
# Rule splitting
# ---------------------------------------------------------------------------

_MARKER_RE = re.compile(
    r"""^\s*(?:
        (?P<num>\d{1,3})\s*[.)\-:)]      # 1.  2)  3-  4:
      | \((?P<par>\d{1,3})\)             # (1)
      | (?P<bul>[-*•▪–])                 # bullets
    )\s+(?P<body>.+)$""",
    re.VERBOSE,
)

_HEADING_RE = re.compile(r"^\s*#{1,4}\s+(?P<body>.+)$")


def split_rules(text: str, max_rules: int = MAX_RULES) -> list[dict]:
    """Split free text into numbered candidate rules.

    Preserves numbering order, merges continuation lines into the previous
    rule, and never silently discards non-empty content.
    """
    cleaned = (text or "").replace("﻿", "")
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    rules: list[dict] = []
    current: Optional[str] = None

    def flush() -> None:
        nonlocal current
        if current and current.strip():
            rules.append({"number": len(rules) + 1, "text": current.strip()})
        current = None

    for raw_line in cleaned.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        heading = _HEADING_RE.match(line)
        if heading:
            # Headings become context for the next rule, not rules themselves.
            if current is None:
                current = heading.group("body")
            else:
                current += " " + heading.group("body")
            continue
        marker = _MARKER_RE.match(line)
        if marker:
            flush()
            current = marker.group("body").strip()
        elif current is None:
            current = line
        else:
            current += " " + line
    flush()

    # Fallback for pre-normalized text (e.g. single-line parser output):
    # split on inline numbered markers like "1. ... 2. ...".
    if len(rules) <= 1 and rules:
        inline = re.split(r"(?<!\d)(?=\b\d{1,3}[.)]\s+[A-Z0-9₹$€£\"'])", rules[0]["text"])
        inline = [p.strip() for p in inline if p.strip()]
        if len(inline) > 1:
            rules = [
                {"number": i + 1, "text": re.sub(r"^\d{1,3}[.)]\s*", "", p)}
                for i, p in enumerate(inline)
            ]
    return rules[:max_rules]


# ---------------------------------------------------------------------------
# Metric / threshold extraction
# ---------------------------------------------------------------------------

_SCALE = {
    "crore": 1e7, "crores": 1e7, "cr": 1e7,
    "lakh": 1e5, "lakhs": 1e5,
    "thousand": 1e3, "k": 1e3,
    "million": 1e6, "mn": 1e6,
    "billion": 1e9, "bn": 1e9,
}

_METRICS: dict[str, list[str]] = {
    "revenue": ["revenue", "turnover", "sales"],
    "profit": ["profit", "net income", "ebitda", "earnings", "pbt", "pat"],
    "employees": ["employee", "headcount", "staff", "worker", "workforce"],
    "capital": ["capital", "net worth", "networth", "fund"],
    "leverage": ["leverage"],
    "age": ["age"],
    "experience": ["experience"],
    "score": ["score", "marks", "percentage", "rate", "ratio", "percent"],
    "price": ["price"],
    "cost": ["cost", "expense", "expenditure"],
    "investment": ["investment"],
    "assets": ["asset"],
}

_LOWER_WORDS = (
    r"exceed(?:s|ed|ing)?|more than|greater than|above|over|at least|"
    r"minimum(?: of)?|min\.?|no less than|higher than|older than|"
    r"requir(?:e|es|ed|ing|ement)?"
)
_UPPER_WORDS = (
    r"below|less than|fewer than|under|beneath|lower than|at most|"
    r"maximum(?: of)?|max\.?|no more than|up to|capped at|cap of|"
    r"younger than|not exceed(?:ing|s)?"
)
_EQUAL_WORDS = r"exactly|equal to|equals?"

_VALUE_RE = re.compile(
    r"(?P<cur>₹|\$|€|£|Rs\.?|INR|USD)?\s*"
    r"(?P<num>\d[\d,]*(?:\.\d+)?)\s*(?P<plus>\+)?\s*"
    r"(?P<scale>crores?|cr|lakhs?|thousands?|millions?|mn|billions?|bn|[kKmM])?\b"
    r"(?P<pct>%|percent)?",
)

_BETWEEN_RE = re.compile(
    r"between\s+(?P<a>.+?)\s+and\s+(?P<b>.+?)(?:[.,;]|$)", re.IGNORECASE
)

_VAGUE_TERMS: dict[str, str] = {
    "profitable": 'specify the metric and period, e.g. "positive net income for the latest financial year"',
    "reasonable": 'define what counts as reasonable, e.g. a numeric bound or named standard',
    "reasonably": 'define what counts as reasonable, e.g. a numeric bound or named standard',
    "soon": 'state an explicit deadline, e.g. "within 30 days"',
    "adequate": 'state the required amount or level explicitly',
    "sufficient": 'state the required amount or level explicitly',
    "timely": 'state an explicit deadline, e.g. "within 30 days"',
    "promptly": 'state an explicit deadline, e.g. "within 30 days"',
    "appropriate": 'name the exact requirement instead of "appropriate"',
    "significant": 'give a numeric threshold for "significant"',
    "substantial": 'give a numeric threshold for "substantial"',
    "proper": 'describe exactly what "proper" means here',
    "satisfactory": 'define the pass criteria explicitly',
    "acceptable": 'define the acceptance criteria explicitly',
    "relevant": 'name the specific items instead of "relevant"',
    "necessary": 'list what is necessary instead of assuming it',
    "good": 'replace "good" with a measurable criterion',
    "healthy": 'replace "healthy" with a measurable criterion',
    "strong": 'replace "strong" with a measurable criterion',
    "as needed": 'state the triggering condition explicitly',
    "as required": 'state the triggering condition explicitly',
}


def _find_metric(text: str) -> Optional[str]:
    lowered = text.lower()
    for metric, keywords in _METRICS.items():
        for kw in keywords:
            if re.search(r"\b" + re.escape(kw) + r"s?\b", lowered):
                return metric
    return None


def _parse_value(match: re.Match) -> Optional[dict]:
    try:
        num = float(match.group("num").replace(",", ""))
    except (ValueError, AttributeError):
        return None
    scale_word = (match.group("scale") or "").lower()
    scale = _SCALE.get(scale_word, 1.0)
    if match.group("pct"):
        return {"value": num, "unit": "%", "currency": None}
    return {
        "value": num * scale,
        "unit": "money" if match.group("cur") or scale != 1.0 else "count",
        "currency": (match.group("cur") or "").strip() or None,
    }


def _split_numbered_clauses(text: str) -> tuple[list[dict], list[dict], list[dict]]:
    """Return (lower_bounds, upper_bounds, equalities) as value dicts."""
    lowered = text.lower()
    lowers, uppers, equals = [], [], []
    for m in _VALUE_RE.finditer(text):
        val = _parse_value(m)
        if val is None:
            continue
        window = lowered[max(0, m.start() - 40): m.start()]
        if m.start() >= 2 and lowered[m.start() - 1] == ":":
            # Ratio denominator ("1:50"): judge by the context before "N:".
            window = re.sub(r"\d+\s*:\s*$", "", window)
        after = lowered[m.end(): m.end() + 12]
        # A currency symbol may sit between the comparator and the number.
        # NOTE: word lists are wrapped in (?:...) so the end anchor applies
        # to every alternative, not just the last one.
        tail = r"\s*(?:[₹$€£]|Rs\.?)?\s*$"
        is_upper = bool(
            re.search(r"(?:" + _UPPER_WORDS + r")" + tail, window)
            or re.search(r"^\s*or (?:less|lower|fewer)", after)
        )
        is_lower = bool(
            re.search(r"(?:" + _LOWER_WORDS + r")" + tail, window)
            or re.search(r"^\s*or (?:more|higher|greater)", after)
            or (m.group("plus") and not is_upper)
        )
        if is_upper:
            uppers.append(val)
        elif is_lower:
            lowers.append(val)
        elif re.search(r"(?:" + _EQUAL_WORDS + r")" + tail, window):
            equals.append(val)
        elif re.search(r"\bmust be\b|\bshall be\b|\bis\b", window) and val["unit"] != "count":
            equals.append(val)
    return lowers, uppers, equals


def _comparable(a: dict, b: dict) -> bool:
    return a["unit"] == b["unit"] and a.get("currency") == b.get("currency")


# ---------------------------------------------------------------------------
# Per-rule analysis
# ---------------------------------------------------------------------------

def _analyze_single(number: int, text: str) -> dict:
    words = text.split()
    if len(words) < 3:
        return {
            "number": number, "original": text, "status": "UNDETERMINED",
            "explanation": "The rule contains too little content to evaluate.",
            "reasoning": ["Fewer than three words — no testable claim can be identified."],
            "missing_information": ["A complete rule statement."],
            "suggested_correction": None,
        }

    metric = _find_metric(text)
    lowers, uppers, equals = _split_numbered_clauses(text)
    lowered = text.lower()

    # 1. Self-contradiction / impossibility -> INCORRECT
    for low in lowers:
        for up in uppers:
            if _comparable(low, up) and low["value"] >= up["value"]:
                return {
                    "number": number, "original": text, "status": "INCORRECT",
                    "explanation": (
                        f"This rule contradicts itself: it requires at least "
                        f"{_fmt(low)} while also capping the same measure at "
                        f"{_fmt(up)}. Both cannot hold simultaneously."
                    ),
                    "reasoning": [
                        "Lower bound is greater than or equal to the upper bound.",
                        "No value can satisfy both conditions at once.",
                    ],
                    "missing_information": [],
                    "suggested_correction": (
                        "Revise the bounds so both can hold, e.g. lower the "
                        "minimum or raise the maximum."
                    ),
                }
    for eq in equals:
        for other in equals[1:]:
            if _comparable(eq, other) and eq["value"] != other["value"]:
                return {
                    "number": number, "original": text, "status": "INCORRECT",
                    "explanation": "This rule demands two different exact values for the same measure.",
                    "reasoning": ["Mutually exclusive equality conditions."],
                    "missing_information": [],
                    "suggested_correction": "Keep a single exact value or convert one condition into a range.",
                }
    pct_bad = any(v["unit"] == "%" and v["value"] > 100 for v in lowers + uppers + equals)
    if pct_bad:
        return {
            "number": number, "original": text, "status": "INCORRECT",
            "explanation": "The rule requires a percentage above 100%, which is impossible for a share or rate.",
            "reasoning": ["Percentages of a whole cannot exceed 100."],
            "missing_information": [],
            "suggested_correction": "Correct the percentage to a value within 0–100.",
        }
    neg_bad = any(
        v["value"] < 0 and metric in ("employees", "capital", "age", "experience")
        for v in lowers + uppers + equals
    )
    if neg_bad:
        return {
            "number": number, "original": text, "status": "INCORRECT",
            "explanation": f"A negative {metric or 'value'} is not physically meaningful.",
            "reasoning": ["Count-based measures cannot be negative."],
            "missing_information": [],
            "suggested_correction": "Use a non-negative threshold.",
        }
    between = _BETWEEN_RE.search(text)
    if between:
        a_vals = [_parse_value(m) for m in _VALUE_RE.finditer(between.group("a"))]
        b_vals = [_parse_value(m) for m in _VALUE_RE.finditer(between.group("b"))]
        a_vals = [v for v in a_vals if v]
        b_vals = [v for v in b_vals if v]
        if a_vals and b_vals and _comparable(a_vals[0], b_vals[0]) and a_vals[0]["value"] > b_vals[0]["value"]:
            return {
                "number": number, "original": text, "status": "INCORRECT",
                "explanation": "The stated range is inverted: the lower end exceeds the upper end.",
                "reasoning": [f"Range starts at {_fmt(a_vals[0])} but ends at {_fmt(b_vals[0])}."],
                "missing_information": [],
                "suggested_correction": "Swap the range ends so the smaller value comes first.",
            }

    # 2. Comparator without threshold -> INCOMPLETE
    has_comparator = bool(
        re.search(_LOWER_WORDS, lowered) or re.search(_UPPER_WORDS, lowered)
        or re.search(_EQUAL_WORDS, lowered) or re.search(r"\bbetween\b", lowered)
    )
    has_number = bool(lowers or uppers or equals)
    if has_comparator and not has_number:
        comp = "threshold" if "between" not in lowered else "range bounds"
        return {
            "number": number, "original": text, "status": "INCOMPLETE",
            "explanation": f"The rule states a comparison but gives no numeric {comp} to test against.",
            "reasoning": ["A comparison word is present with no measurable value."],
            "missing_information": [f"The numeric {comp} (value and unit)."],
            "suggested_correction": "Add the missing figure, e.g. \"... must exceed <N> <unit>\".",
        }

    # 3. Vague term without measurable threshold -> NEEDS_CLARIFICATION
    vague_hits = [t for t in _VAGUE_TERMS if re.search(r"\b" + re.escape(t) + r"\b", lowered)]
    if vague_hits and not has_number:
        term = vague_hits[0]
        return {
            "number": number, "original": text, "status": "NEEDS_CLARIFICATION",
            "explanation": (
                f"\"{term}\" is ambiguous — different readers will interpret it "
                f"differently, so compliance cannot be verified as written."
            ),
            "reasoning": [
                f"Contains the undefined term \"{term}\".",
                "No measurable threshold is given to anchor it.",
            ],
            "missing_information": [f"A precise definition of \"{term}\"."],
            "suggested_correction": f"Clarify \"{term}\": {_VAGUE_TERMS[term]}.",
        }

    # 4. Qualitative profit claim without period -> NEEDS_CLARIFICATION
    if metric == "profit" and re.search(r"\bpositive\b", lowered) and not re.search(
        r"year|annual|quarter|month|fy\d|20\d{2}", lowered
    ):
        return {
            "number": number, "original": text, "status": "NEEDS_CLARIFICATION",
            "explanation": "The profit requirement has no reporting period, so it cannot be verified.",
            "reasoning": ["Metric is directional (\"positive\") but unbounded in time."],
            "missing_information": ["The financial period the profit applies to."],
            "suggested_correction": (
                "Name the period, e.g. \"... for the latest completed financial year\"."
            ),
        }

    # 5. Measurable threshold -> VALID (note any vague modifier, don't punish it)
    if has_number:
        reasoning = ["Contains a measurable threshold that can be tested objectively."]
        if vague_hits:
            reasoning.append(
                f"Note: the modifier \"{vague_hits[0]}\" is informal — consider defining it."
            )
        return {
            "number": number, "original": text, "status": "VALID",
            "explanation": "This rule is measurable, complete, and contains no logical error.",
            "reasoning": reasoning,
            "missing_information": [],
            "suggested_correction": None,
        }

    # 6. Fallback
    return {
        "number": number, "original": text, "status": "UNDETERMINED",
        "explanation": "No testable claim could be identified in this rule as written.",
        "reasoning": ["No threshold, comparison, or verifiable condition was found."],
        "missing_information": ["A verifiable condition with a clear pass/fail criterion."],
        "suggested_correction": None,
    }


def _fmt(val: dict) -> str:
    cur = val.get("currency") or ""
    num = val["value"]
    num_s = str(int(num)) if float(num).is_integer() else f"{num:,.2f}"
    suffix = "%" if val["unit"] == "%" else ""
    return f"{cur}{num_s}{suffix}".strip()


# ---------------------------------------------------------------------------
# Cross-rule analysis
# ---------------------------------------------------------------------------

def _norm_text(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", text.lower())).strip()


def _detect_cross_rule(parsed: list[dict]) -> list[dict]:
    conflicts: list[dict] = []
    seen: dict[str, int] = {}
    n = len(parsed)

    for i in range(n):
        norm = _norm_text(parsed[i]["original"])
        if norm in seen:
            conflicts.append({
                "kind": "duplicate",
                "rules": [seen[norm], parsed[i]["number"]],
                "explanation": (
                    f"Rules {seen[norm]} and {parsed[i]['number']} are duplicates — "
                    f"they state the same requirement. Keep one and remove the other."
                ),
            })
        else:
            seen[norm] = parsed[i]["number"]

    for i in range(n):
        for j in range(i + 1, n):
            a, b = parsed[i], parsed[j]
            if a["metric"] is None or a["metric"] != b["metric"]:
                continue
            for low in a["lowers"]:
                for up in b["uppers"]:
                    if _comparable(low, up) and low["value"] >= up["value"]:
                        conflicts.append({
                            "kind": "contradiction",
                            "rules": [a["number"], b["number"]],
                            "explanation": (
                                f"Rules {a['number']} and {b['number']} conflict. "
                                f"Rule {a['number']} requires {a['metric']} of at least "
                                f"{_fmt(low)}, while Rule {b['number']} caps it at "
                                f"{_fmt(up)}. Both conditions cannot be satisfied "
                                f"simultaneously."
                            ),
                        })
            for up in a["uppers"]:
                for low in b["lowers"]:
                    if _comparable(low, up) and low["value"] >= up["value"]:
                        conflicts.append({
                            "kind": "contradiction",
                            "rules": [a["number"], b["number"]],
                            "explanation": (
                                f"Rules {a['number']} and {b['number']} conflict. "
                                f"Rule {b['number']} requires {b['metric']} of at least "
                                f"{_fmt(low)}, while Rule {a['number']} caps it at "
                                f"{_fmt(up)}. Both conditions cannot be satisfied "
                                f"simultaneously."
                            ),
                        })
            for ea in a["equals"]:
                for eb in b["equals"]:
                    if _comparable(ea, eb) and ea["value"] != eb["value"]:
                        conflicts.append({
                            "kind": "contradiction",
                            "rules": [a["number"], b["number"]],
                            "explanation": (
                                f"Rules {a['number']} and {b['number']} demand different "
                                f"exact values ({_fmt(ea)} vs {_fmt(eb)}) for {a['metric']}."
                            ),
                        })
            # Same-direction overlap (informational, not a conflict).
            same_lower = any(
                _comparable(x, y) and x["value"] != y["value"]
                for x in a["lowers"] for y in b["lowers"]
            )
            same_upper = any(
                _comparable(x, y) and x["value"] != y["value"]
                for x in a["uppers"] for y in b["uppers"]
            )
            if (same_lower or same_upper) and not any(
                c["kind"] == "contradiction"
                and set(c["rules"]) == {a["number"], b["number"]}
                for c in conflicts
            ):
                conflicts.append({
                    "kind": "overlap",
                    "rules": [a["number"], b["number"]],
                    "explanation": (
                        f"Rules {a['number']} and {b['number']} overlap on {a['metric']} — "
                        f"both constrain the same measure in the same direction. "
                        f"The stricter bound governs; consider merging them."
                    ),
                })
    return conflicts


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_rules(rules: list[str]) -> dict:
    """Analyze every rule; returns a dict matching AnalysisResponse."""
    cleaned = [(i + 1, (r or "").strip()) for i, r in enumerate(rules)]
    cleaned = [(n, t) for n, t in cleaned if t]
    if not cleaned:
        raise ValueError("No rules were provided for analysis.")

    items: list[dict] = []
    parsed: list[dict] = []
    for number, text in cleaned:
        item = _analyze_single(number, text)
        items.append(item)
        lowers, uppers, equals = _split_numbered_clauses(text)
        parsed.append({
            "number": number, "original": text, "metric": _find_metric(text),
            "lowers": lowers, "uppers": uppers, "equals": equals,
        })

    cross = _detect_cross_rule(parsed)

    # Rules in a contradiction become CONFLICTING (keeps every rule counted).
    conflicted = set()
    for c in cross:
        if c["kind"] == "contradiction":
            conflicted.update(c["rules"])
    for item in items:
        if item["number"] in conflicted and item["status"] not in ("INCORRECT",):
            item["status"] = "CONFLICTING"
            partners = sorted({
                r for c in cross
                if c["kind"] == "contradiction" and item["number"] in c["rules"]
                for r in c["rules"] if r != item["number"]
            })
            item["reasoning"] = list(item.get("reasoning") or []) + [
                f"Contradicted by Rule {p} — see Cross-Rule Conflicts." for p in partners
            ]

    summary = {
        "total": len(items), "valid": 0, "needs_clarification": 0,
        "incorrect": 0, "conflicting": 0, "incomplete": 0, "undetermined": 0,
    }
    key_map = {
        "VALID": "valid", "NEEDS_CLARIFICATION": "needs_clarification",
        "INCORRECT": "incorrect", "CONFLICTING": "conflicting",
        "INCOMPLETE": "incomplete", "UNDETERMINED": "undetermined",
    }
    for item in items:
        summary[key_map[item["status"]]] += 1

    critical: list[dict] = []
    for c in cross:
        if c["kind"] == "contradiction":
            critical.append({"text": f"Rules {c['rules'][0]} and {c['rules'][1]} conflict."})
    for item in items:
        if item["status"] == "INCORRECT":
            critical.append({"text": f"Rule {item['number']} is logically impossible as written."})
    for item in items:
        if item["status"] in ("NEEDS_CLARIFICATION", "INCOMPLETE"):
            critical.append({"text": f"Rule {item['number']} cannot be verified until clarified."})
    critical = critical[:8]

    corrections: list[str] = []
    for item in items:
        if item.get("suggested_correction") and len(corrections) < 6:
            corrections.append(f"Rule {item['number']}: {item['suggested_correction']}")

    return {
        "total": len(items),
        "rules": items,
        "cross_rule_conflicts": cross,
        "summary": summary,
        "critical_issues": critical,
        "recommended_corrections": corrections,
    }


def analyze_with_llm(rules: list[str], llm_client: Any) -> dict:
    """Optional LLM path: structured JSON via system prompt, validated."""
    from services.analyzer_prompts import ANALYZER_SYSTEM_PROMPT, build_user_prompt
    from schemas.analysis import AnalysisResponse

    cleaned = [r.strip() for r in (rules or []) if (r or "").strip()]
    if not cleaned:
        raise ValueError("No rules were provided for analysis.")

    if hasattr(llm_client, "chat"):
        response = llm_client.chat(messages=[
            {"role": "system", "content": ANALYZER_SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(cleaned)},
        ])
        if hasattr(response, "message") and hasattr(response.message, "content"):
            raw = response.message.content
        elif isinstance(response, dict):
            raw = response.get("message", {}).get("content") or response.get("content", "")
        else:
            raw = str(response)
    elif hasattr(llm_client, "generate"):
        raw = llm_client.generate(
            prompt=build_user_prompt(cleaned), system=ANALYZER_SYSTEM_PROMPT
        )
    else:
        raise TypeError(f"Unsupported LLM client type: {type(llm_client)}")

    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM returned malformed JSON: {exc}") from exc

    validated = AnalysisResponse(**data)  # raises on schema violation
    if len(validated.rules) != len(cleaned):
        raise ValueError(
            f"LLM analyzed {len(validated.rules)} of {len(cleaned)} rules — "
            "every rule must be analyzed."
        )
    return validated.model_dump()


# ---------------------------------------------------------------------------
# Context-aware follow-up chat (deterministic)
# ---------------------------------------------------------------------------

_RULE_REF_RE = re.compile(r"rule\s*(\d+)", re.IGNORECASE)


def answer_followup(
    rules: list[str],
    analysis: Optional[dict],
    question: str,
) -> dict:
    """Answer a follow-up about the current rule set and analysis context."""
    q = (question or "").strip()
    ql = q.lower()
    total = len([r for r in (rules or []) if (r or "").strip()])
    ref = _RULE_REF_RE.search(ql)
    num = int(ref.group(1)) if ref else None
    by_number = {}
    if isinstance(analysis, dict):
        for item in analysis.get("rules", []):
            by_number[item.get("number")] = item

    def rule_block(n: int) -> str:
        item = by_number.get(n)
        if not item:
            return f"I don't have an analysis for Rule {n}."
        lines = [
            f"### Rule {n} — {item.get('status', '').replace('_', ' ')}",
            "",
            f"> \"{item.get('original', '')}\"",
            "",
            item.get("explanation", ""),
        ]
        if item.get("suggested_correction"):
            lines += ["", f"**Suggested correction:** {item['suggested_correction']}"]
        return "\n".join(lines)

    if re.search(r"re-?analy|re-?evaluat|analy[sz]e again|revised|updated rules", ql):
        return {
            "content": (
                f"Re-running analysis on the current {total} rule(s). "
                f"Edit the rules above if needed, then I'll produce a fresh verdict."
            ),
            "action": "reanalyze",
        }
    if num is not None and re.search(r"rewrite|fix|correct|improve|rephrase", ql):
        item = by_number.get(num)
        if item and item.get("suggested_correction"):
            return {
                "content": f"Here's a corrected version of **Rule {num}**:\n\n{item['suggested_correction']}",
                "action": None,
            }
        if item and item.get("status") == "VALID":
            return {
                "content": f"Rule {num} is already **VALID** — no rewrite needed:\n\n> \"{item.get('original', '')}\"",
                "action": None,
            }
        if item and item.get("status") == "CONFLICTING" and isinstance(analysis, dict):
            for c in analysis.get("cross_rule_conflicts", []):
                if c.get("kind") == "contradiction" and num in c.get("rules", []):
                    partner = next(r for r in c["rules"] if r != num)
                    partner_text = (by_number.get(partner) or {}).get("original", "")
                    return {
                        "content": (
                            f"To resolve the conflict, change **Rule {num}** so it no "
                            f"longer contradicts **Rule {partner}**:\n\n"
                            f"> \"{partner_text}\"\n\n"
                            f"**Conflict:** {c.get('explanation', '')}\n\n"
                            f"**Suggested rewrite:** align Rule {num}'s bound with Rule "
                            f"{partner}'s requirement — e.g. raise the cap or lower the "
                            f"minimum so a single value can satisfy both rules, then "
                            f"ask me to re-analyze."
                        ),
                        "action": None,
                    }
        return {"content": rule_block(num), "action": None}
    if num is not None and re.search(r"why|explain|conflict|reason|meaning", ql):
        extra = ""
        if isinstance(analysis, dict):
            for c in analysis.get("cross_rule_conflicts", []):
                if num in c.get("rules", []):
                    extra += f"\n\n**Cross-rule note:** {c.get('explanation', '')}"
        return {"content": rule_block(num) + extra, "action": None}
    if num is not None:
        return {"content": rule_block(num), "action": None}
    if re.search(r"conflict|contradic", ql):
        if isinstance(analysis, dict) and analysis.get("cross_rule_conflicts"):
            lines = ["### Cross-Rule Conflicts", ""]
            for c in analysis["cross_rule_conflicts"]:
                lines.append(f"- **Rules {c['rules'][0]} & {c['rules'][1]}** ({c.get('kind', '')}): {c.get('explanation', '')}")
            return {"content": "\n".join(lines), "action": None}
        return {"content": "No cross-rule conflicts were detected in the current rule set.", "action": None}
    if re.search(r"duplicate|overlap", ql):
        if isinstance(analysis, dict):
            dups = [c for c in analysis.get("cross_rule_conflicts", []) if c.get("kind") in ("duplicate", "overlap")]
            if dups:
                lines = ["### Duplicates & Overlaps", ""]
                for c in dups:
                    lines.append(f"- **Rules {c['rules'][0]} & {c['rules'][1]}** ({c.get('kind', '')}): {c.get('explanation', '')}")
                return {"content": "\n".join(lines), "action": None}
        return {"content": "No duplicates or overlaps were detected.", "action": None}
    if re.search(r"\bvalid\b", ql):
        if isinstance(analysis, dict):
            ok = [r for r in analysis.get("rules", []) if r.get("status") == "VALID"]
            if ok:
                return {"content": "**Valid rules:** " + ", ".join(f"Rule {r['number']}" for r in ok) + ".", "action": None}
        return {"content": "Run an analysis first, then ask me which rules are valid.", "action": None}
    if re.search(r"summar|overview|result", ql):
        if isinstance(analysis, dict):
            s = analysis.get("summary", {})
            return {
                "content": (
                    f"**Analysis summary — {s.get('total', total)} rules:** "
                    f"{s.get('valid', 0)} valid, {s.get('needs_clarification', 0)} need clarification, "
                    f"{s.get('incorrect', 0)} incorrect, {s.get('conflicting', 0)} conflicting, "
                    f"{s.get('incomplete', 0)} incomplete, {s.get('undetermined', 0)} undetermined."
                ),
                "action": None,
            }
        return {"content": "Run an analysis first, then I'll summarize it.", "action": None}
    if re.search(r"^(hi|hello|hey|thanks|thank you)\b", ql):
        return {
            "content": (
                f"Hello! I'm tracking **{total} rule(s)** with their latest analysis. "
                f"Ask me things like *\"Why does Rule 2 conflict?\"* or *\"Rewrite Rule 3\"*."
            ),
            "action": None,
        }
    # Default: contextual overview.
    if isinstance(analysis, dict):
        s = analysis.get("summary", {})
        crit = analysis.get("critical_issues", [])
        lines = [
            f"I'm tracking **{s.get('total', total)} rule(s)** — "
            f"{s.get('valid', 0)} valid, {s.get('incorrect', 0)} incorrect, "
            f"{s.get('conflicting', 0)} conflicting.",
        ]
        if crit:
            lines.append("")
            lines.append(f"Top issue: {crit[0].get('text', '')}")
        lines.append("")
        lines.append("Try: *\"Explain Rule 1\"* · *\"Rewrite Rule 2\"* · *\"Show conflicts\"* · *\"Re-analyze\"*.")
        return {"content": "\n".join(lines), "action": None}
    return {
        "content": (
            "Analyze your rules first, then I can explain any rule, rewrite "
            "problematic ones, or walk through the conflicts."
        ),
        "action": None,
    }
