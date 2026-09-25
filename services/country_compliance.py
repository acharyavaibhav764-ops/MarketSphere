"""
services/country_compliance.py — Country-specific compliance analysis engine.

Pipeline:
  user rules + selected country
    -> match each rule against APPROVED country requirements (rule store)
    -> classify (COMPLIANT / PARTIALLY / NON-COMPLIANT / GAP / CONFLICT ...)
    -> severity-weighted compatibility score (transparent methodology)
    -> grounded report with regulator sources, dates, required actions

Ground rules (never violated):
  - Only approved requirements are used. Drafts do not exist for analysis.
  - No identified requirement  =>  UNDETERMINED, never a guessed verdict.
  - Missing applicability context  =>  explicitly requested, never assumed.
  - Scores are severity-weighted with a published methodology, not raw ratios.
  - Findings cite the actual source record (authority/title/date/evidence).
"""
import datetime
import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

MAX_RULES = 200
MAX_RULE_CHARS = 2000

SEVERITY_PENALTY = {"CRITICAL": 25, "HIGH": 15, "MEDIUM": 8, "LOW": 3}
PARTIAL_PENALTY = 4

SCORE_METHODOLOGY = (
    "Compatibility starts at 100. Each non-compliant finding subtracts a "
    "severity weight (CRITICAL 25, HIGH 15, MEDIUM 8, LOW 3); each partially "
    "compliant rule subtracts 4. Undetermined rules never subtract — they are "
    "listed under Information required instead. Score = max(0, 100 - penalties)."
)

# ---------------------------------------------------------------------------
# Topic taxonomy: user-rule keywords -> requirement topics
# ---------------------------------------------------------------------------

_TOPIC_KEYWORDS: dict[str, list[str]] = {
    "capital": ["capital", "paid-up", "paid up", "net worth", "minimum investment"],
    "leverage": ["leverage", "margin", "gearing"],
    "license": ["license", "licence", "permit", "authoriz", "operating approval"],
    "certification": ["certif"],
    "registration": ["regist"],
    "documentation": ["document", "record-keeping", "records", "customs declaration"],
    "tax": ["tax", "duty", "duties", "tariff", "tribut", "imposto", "icms"],
    "presence": ["office", "branch", "subsidiar", "director", "local presence",
                 "representative", "establishment"],
    "restriction": ["prohibit", "ban", "restrict", "forbidden", "not permitted"],
}

# Severity per topic for genuine violations (capped when evidence is weak).
_TOPIC_SEVERITY: dict[str, str] = {
    "license": "CRITICAL",
    "registration": "CRITICAL",
    "capital": "CRITICAL",
    "tax": "HIGH",
    "leverage": "HIGH",
    "presence": "HIGH",
    "certification": "HIGH",
    "restriction": "HIGH",
    "documentation": "MEDIUM",
}

_GAP_WHY: dict[str, str] = {
    "capital": "Operating below the statutory capital floor can block authorization.",
    "leverage": "Offering leverage above the retail cap breaches product rules.",
    "license": "Operating without a required license can halt the operation.",
    "certification": "Missing mandatory certification can block market access.",
    "registration": "Missing mandatory registration can block the operation.",
    "documentation": "Incomplete documentation causes clearance and audit failures.",
    "tax": "Unaddressed tax obligations create clearance holds and penalties.",
    "presence": "Unmet local-presence mandates can invalidate authorization.",
    "restriction": "Ignoring product restrictions risks seizure or prohibition.",
}

_KNOWN_JURISDICTIONS = [
    "United States", "United Kingdom", "Singapore", "Australia", "Switzerland",
    "Hong Kong", "Japan", "India", "United Arab Emirates", "Canada", "France",
    "Germany", "Netherlands", "South Korea", "Brazil",
]


def detect_topics(text: str) -> list[str]:
    lowered = text.lower()
    found = []
    for topic, keywords in _TOPIC_KEYWORDS.items():
        for kw in keywords:
            if re.search(r"\b" + re.escape(kw), lowered):
                found.append(topic)
                break
    return found


