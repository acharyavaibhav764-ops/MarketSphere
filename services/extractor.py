"""
services/extractor.py — AI-assisted regulatory rule extraction pipeline.

Two-stage process:
  Stage 1 (Extractor LLM): Given a source text chunk, extract candidate rules
           as a JSON array conforming to CandidateRule.
  Stage 2 (Judge LLM):     Verify each extracted rule. Check that
           supporting_quote exists in the source and that numeric values are
           supported by the quote. Assign evidence_tag.
  Stage 3 (Deterministic): Programmatic verbatim check — any rule whose
           supporting_quote is not a literal substring of chunk_text is
           rejected unconditionally, regardless of what the LLM judge said.

Design principles:
  - The LLM never makes the final accept/reject decision — the deterministic
    verbatim check does. The LLM judge only calibrates evidence_tag.
  - Prompt version is recorded on every candidate for reproducibility.
  - All outputs arrive with review_status="draft". A human reviewer must
    approve before the rule reaches the evaluator.
"""
import json
import logging
from typing import Any

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

Your job is to verify each candidate rule and assign an `evidence_tag`.

For each rule:
1. Confirm that the `supporting_quote` field exists VERBATIM in SOURCE TEXT.
   If it does not, mark evidence_tag = "Unresolved Policy / Draft".
2. If numeric values (leverage_cap_retail, required_capital_usd) are present,
   confirm they are explicitly stated in the supporting_quote.
3. Assign evidence_tag:
   - "Verified Fact"              — quote is verbatim, value is confirmed, rule is in-force law.
   - "Analyst Estimate"           — plausible interpretation but not directly quoted.
   - "Unresolved Policy / Draft"  — contradicted, quote not found, or text is draft/consultation.

Return the same JSON array with `evidence_tag` added to every rule.
Do not remove any rules — only annotate them.
"""


# ---------------------------------------------------------------------------
# Core extraction function
# ---------------------------------------------------------------------------

def extract_candidate_rules(
    chunk_text: str,
    source_id: str,
    chunk_id: str | None,
    page_number: int | None,
    generator: Any,
) -> list[CandidateRule]:
    """Extract structured candidate rules from a single source text chunk.

    Args:
        chunk_text:  Text of one source chunk (heading + paragraphs, etc.).
        source_id:   SourceRegistry.source_id of the parent document.
        chunk_id:    Chunk identifier from HybridChunker (can be None).
        page_number: Zero-based page index (can be None for HTML sources).
        generator:   An object with a ``.generate(prompt, system)`` method
                     (e.g. the existing ``core.Generator`` Ollama wrapper).

    Returns:
        list[CandidateRule]: Zero or more validated candidate rules, all with
        ``review_status="draft"``. Rules with hallucinated quotes are excluded.
    """
    if not chunk_text.strip():
        logger.debug("Empty chunk passed to extractor — returning [].")
        return []

    schema_str = json.dumps(CandidateRule.model_json_schema(), indent=2)

    # -----------------------------------------------------------------------
    # Stage 1: Extraction
    # -----------------------------------------------------------------------
    extractor_system = EXTRACTOR_SYSTEM_TEMPLATE.format(schema=schema_str)
    extraction_prompt = f"SOURCE TEXT:\n{chunk_text}\n\nExtract rules as a JSON array."

    try:
        raw_extraction = generator.generate(
            prompt=extraction_prompt, system=extractor_system
        )
    except Exception as exc:
        logger.error("Extractor LLM call failed for chunk %s: %s", chunk_id, exc)
        return []

    try:
        extracted: list[dict] = json.loads(raw_extraction)
        if not isinstance(extracted, list):
            logger.warning("Extractor returned non-list JSON for chunk %s.", chunk_id)
            return []
    except json.JSONDecodeError as exc:
        logger.warning("Extractor returned invalid JSON for chunk %s: %s", chunk_id, exc)
        return []

    if not extracted:
        return []

    # -----------------------------------------------------------------------
    # Stage 2: LLM-as-a-Judge
    # -----------------------------------------------------------------------
    judge_prompt = (
        f"SOURCE TEXT:\n{chunk_text}\n\n"
        f"EXTRACTED:\n{json.dumps(extracted, indent=2)}"
    )

    try:
        raw_judged = generator.generate(prompt=judge_prompt, system=JUDGE_SYSTEM)
        judged: list[dict] = json.loads(raw_judged)
        if not isinstance(judged, list):
            logger.warning(
                "Judge returned non-list JSON for chunk %s. "
                "Falling back to extractor output.", chunk_id,
            )
            judged = extracted
    except (json.JSONDecodeError, Exception) as exc:
        logger.warning(
            "Judge LLM failed for chunk %s (%s). Falling back to extractor output.", chunk_id, exc
        )
        judged = extracted

    # -----------------------------------------------------------------------
    # Stage 3: Deterministic verbatim validation — final gate, no exceptions
    # -----------------------------------------------------------------------
    validated: list[CandidateRule] = []
    for raw_rule in judged:
        quote = raw_rule.get("supporting_quote", "")

        # Hard rejection: quote must be a literal substring of the source text
        if not quote or quote not in chunk_text:
            logger.warning(
                "Rejected candidate rule from chunk %s — supporting_quote not verbatim: %r",
                chunk_id, quote[:80],
            )
            continue

        # Inject provenance fields if the LLM omitted them
        raw_rule.setdefault("source_id", source_id)
        raw_rule.setdefault("source_chunk_id", chunk_id)
        raw_rule.setdefault("page_number", page_number)
        raw_rule.setdefault("extraction_model", "ollama")
        raw_rule.setdefault("prompt_version", PROMPT_VERSION)
        raw_rule.setdefault("evidence_tag", "Analyst Estimate")

        # Schema validation via Pydantic
        try:
            rule = CandidateRule(**raw_rule)
        except Exception as exc:
            logger.warning(
                "Schema validation failed for candidate in chunk %s: %s", chunk_id, exc
            )
            continue

        validated.append(rule)

    logger.info(
        "Chunk %s: %d/%d candidates passed verbatim + schema validation.",
        chunk_id, len(validated), len(judged),
    )
    return validated
