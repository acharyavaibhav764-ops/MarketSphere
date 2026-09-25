"""
services/extractor.py — AI-assisted regulatory rule extraction pipeline.

Two-stage process with mandatory programmatic verbatim verification:
  Stage 1 (Extractor LLM): Given a source text chunk, extract candidate rules
           as a JSON array conforming to CandidateRule via llm_client.chat() / generate().
  Stage 2 (Judge LLM):     Separate LLM verification step. Evaluates extracted rules
           against the source text, confirms numeric accuracy, and assigns evidence_tag.
  Stage 3 (Deterministic): Programmatic verbatim check — raises ValueError or drops
           any rule whose supporting_quote is not a literal substring of chunk_text.
"""
import json
import logging
from typing import Any, List, Optional

from schemas.rule import CandidateRule

logger = logging.getLogger(__name__)

PROMPT_VERSION = "v1.0"

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

EXTRACTOR_SYSTEM_TEMPLATE = """\
You are a regulatory extraction agent for MochaTrade.

Given a source text chunk from an official regulatory document, extract every
trading / compliance rule into a JSON array. Each element must conform to this
JSON schema:
{schema}

STRICT RULES:
1. `supporting_quote` MUST be a verbatim substring of the provided SOURCE TEXT.
   Copy it character-for-character — do not paraphrase or summarise.
2. Extract `leverage_cap_retail` only if the source explicitly states a numeric
   cap (e.g. "1:5", "1:300", "maximum leverage of five to one").
3. Extract `required_capital_usd` as a float only if a specific capital floor
   is stated in USD or clearly convertible to USD.
4. Use null for any field not explicitly supported by the source text.
   NEVER invent, assume, or interpolate missing values.
5. Return an empty array [] if the chunk contains no regulatory rules.
"""

JUDGE_SYSTEM = """\
You are an LLM judge for a regulatory compliance system.

You will receive:
  - SOURCE TEXT: The original chunk from the regulatory document.
  - EXTRACTED: A JSON array of candidate rules extracted from that chunk.

Your job is to verify each candidate rule as a distinct second evaluation pass:
1. Confirm that the `supporting_quote` field exists VERBATIM in SOURCE TEXT.
2. If numeric values (leverage_cap_retail, required_capital_usd) are present,
   confirm they are explicitly stated in the supporting_quote.
3. Assign evidence_tag:
   - "Verified Fact"              — quote is verbatim, value is confirmed, rule is in-force law.
   - "Analyst Estimate"           — plausible interpretation but not directly quoted.
   - "Unresolved Policy / Draft"  — contradicted, quote not found, or text is draft/consultation.

Return the same JSON array with `evidence_tag` added to every rule.
Do not remove any rules — only annotate them.
"""


def _call_llm(client: Any, system_prompt: str, user_prompt: str) -> str:
    """Execute LLM call via client.chat() or generator.generate()."""
    if hasattr(client, "chat"):
        # Real llm_client.chat() call
        response = client.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
        )
        if hasattr(response, "message") and hasattr(response.message, "content"):
            return response.message.content
        if isinstance(response, dict):
            return response.get("message", {}).get("content") or response.get("content", "")
        return str(response)
    elif hasattr(client, "generate"):
        return client.generate(prompt=user_prompt, system=system_prompt)
    else:
        raise TypeError(f"Unsupported LLM client type: {type(client)}")


def verify_verbatim_quote(supporting_quote: str, chunk_text: str) -> None:
    """
    Deterministic programmatic check.
    Raises ValueError if supporting_quote is not an exact verbatim substring.
    """
    if not supporting_quote or supporting_quote not in chunk_text:
        raise ValueError(
            f"Hallucination detected: supporting_quote {supporting_quote!r} "
            f"is not a verbatim substring of source chunk."
        )


def extract_rules(
    chunk_text: str,
    source_id: str,
    chunk_id: Optional[str] = None,
    page_number: Optional[int] = None,
    llm_client: Any = None,
    raise_on_hallucination: bool = False,
) -> List[CandidateRule]:
    """
    Extract structured candidate rules using two-stage LLM pipeline + verbatim check.
    """
    if not chunk_text.strip():
        return []

    schema_str = json.dumps(CandidateRule.model_json_schema(), indent=2)

    # -----------------------------------------------------------------------
    # Stage 1: Extraction LLM Call
    # -----------------------------------------------------------------------
    extractor_system = EXTRACTOR_SYSTEM_TEMPLATE.format(schema=schema_str)
    extraction_prompt = f"SOURCE TEXT:\n{chunk_text}\n\nExtract rules as a JSON array."

    try:
        raw_extraction = _call_llm(llm_client, extractor_system, extraction_prompt)
    except Exception as exc:
        logger.error("Extractor LLM call failed: %s", exc)
        return []

    try:
        extracted: list[dict] = json.loads(raw_extraction)
        if not isinstance(extracted, list):
            return []
    except json.JSONDecodeError as exc:
        logger.warning("Extractor returned invalid JSON: %s", exc)
        return []

    if not extracted:
        return []

    # -----------------------------------------------------------------------
    # Stage 2: LLM-as-a-Judge (Separate Second Call)
    # -----------------------------------------------------------------------
    judge_prompt = (
        f"SOURCE TEXT:\n{chunk_text}\n\n"
        f"EXTRACTED:\n{json.dumps(extracted, indent=2)}"
    )

    try:
        raw_judged = _call_llm(llm_client, JUDGE_SYSTEM, judge_prompt)
        judged: list[dict] = json.loads(raw_judged)
        if not isinstance(judged, list):
            judged = extracted
    except Exception as exc:
        logger.warning("Judge LLM failed (%s), using extraction output.", exc)
        judged = extracted

    # -----------------------------------------------------------------------
    # Stage 3: Programmatic Verbatim Validation
    # -----------------------------------------------------------------------
    validated: List[CandidateRule] = []
    for raw_rule in judged:
        quote = raw_rule.get("supporting_quote", "")

        # Verbatim check
        if raise_on_hallucination:
            verify_verbatim_quote(quote, chunk_text)
        elif not quote or quote not in chunk_text:
            logger.warning("Rejected non-verbatim quote: %r", quote[:80])
            continue

        raw_rule.setdefault("source_id", source_id)
        raw_rule.setdefault("source_chunk_id", chunk_id)
        raw_rule.setdefault("page_number", page_number)
        raw_rule.setdefault("extraction_model", getattr(llm_client, "model", "llm"))
        raw_rule.setdefault("prompt_version", PROMPT_VERSION)
        raw_rule.setdefault("evidence_tag", "Analyst Estimate")

        try:
            rule = CandidateRule(**raw_rule)
            validated.append(rule)
        except Exception as exc:
            logger.warning("Schema validation failed: %s", exc)
            continue

    return validated


# Alias for backwards compatibility
extract_candidate_rules = extract_rules