def _negates(text: str, keywords: list[str]) -> bool:
    """Does the rule explicitly waive a requirement (no X / without X / X not required)?"""
    lowered = text.lower()
    for kw in keywords:
        stem = re.escape(kw.rstrip("*"))
        if re.search(r"\bno\b[^.]{0,30}" + stem, lowered):
            return True
        if re.search(r"\bwithout\b[^.]{0,30}" + stem, lowered):
            return True
        if re.search(stem + r"[^.]{0,30}\bnot required\b", lowered):
            return True
        if re.search(stem + r"[^.]{0,30}\bis not needed\b", lowered):
            return True
    return False


# ---------------------------------------------------------------------------
# Requirement access (ORM-agnostic)
# ---------------------------------------------------------------------------

def _req_text(req: Any) -> str:
    data = getattr(req, "rule_data", {}) or {}
    return (
        data.get("obligation_or_restriction")
        or data.get("obligation")
        or getattr(req, "topic", "")
        or ""
    )


def _req_quote(req: Any) -> str:
    data = getattr(req, "rule_data", {}) or {}
    return data.get("supporting_quote", "") or ""


def _req_matches_topic(req: Any, topic: str) -> bool:
    if (getattr(req, "topic", "") or "").lower() == topic:
        return True
    haystack = f"{_req_text(req)} {_req_quote(req)}".lower()
    return any(
        re.search(r"\b" + re.escape(kw.rstrip("*")), haystack)
        for kw in _TOPIC_KEYWORDS.get(topic, [])
    )


def _requirement_statement(req: Any) -> str:
    regulator = getattr(req, "regulator", "") or "The regulator"
    obligation = _req_text(req)
    bits = [f"{regulator} requires: {obligation}" if obligation else f"{regulator} requirement applies."]
    cap = getattr(req, "leverage_cap", None)
    if cap:
        bits.append(f"Statutory retail cap: {cap}.")
    floor = getattr(req, "required_capital", None)
    if floor is not None:
        try:
            bits.append(f"Statutory capital floor: USD {float(floor):,.0f}.")
        except (TypeError, ValueError):
            pass
    return " ".join(bits)


def _evidence_for(req: Any, source_map: dict) -> dict:
    source = source_map.get(getattr(req, "source_id", "")) if source_map else None
    tag = getattr(req, "evidence_tag", None)
    reviewed = getattr(req, "reviewed_at", None)
    date_str = ""
    try:
        date_str = reviewed.isoformat()[:10] if reviewed else ""
    except AttributeError:
        date_str = str(reviewed) if reviewed else ""
    if source is not None:
        return {
            "authority": getattr(source, "regulator", "") or getattr(req, "regulator", ""),
            "title": getattr(source, "title", "") or "",
            "url": getattr(source, "source_url", None),
            "reviewed_at": date_str,
            "evidence_tag": tag,
            "verified": tag == "Verified Fact",
        }
    return {
        "authority": getattr(req, "regulator", ""),
        "title": "",
        "url": None,
        "reviewed_at": date_str,
        "evidence_tag": tag,
        "verified": tag == "Verified Fact",
    }


def _severity_for(topic: str, verified: bool) -> str:
    sev = _TOPIC_SEVERITY.get(topic, "MEDIUM")
    if not verified and sev in ("CRITICAL", "HIGH"):
        return "MEDIUM"
    return sev


# ---------------------------------------------------------------------------
# Numeric comparison (reuses proven parsers)
# ---------------------------------------------------------------------------

def _parse_ratio(text: Optional[str]) -> Optional[int]:
    if not text or not isinstance(text, str):
        return None
    parts = text.strip().split(":")
    if len(parts) == 2:
        try:
            return int(parts[1])
        except ValueError:
            return None
    return None


_NON_USD_CURRENCIES = [
    "sgd", "eur", "gbp", "jpy", "brl", "krw", "cad", "aud", "chf", "hkd",
    "cny", "inr", "aed", "sek", "nok", "dkk", "nzd", "zar", "mxn",
]


