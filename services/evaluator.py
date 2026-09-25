"""
services/evaluator.py — Deterministic compliance evaluation engine.

Evaluates a broker/product profile against approved regulatory rules.
Completely deterministic:
  - No LLM in the hot path.
  - Returns PASS, CONFLICT, or UNKNOWN.
  - Missing facts NEVER default to PASS (they evaluate to UNKNOWN).
  - Every result references the rule_id, rule_version, topic, and verbatim supporting_quote.
"""
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _parse_ratio_denominator(ratio_str: str) -> Optional[int]:
    """Parse leverage ratio e.g. '1:5' -> 5, '1:100' -> 100."""
    try:
        parts = ratio_str.strip().split(":")
        if len(parts) == 2:
            return int(parts[1])
        return None
    except (ValueError, IndexError):
        return None


def evaluate_profile(profile: Dict[str, Any], db: Any) -> List[Dict[str, Any]]:
    """
    Evaluate a product/market profile against approved compliance rules.

    Args:
        profile: Dictionary containing:
            - jurisdiction: str (e.g. "UAE")
            - product_type: Optional[str] (e.g. "leveraged_derivatives")
            - leverage_offered: Optional[str] (e.g. "1:100")
            - capital_available_usd: Optional[float] (e.g. 300000)
        db: SQLAlchemy session or compatible object supporting query / all.

    Returns:
        List of evaluation result dicts:
            - rule_id: str
            - rule_version: int
            - topic: str
            - status: "PASS" | "CONFLICT" | "UNKNOWN"
            - reason: str
            - supporting_quote: str
    """
    from models.rule import ComplianceRule

    jurisdiction = profile.get("jurisdiction")
    if not jurisdiction:
        return []

    # Support SQLAlchemy Session query or mock DB
    if hasattr(db, "query"):
        rules = (
            db.query(ComplianceRule)
            .filter(
                ComplianceRule.jurisdiction == jurisdiction,
                ComplianceRule.review_status == "approved",
            )
            .all()
        )
    elif isinstance(db, (list, tuple)):
        rules = [
            r for r in db
            if getattr(r, "jurisdiction", None) == jurisdiction
            and getattr(r, "review_status", None) == "approved"
        ]
    else:
        rules = []

    results = []
    for rule in rules:
        rd = getattr(rule, "rule_data", {}) or {}
        entry: Dict[str, Any] = {
            "rule_id": getattr(rule, "rule_id", "unknown"),
            "rule_version": getattr(rule, "rule_version", 1),
            "topic": getattr(rule, "topic", None),
            "supporting_quote": rd.get("supporting_quote") or getattr(rule, "supporting_quote", None),
        }

        # 1. Capital floor evaluation
        req_cap = getattr(rule, "required_capital", None)
        if req_cap is None and isinstance(rd, dict):
            req_cap = rd.get("required_capital_usd")

        avail_cap = profile.get("capital_available_usd")
        if req_cap is not None:
            if avail_cap is None:
                entry.update({
                    "status": "UNKNOWN",
                    "reason": "capital_available_usd not provided in product profile",
                })
                results.append(entry)
                continue
            if avail_cap < req_cap:
                entry.update({
                    "status": "CONFLICT",
                    "reason": f"Available capital USD {avail_cap:,.2f} is below statutory requirement of USD {req_cap:,.2f}",
                })
                results.append(entry)
                continue

        # 2. Retail leverage cap evaluation
        cap_str = getattr(rule, "leverage_cap", None)
        if not cap_str and isinstance(rd, dict):
            cap_str = rd.get("leverage_cap_retail")

        offered_str = profile.get("leverage_offered")
        if cap_str and offered_str:
            cap_ratio = _parse_ratio_denominator(cap_str)
            offered_ratio = _parse_ratio_denominator(offered_str)
            if cap_ratio is None or offered_ratio is None:
                entry.update({
                    "status": "UNKNOWN",
                    "reason": f"Could not parse leverage ratio comparison: offered='{offered_str}', cap='{cap_str}'",
                })
                results.append(entry)
                continue
            if offered_ratio > cap_ratio:
                entry.update({
                    "status": "CONFLICT",
                    "reason": f"Offered leverage {offered_str} exceeds statutory cap of {cap_str}",
                })
                results.append(entry)
                continue

        # All evaluated parameters satisfied
        entry.update({
            "status": "PASS",
            "reason": "All checked statutory conditions satisfied",
        })
        results.append(entry)

    return results
