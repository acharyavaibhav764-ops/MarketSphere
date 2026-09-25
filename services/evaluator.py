"""
services/evaluator.py — Deterministic compliance evaluation engine.

Evaluates a broker/product profile against approved regulatory rules.
Completely deterministic:
  - No LLM in the hot path.
  - Queries ONLY rules with review_status == "approved".
  - Evaluates statutory capital floors, retail leverage caps, and local presence.
  - Missing facts NEVER default to PASS (strictly evaluate to UNKNOWN).
  - Returns PASS, CONFLICT, or UNKNOWN with specific rule citations.
"""
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def parse_ratio_denominator(ratio_str: str) -> Optional[int]:
    """Parse leverage ratio e.g. '1:5' -> 5, '1:30' -> 30."""
    if not ratio_str or not isinstance(ratio_str, str):
        return None
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
            - jurisdiction: str (e.g. "United States", "United Kingdom", "UAE")
            - product_type: Optional[str] (e.g. "leveraged_derivatives", "spot_trading")
            - leverage_offered: Optional[str] (e.g. "1:100", "1:20")
            - capital_available_usd: Optional[float] (e.g. 500000.0)
            - has_local_presence: Optional[bool]
        db: SQLAlchemy session, list of rule objects, or MockDB.

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

    # Filter ONLY approved rules
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
            "topic": getattr(rule, "topic", "general"),
            "supporting_quote": rd.get("supporting_quote") or getattr(rule, "supporting_quote", ""),
        }

        # 1. Capital floor evaluation
        req_cap = getattr(rule, "required_capital", None)
        if req_cap is None and isinstance(rd, dict):
            req_cap = rd.get("required_capital_usd")

        if req_cap is not None:
            avail_cap = profile.get("capital_available_usd")
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
                    "reason": (
                        f"Available capital USD {avail_cap:,.2f} is below "
                        f"statutory requirement of USD {req_cap:,.2f}"
                    ),
                })
                results.append(entry)
                continue

        # 2. Retail leverage cap evaluation
        cap_str = getattr(rule, "leverage_cap", None)
        if not cap_str and isinstance(rd, dict):
            cap_str = rd.get("leverage_cap_retail")

        if cap_str:
            offered_str = profile.get("leverage_offered")
            if not offered_str:
                entry.update({
                    "status": "UNKNOWN",
                    "reason": "leverage_offered not provided in product profile",
                })
                results.append(entry)
                continue

            cap_ratio = parse_ratio_denominator(cap_str)
            offered_ratio = parse_ratio_denominator(offered_str)

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
                    "reason": f"Offered retail leverage {offered_str} exceeds statutory cap of {cap_str}",
                })
                results.append(entry)
                continue

        # 3. Local presence check (if rule mandates presence)
        presence_summary = rd.get("presence_friction_summary") or getattr(rule, "presence_friction_summary", None)
        if presence_summary and getattr(rule, "topic", "") == "presence":
            has_presence = profile.get("has_local_presence")
            if has_presence is None:
                entry.update({
                    "status": "UNKNOWN",
                    "reason": "has_local_presence not specified in product profile",
                })
                results.append(entry)
                continue
            if has_presence is False:
                entry.update({
                    "status": "CONFLICT",
                    "reason": f"Mandatory local presence not established: {presence_summary}",
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