def _compare_leverage(user_text: str, cap: str) -> Optional[str]:
    """'satisfies' | 'breaches' | None (no user figure to test)."""
    from services.rule_analyzer import _split_numbered_clauses

    lowers, uppers, _ = _split_numbered_clauses(user_text)
    cap_ratio = _parse_ratio(cap)
    if cap_ratio is None:
        return None
    offered = [v["value"] for v in lowers + uppers if v["unit"] != "%"]
    if not offered:
        # Bare statement ("we offer 1:30") names the offered ratio outright.
        bare = re.search(r"\b1\s*:\s*(\d+)", user_text)
        if bare:
            offered = [float(bare.group(1))]
    if not offered:
        return None
    offered_ratio = max(offered)
    return "breaches" if offered_ratio > cap_ratio else "satisfies"


def _compare_capital(user_text: str, floor: float) -> Optional[str]:
    from services.rule_analyzer import _split_numbered_clauses, _find_metric

    lowered = user_text.lower()
    if any(re.search(r"\b" + cur + r"\b", lowered) for cur in _NON_USD_CURRENCIES):
        # Never convert foreign currency by assumption — request confirmation.
        return None
    if _find_metric(user_text) not in ("capital", "investment", None):
        # Only compare when the rule is plausibly about funds.
        if _find_metric(user_text) not in (None, "capital", "investment", "assets"):
            return None
    lowers, uppers, equals = _split_numbered_clauses(user_text)
    candidates = [
        v["value"] for v in lowers + uppers + equals
        if v["unit"] == "money" and v["value"] >= 1000
    ]
    if not candidates:
        return None
    return "breaches" if min(candidates) < float(floor) else "satisfies"


# ---------------------------------------------------------------------------
# Per-rule verdicts
# ---------------------------------------------------------------------------

def _classify_rule(
    number: int,
    text: str,
    country: str,
    approved: list,
    source_map: dict,
) -> tuple[dict, list]:
    """Returns (rule_result_dict, matched_requirements)."""
    topics = detect_topics(text)
    lowered = text.lower()

    # Explicit out-of-scope: rule names a different jurisdiction.
    for other in _KNOWN_JURISDICTIONS:
        if other.lower() != country.lower() and other.lower() in lowered:
            return ({
                "id": number, "user_rule": text, "status": "NOT_APPLICABLE",
                "severity": None,
                "country_requirement": None,
                "explanation": (
                    f"This rule is scoped to {other}, not {country}, so it was "
                    f"excluded from the {country} compatibility calculation."
                ),
                "required_action": None,
                "missing_information": [],
                "sources": [],
            }, [])

    matched: list[tuple[Any, str]] = []
    for req in approved:
        for topic in topics:
            if _req_matches_topic(req, topic):
                matched.append((req, topic))
                break

    if not matched:
        needed = []
        if topics:
            needed.append(
                f"An identified {country} requirement on: {', '.join(topics)} "
                f"(none found in the current store)."
            )
        else:
            needed.append("A requirement topic this rule can be checked against.")
        needed.append("Product and operation context (see Information required).")
        return ({
            "id": number, "user_rule": text, "status": "UNDETERMINED",
            "severity": None,
            "country_requirement": None,
            "explanation": (
                f"Cannot determine applicability: MarketSphere holds no identified "
                f"{country} requirement matching this rule, so no verdict was guessed."
            ),
            "required_action": None,
            "missing_information": needed,
            "sources": [],
        }, [])

    # Evaluate against every matched requirement; worst verdict wins.
    verdict_rank = {"COMPLIANT": 0, "PARTIALLY_COMPLIANT": 1, "NON_COMPLIANT": 2}
    best = {"status": "COMPLIANT"}
    sources: list[dict] = []
    seen_src: set[str] = set()
    req_texts: list[str] = []
    actions: list[str] = []
    missing: list[str] = []
    explanations: list[str] = []
    worst_topic = ""
    worst_verified = True

    for req, topic in matched:
        statement = _requirement_statement(req)
        if statement not in req_texts:
            req_texts.append(statement)
        ev = _evidence_for(req, source_map)
        key = (ev["authority"], ev["title"])
        if key not in seen_src:
            seen_src.add(key)
            sources.append(ev)

        status = "COMPLIANT"
        reason = ""
        action = None
        need: list[str] = []

        kws = _TOPIC_KEYWORDS[topic]
        if _negates(text, kws):
            status = "NON_COMPLIANT"
            reason = (
                f"The rule waives a {topic} obligation that applies in {country}: "
                f"{statement}"
            )
            action = f"Remove the waiver and satisfy the {topic} requirement before proceeding."
        elif topic == "leverage" and getattr(req, "leverage_cap", None):
            cmp = _compare_leverage(text, req.leverage_cap)
            if cmp == "breaches":
                status = "NON_COMPLIANT"
                reason = (
                    f"Offered leverage exceeds the statutory cap of {req.leverage_cap}: "
                    f"{statement}"
                )
                action = f"Reduce offered leverage to within {req.leverage_cap}."
            elif cmp == "satisfies":
                reason = f"Offered leverage sits within the statutory cap of {req.leverage_cap}."
            else:
                status = "PARTIALLY_COMPLIANT"
                reason = (
                    f"The rule addresses leverage but states no figure to test against "
                    f"the {req.leverage_cap} cap."
                )
                need.append("The offered leverage ratio (e.g. 1:20).")
                action = f"State the offered leverage so it can be checked against {req.leverage_cap}."
        elif topic == "capital" and getattr(req, "required_capital", None) is not None:
            cmp = _compare_capital(text, req.required_capital)
            if cmp == "breaches":
                try:
                    floor_s = f"USD {float(req.required_capital):,.0f}"
                except (TypeError, ValueError):
                    floor_s = str(req.required_capital)
                status = "NON_COMPLIANT"
                reason = f"Stated capital is below the statutory floor of {floor_s}: {statement}"
                action = f"Raise committed capital to at least {floor_s}."
            elif cmp == "satisfies":
                reason = "Stated capital meets the statutory floor."
            else:
                status = "PARTIALLY_COMPLIANT"
                if any(re.search(r"\b" + cur + r"\b", text.lower()) for cur in _NON_USD_CURRENCIES):
                    reason = (
                        "The rule states capital in a foreign currency, which is not "
                        "converted by assumption."
                    )
                    need.append("USD-equivalent of the stated capital (or confirmation it clears the floor).")
                    action = "Confirm the USD-equivalent clears the statutory floor."
                else:
                    reason = "The rule addresses capital but states no amount to test."
                    need.append("The committed capital amount in USD.")
                    action = "State the committed capital amount."
        elif topic in ("license", "certification", "registration"):
            # Affirmation without mechanism => partially compliant.
            if re.search(r"\b(must|shall|will|required|obtain|hold|maintain)\b", lowered):
                status = "PARTIALLY_COMPLIANT"
                reason = (
                    f"The rule correctly identifies the {topic} obligation but does not "
                    f"specify the applicable mechanism."
                )
                need.append(f"The applicable {topic} mechanism/authority.")
                action = f"Name the applicable {topic} mechanism and reference: {statement}"
            else:
                status = "PARTIALLY_COMPLIANT"
                reason = f"The rule touches on {topic} without a verifiable commitment."
                need.append(f"What exactly is committed for {topic}.")
                action = f"Convert this into a verifiable commitment consistent with: {statement}"
        elif topic == "presence":
            if re.search(r"\b(will|shall|must|maintain|establish|appoint)\b", lowered) and not _negates(text, kws):
                reason = "The rule commits to the required local presence."
            else:
                status = "PARTIALLY_COMPLIANT"
                reason = "Local presence is mentioned without a concrete commitment."
                need.append("The concrete presence commitment (office, directors).")
                action = f"Commit explicitly: {statement}"
        else:  # documentation / tax / restriction: affirmation counts when specific-ish
            if re.search(r"\b\d\b|%|must\s+(pay|file|submit|provide|maintain)\b", lowered):
                reason = f"The rule addresses {topic} consistently with: {statement}"
            else:
                status = "PARTIALLY_COMPLIANT"
                reason = f"The rule mentions {topic} without verifiable detail."
                need.append(f"The concrete {topic} figures or steps.")
                action = f"Add verifiable detail consistent with: {statement}"

        if not ev.get("verified") and status == "NON_COMPLIANT":
            reason += " (Supporting evidence is not yet verified — treat as provisional.)"

        if verdict_rank[status] > verdict_rank[best["status"]]:
            best = {"status": status}
            worst_topic = topic
            worst_verified = ev.get("verified", False)
        explanations.append(reason)
        if action and action not in actions:
            actions.append(action)
        for n in need:
            if n not in missing:
                missing.append(n)

    final_status = best["status"]
    severity = None
    if final_status == "NON_COMPLIANT":
        severity = _severity_for(worst_topic, worst_verified)

    explanation = " ".join(e for e in explanations if e)
    return ({
        "id": number, "user_rule": text, "status": final_status,
        "severity": severity,
        "country_requirement": " ".join(req_texts) if req_texts else None,
        "explanation": explanation,
        "required_action": actions[0] if actions else None,
        "missing_information": missing,
        "sources": sources,
    }, [r for r, _ in matched])


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------

def _label_for(score: int, has_requirements: bool = True) -> str:
    if not has_requirements:
        return "Insufficient data"
    if score >= 90:
        return "Highly compatible"
    if score >= 70:
        return "Mostly compatible"
    if score >= 50:
        return "Partially compatible"
    if score >= 30:
        return "Low compatibility"
    return "At risk"


def analyze_country_compliance(
    country: str,
    user_rules: list,
    approved_requirements: list,
    source_map: Optional[dict] = None,
    context: Optional[dict] = None,
    analysis_date: Optional[str] = None,
) -> dict:
    cleaned = [(i + 1, (r or "").strip()) for i, r in enumerate(user_rules or [])]
    cleaned = [(n, t) for n, t in cleaned if t]
    if not cleaned:
        raise ValueError("No rules were provided for analysis.")
    if len(cleaned) > MAX_RULES:
        raise ValueError(f"Too many rules ({len(cleaned)}). The limit is {MAX_RULES}.")
    too_long = [n for n, t in cleaned if len(t) > MAX_RULE_CHARS]
    if too_long:
        raise ValueError(f"Rule(s) {too_long} exceed {MAX_RULE_CHARS} characters.")

    country = (country or "").strip()
    if not country:
        raise ValueError("A country is required for compliance analysis.")
    context = dict(context or {})
    source_map = source_map or {}
    date_str = analysis_date or datetime.date.today().isoformat()

    results: list[dict] = []
    covered_req_ids: set[str] = set()
    for number, text in cleaned:
        item, matched_reqs = _classify_rule(number, text, country, approved_requirements, source_map)
        results.append(item)
        for req in matched_reqs:
            covered_req_ids.add(getattr(req, "rule_id", ""))

    # Internal user-rule conflicts (metric contradictions), reused detector.
    conflicts: list[dict] = []
    internal = _detect_internal_conflicts(cleaned)
    for rules_pair, explanation in internal:
        conflicts.append({
            "kind": "internal", "rules": list(rules_pair),
            "explanation": explanation, "sources": [],
        })

    # Regulatory conflicts: non-compliant rules contradicting requirements.
    for item in results:
        if item["status"] == "NON_COMPLIANT" and item.get("country_requirement"):
            conflicts.append({
                "kind": "regulatory", "rules": [item["id"]],
                "explanation": (
                    f"Rule {item['id']} conflicts with the {country} requirement: "
                    f"{item['country_requirement']}"
                ),
                "sources": item.get("sources", []),
            })

    # Violations (with severity), required actions, gaps.
    violations: list[dict] = []
    required_actions: list[str] = []
    for item in results:
        if item["status"] == "NON_COMPLIANT":
            violations.append({
                "rule_id": item["id"],
                "severity": item.get("severity") or "MEDIUM",
                "user_rule": item["user_rule"],
                "country_requirement": item.get("country_requirement") or "",
                "explanation": item.get("explanation") or "",
                "required_action": item.get("required_action") or "",
                "sources": item.get("sources", []),
            })
            if item.get("required_action"):
                act = f"Rule {item['id']}: {item['required_action']}"
                if act not in required_actions:
                    required_actions.append(act)

    gaps: list[dict] = []
    for req in approved_requirements:
        rid = getattr(req, "rule_id", "")
        if rid and rid in covered_req_ids:
            continue
        topic = (getattr(req, "topic", "") or "general").lower()
        gaps.append({
            "topic": topic,
            "requirement": _requirement_statement(req),
            "why_it_matters": _GAP_WHY.get(
                topic, "The requirement applies but the user's rules never address it."),
            "sources": [_evidence_for(req, source_map)],
        })
        if len(gaps) >= 6:
            break
    for g in gaps:
        act = f"Address missing requirement ({g['topic']}): {g['requirement']}"
        if act not in required_actions:
            required_actions.append(act)

    # Missing information: per-rule needs + context triggers.
    missing: list[str] = []
    for item in results:
        for need in item.get("missing_information", []):
            if need not in missing:
                missing.append(need)
    rule_topics = set()
    for _, text in cleaned:
        rule_topics.update(detect_topics(text))
    ctx_product = (context.get("product") or "").strip()
    ctx_ncm = (context.get("ncm") or "").strip()
    ctx_op = (context.get("operation") or "").strip()
    ctx_dest = (context.get("destination") or "").strip()
    if rule_topics & {"license", "certification", "registration", "tax"}:
        if not ctx_product:
            missing.append("Product description (needed to pin down which authorizations apply).")
        if not ctx_ncm:
            missing.append("Product NCM/HS classification (treatment can depend on classification).")
    if rule_topics & {"tax"} and not ctx_dest:
        missing.append("Destination state/region (tax treatment can vary by destination).")
    blob = " ".join(t for _, t in cleaned).lower()
    if re.search(r"\bimport\b|\bexport\b", blob) and not ctx_op:
        missing.append("Operation type (import / export / domestic).")
    missing = missing[:8]

    # Score (severity-weighted, transparent).
    penalty = 0
    for v in violations:
        penalty += SEVERITY_PENALTY.get(v["severity"], 8)
    penalty += PARTIAL_PENALTY * sum(1 for i in results if i["status"] == "PARTIALLY_COMPLIANT")
    score = max(0, 100 - penalty)
    methodology = SCORE_METHODOLOGY
    if not approved_requirements:
        # No identified requirements: a numeric score would mislead.
        score = 0
        missing.append(
            f"No approved requirements for {country} exist in the current store — "
            f"add and approve requirements before a compatibility score is meaningful."
        )
        missing = missing[:8]
        methodology += (
            " No approved requirements were identified for this country, so every "
            "rule is UNDETERMINED and the score is withheld (shown as 0)."
        )

    summary = {
        "total_rules": len(results),
        "compliant": sum(1 for i in results if i["status"] == "COMPLIANT"),
        "partially_compliant": sum(1 for i in results if i["status"] == "PARTIALLY_COMPLIANT"),
        "non_compliant": sum(1 for i in results if i["status"] == "NON_COMPLIANT"),
        "undetermined": sum(1 for i in results if i["status"] in ("UNDETERMINED", "NOT_APPLICABLE", "MISSING_REQUIREMENT", "CONTRADICTORY")),
    }

    # Dedupe sources across the report.
    all_sources: list[dict] = []
    seen: set[tuple] = set()
    for item in results:
        for s in item.get("sources", []):
            key = (s.get("authority"), s.get("title"))
            if key not in seen:
                seen.add(key)
                all_sources.append(s)

    return {
        "country": country,
        "analysis_date": date_str,
        "context": {
            "product": context.get("product"),
            "operation": context.get("operation"),
            "ncm": context.get("ncm"),
            "destination": context.get("destination"),
            "origin": context.get("origin"),
            "industry": context.get("industry"),
        },
        "compatibility": {
            "score": score,
            "label": _label_for(score, bool(approved_requirements)),
            "methodology": methodology,
        },
        "summary": summary,
        "rules": results,
        "violations": violations,
        "gaps": gaps,
        "conflicts": conflicts,
        "missing_information": missing,
        "required_actions": required_actions[:8],
        "sources": all_sources,
    }


def _detect_internal_conflicts(cleaned: list) -> list:
    """Reuse the metric-contradiction detector for user↔user conflicts."""
    from services import rule_analyzer as ra

    parsed = []
    for number, text in cleaned:
        lowers, uppers, equals = ra._split_numbered_clauses(text)
        parsed.append({
            "number": number, "original": text,
            "metric": ra._find_metric(text),
            "lowers": lowers, "uppers": uppers, "equals": equals,
        })
    out = []
    for entry in ra._detect_cross_rule(parsed):
        if entry.get("kind") == "contradiction":
            out.append((entry["rules"], entry["explanation"]))
    return out


# ---------------------------------------------------------------------------
# Follow-up chat over the report context
# ---------------------------------------------------------------------------

_RULE_REF_RE = re.compile(r"rule\s*(\d+)", re.IGNORECASE)


def answer_compliance_question(
    country: str,
    rules: list,
    report: Optional[dict],
    context: Optional[dict],
    question: str,
) -> dict:
    q = (question or "").strip()
    ql = q.lower()
    total = len([r for r in (rules or []) if (r or "").strip()])
    ref = _RULE_REF_RE.search(ql)
    num = int(ref.group(1)) if ref else None
    by_id = {}
    if isinstance(report, dict):
        for item in report.get("rules", []):
            by_id[item.get("id")] = item

    def rule_detail(n: int) -> str:
        item = by_id.get(n)
        if not item:
            return f"I don't have a finding for Rule {n} in this {country} report."
        lines = [
            f"### Rule {n:02d} — {item.get('status', '').replace('_', ' ')}",
            "",
            f"User rule: \"{item.get('user_rule', '')}\"",
            "",
        ]
        if item.get("country_requirement"):
            lines += [f"**{country} requirement:** {item['country_requirement']}", ""]
        lines.append(item.get("explanation", ""))
        if item.get("required_action"):
            lines += ["", f"**Required action:** {item['required_action']}"]
        if item.get("missing_information"):
            lines += ["", "**Still needed:** " + "; ".join(item["missing_information"])]
        return "\n".join(lines)

    if re.search(r"re-?analy|re-?calculat|re-?evaluat|revised|updated rules|changing rule", ql):
        return {
            "content": (
                f"Re-running the {country} compatibility analysis on the current "
                f"{total} rule(s). Edit the rules above if needed — I'll produce a fresh report."
            ),
            "action": "reanalyze",
        }
    if num is not None and re.search(r"why|explain|reason|non-?compliant|violat", ql):
        return {"content": rule_detail(num), "action": None}
    if num is not None and re.search(r"rewrite|fix|correct|improve|change|update", ql):
        item = by_id.get(num)
        if item and item.get("required_action"):
            return {
                "content": f"**To fix Rule {num}:** {item['required_action']}",
                "action": None,
            }
        return {"content": rule_detail(num), "action": None}
    if num is not None and re.search(r"source|citation|evidence|proof", ql):
        item = by_id.get(num)
        if item and item.get("sources"):
            lines = [f"### Sources for Rule {num}", ""]
            for s in item["sources"]:
                line = f"- **{s.get('authority', 'Unknown authority')}** — {s.get('title', '')}"
                if s.get("reviewed_at"):
                    line += f" (reviewed {s['reviewed_at']})"
                if s.get("url"):
                    line += f" — [View official source]({s['url']})"
                if not s.get("verified"):
                    line += " — UNVERIFIED"
                lines.append(line)
            return {"content": "\n".join(lines), "action": None}
        return {"content": f"No verified source is attached to Rule {num} — its finding is UNDETERMINED.", "action": None}
    if num is not None:
        return {"content": rule_detail(num), "action": None}
    if re.search(r"critical|violations? only|what('| i)s wrong|show .*violat", ql):
        if isinstance(report, dict) and report.get("violations"):
            lines = ["### Violations", ""]
            for v in report["violations"]:
                if "critical" in ql and v.get("severity") != "CRITICAL":
                    continue
                lines.append(
                    f"- **Rule {v['rule_id']}** ({v.get('severity', '')}): {v.get('explanation', '')}"
                )
            if len(lines) == 2:
                return {"content": "No critical violations in this report.", "action": None}
            return {"content": "\n".join(lines), "action": None}
        return {"content": f"No violations were found against the identified {country} requirements.", "action": None}
    if re.search(r"missing|gap|information.*(need|require|missing)|what.*missing", ql):
        if isinstance(report, dict) and (report.get("missing_information") or report.get("gaps")):
            lines = ["### Information required", ""]
            for need in report.get("missing_information", []):
                lines.append(f"- {need}")
            if report.get("gaps"):
                lines.append("")
                lines.append("**Unaddressed requirements (gaps):**")
                for g in report["gaps"]:
                    lines.append(f"- {g.get('topic', '')}: {g.get('requirement', '')}")
            return {"content": "\n".join(lines), "action": None}
        return {"content": "No additional information is currently required.", "action": None}
    if re.search(r"partial", ql):
        if isinstance(report, dict):
            partial = [r for r in report.get("rules", []) if r.get("status") == "PARTIALLY_COMPLIANT"]
            if partial:
                return {
                    "content": "**Partially compliant:** " + ", ".join(f"Rule {r['id']}" for r in partial) + ".",
                    "action": None,
                }
        return {"content": "No partially compliant rules in this report.", "action": None}
    if re.search(r"source", ql):
        if isinstance(report, dict) and report.get("sources"):
            lines = ["### Report sources", ""]
            for s in report["sources"]:
                line = f"- **{s.get('authority', '')}** — {s.get('title', '')}"
                if s.get("reviewed_at"):
                    line += f" (reviewed {s['reviewed_at']})"
                if s.get("url"):
                    line += f" — [View official source]({s['url']})"
                lines.append(line)
            return {"content": "\n".join(lines), "action": None}
        return {"content": "This report has no verified sources attached.", "action": None}
    if re.search(r"summar|overview|score|compatib", ql):
        if isinstance(report, dict):
            c = report.get("compatibility", {})
            s = report.get("summary", {})
            return {
                "content": (
                    f"**{country} compatibility: {c.get('score', 0)}% — {c.get('label', '')}.** "
                    f"{s.get('total_rules', total)} rules analyzed: {s.get('compliant', 0)} compliant, "
                    f"{s.get('partially_compliant', 0)} partial, {s.get('non_compliant', 0)} non-compliant, "
                    f"{s.get('undetermined', 0)} undetermined."
                ),
                "action": None,
            }
        return {"content": "Run an analysis first, then I'll summarize it.", "action": None}
    if re.search(r"^(hi|hello|hey|thanks|thank you)\b", ql):
        return {
            "content": (
                f"Hello! I'm tracking the {country} report over **{total} rule(s)**. "
                f"Ask *\"Why is Rule 2 non-compliant?\"*, *\"What am I missing?\"* or *\"Show violations\"*."
            ),
            "action": None,
        }
    if isinstance(report, dict):
        c = report.get("compatibility", {})
        lines = [
            f"**{country}: {c.get('score', 0)}% — {c.get('label', '')}.**",
            "",
        ]
        if report.get("violations"):
            lines.append(f"Top issue: Rule {report['violations'][0]['rule_id']} ({report['violations'][0].get('severity', '')}).")
            lines.append("")
        lines.append("Try: *\"Why is Rule 1 non-compliant?\"* · *\"What am I missing?\"* · *\"Show violations\"* · *\"Re-analyze\"*.")
        return {"content": "\n".join(lines), "action": None}
    return {
        "content": "Analyze your rules against the country first — then I can explain any finding.",
        "action": None,
    }
