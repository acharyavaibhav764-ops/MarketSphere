# MochaTrade Country Trading Policy Extraction — Agent Implementation Plan

**Target Audience:** AI Agent / Developer (Instructional Roadmap)
**Context:** We are building the "MochaTrade Country Trading Policy Extraction & Compliance System" on top of the existing `MarketSphere` RAG codebase. 
**Current State:** The `MarketSphere` parsing architecture is complete up to `v4`.
**Constraints:** The parser pipeline must implement **Phase v5 (PDF deep parser with DeepSeek-OCR2)**, but must **strictly exclude v6 (vLLM migration)** due to hardware constraints.

This document serves as a verbose, step-by-step implementation guide with code snippets to achieve the end-to-end MochaTrade compliance workflow.

---

## Phase 1: Source Registry and Ingestion Foundation

**Objective:** Build a robust, versioned repository for official regulator documents. We need to store original bytes in MinIO and metadata in PostgreSQL.

### 1.1 Database Models (SQLAlchemy)
Create models to track the provenance of every document.
```python
# models/source.py
from sqlalchemy import Column, String, DateTime, Enum, Integer
from sqlalchemy.orm import declarative_base
import datetime

Base = declarative_base()

class ProcessingStatus(str, Enum):
    DISCOVERED = "discovered"
    FETCHED = "fetched"
    PARSED = "parsed"
    FAILED = "failed"
    REVIEWED = "reviewed"

class SourceRegistry(Base):
    __tablename__ = 'source_registry'
    
    source_id = Column(String, primary_key=True)
    jurisdiction = Column(String, index=True)
    regulator = Column(String)
    title = Column(String)
    source_url = Column(String, unique=True)
    source_type = Column(String) # HTML, PDF, DOCX
    content_hash = Column(String) # For duplication detection
    storage_uri = Column(String) # MinIO bucket path
    retrieved_at = Column(DateTime, default=datetime.datetime.utcnow)
    processing_status = Column(String, default=ProcessingStatus.DISCOVERED)
```

### 1.2 Ingestion API
Implement FastAPI endpoints to handle URL fetching and file uploads. Use `minio` python client to persist original bytes before parsing.
```python
# api/v1/endpoints/sources.py
from fastapi import APIRouter, UploadFile, HTTPException
import hashlib

router = APIRouter()

@router.post("/sources/ingest")
async def ingest_source(jurisdiction: str, regulator: str, file: UploadFile):
    content = await file.read()
    content_hash = hashlib.sha256(content).hexdigest()
    
    # 1. Check if hash exists in DB
    # 2. Upload original `content` to MinIO
    # 3. Create SourceRegistry record
    # 4. Return source_id
    return {"source_id": "src_123", "hash": content_hash, "status": "fetched"}
```

---

## Phase 2: Parser Pipeline Completion (v5 only)

**Objective:** The RAG parser is at `v4` (PDF stub). We must implement **v5 (PdfPageRouter)** for per-page triage. **Do NOT implement v6 (vLLM migration)**; use HuggingFace `transformers` for DeepSeek-OCR2 instead.

### 2.1 Per-Page Triage Logic
Use PyMuPDF (`fitz`) to rapidly determine the optimal parsing tool per page without invoking heavy models upfront.
```python
# parsers/pdf_router.py
import fitz # PyMuPDF

def triage_page(page: fitz.Page) -> str:
    text_tokens = len(page.get_text().split())
    has_text = text_tokens > 10
    
    # Check for tables
    has_table = len(page.find_tables().tables) > 0
    
    # Calculate image area (pseudo-code)
    images = page.get_images(full=True)
    image_ratio = calculate_image_area(images) / page.rect.get_area()

    if not has_text or image_ratio > 0.5:
        return "DEEPSEEK_OCR2" # Scanned or heavy image
    elif has_table:
        return "DOCLING" # Structure-aware extraction
    else:
        return "PYMUPDF4LLM" # Standard clean text
```

### 2.2 DeepSeek-OCR2 Integration (HF Transformers)
Integrate DeepSeek-OCR2 for pages routed to it. Keep it on `bfloat16` and use Flash Attention 2 to fit within VRAM constraints.
```python
# parsers/deepseek_parser.py
from transformers import AutoModel, AutoTokenizer
import torch

class DeepSeekOCR2Parser:
    def __init__(self):
        self.model_name = "deepseek-ai/DeepSeek-OCR-2"
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name, trust_remote_code=True)
        self.model = AutoModel.from_pretrained(
            self.model_name, 
            trust_remote_code=True, 
            _attn_implementation='flash_attention_2', 
            use_safetensors=True
        ).eval().cuda().to(torch.bfloat16)

    def parse_image(self, image_path: str) -> str:
        prompt = "<image>\n<|grounding|>Convert the document to markdown. "
        res = self.model.infer(
            self.tokenizer, 
            prompt=prompt, 
            image_file=image_path, 
            output_path='./temp_output', 
            base_size=1024, 
            image_size=768, 
            crop_mode=True
        )
        return res
```
*(Ensure all pages, regardless of route, are unified into the `DoclingDocument` or common block schema before chunking.)*

---

## Phase 3: AI-Assisted Rule Extraction

**Objective:** Pass the chunked, anchored document text to an LLM to extract candidate rules. Output must strictly conform to a Pydantic schema and include verifiable quotes.

### 3.1 Candidate Rule Schema
```python
# schemas/rule.py
from pydantic import BaseModel, Field
from typing import Optional, Literal

class CandidateRule(BaseModel):
    jurisdiction: str = Field(..., description="Country or market")
    regulator: str = Field(..., description="Issuing authority")
    topic: str = Field(..., description="Regulatory topic (e.g., AML, KYC)")
    obligation_or_restriction: str = Field(..., description="The actual rule summary")
    
    # Integrating TOPSIS Market Ranking parameters:
    leverage_cap_retail: Optional[str] = Field(None, description="Statutorily permitted retail leverage cap (e.g., 1:5, 1:300) [C4]")
    required_capital_local_currency: Optional[float] = Field(None, description="Minimum statutory paid-up capital [C6]")
    presence_friction: Optional[str] = Field(None, description="Physical infra, resident director, or data localization mandates [C7]")
    pathway_clarity: Optional[str] = Field(None, description="Explicit framework for leveraged derivatives [C3]")
    
    applicability_conditions: Optional[str] = Field(None, description="When does this apply?")
    required_facts: Optional[list[str]] = Field(None, description="Facts needed to evaluate")
    supporting_quote: str = Field(..., description="Verbatim quote from the source text")
    source_id: str = Field(...)
    page_number: Optional[int] = Field(None)
    evidence_tag: Literal["Verified Fact", "Analyst Estimate", "Unresolved Policy / Draft"] = Field(..., description="Confidence tag for Monte Carlo calibration")
```

### 3.2 Extraction Prompt Configuration
Use the local `Ollama` generator (already in `core/generator.py`) combined with structured outputs.
```python
# services/extractor.py
import json

def extract_rules(chunk_text: str, source_metadata: dict) -> list[CandidateRule]:
    extractor_prompt = f"""
    You are a regulatory extraction agent. Extract structured regulatory rules matching the CandidateRule schema.
    Specifically target constraints regarding Leverage Limits, Capital Requirements, and Local Presence.
    You MUST provide a `supporting_quote` that is a verbatim exact match from the text.
    """
    # Invoke local LLM via API for extraction
    # extracted_payload = llm_client.chat(prompt=extractor_prompt, context=chunk_text)
    
    # LLM-as-a-Judge Phase (Combat Hallucinations)
    judge_prompt = f"""
    Verify the extracted JSON against the source chunk. 
    1. Does the `supporting_quote` exist verbatim in the text?
    2. Does the quote logically support the extracted `leverage_cap_retail` or `required_capital_local_currency`?
    If yes, mark as 'Verified Fact'. If contradicted or draft phase, mark as 'Unresolved Policy / Draft'. 
    If unverifiable but estimated, mark as 'Analyst Estimate'.
    """
    # validated_payload = llm_client.chat(prompt=judge_prompt, context={"text": chunk_text, "extracted": extracted_payload})
    
    # rules = [CandidateRule(**r) for r in json.loads(validated_payload)]
    
    # Deterministic programmatic check for absolute verbatim match
    # for rule in rules:
    #     if rule.supporting_quote not in chunk_text:
    #         raise ValueError(f"Hallucinated quote detected in {rule.jurisdiction}")
    return rules
```

---

## Phase 4: Rule Versioning and Human Review

**Objective:** Draft rules are unusable until human-reviewed. Build the review state machine.

### 4.1 Approved Rule Store
```python
# models/rule_store.py
class RuleStatus(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"

class ComplianceRule(Base):
    __tablename__ = 'compliance_rules'
    
    rule_id = Column(String, primary_key=True)
    rule_version = Column(Integer, default=1)
    status = Column(String, default=RuleStatus.DRAFT)
    rule_data = Column(JSON) # Stores CandidateRule dict
    reviewer_id = Column(String, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
```

### 4.2 Review API
```python
# api/v1/endpoints/rules.py
@router.post("/rules/{rule_id}/review")
async def review_rule(rule_id: str, action: str, reviewer_id: str):
    # action in ["approve", "reject"]
    # Update DB status and increment version if edited.
    return {"status": "success", "new_state": action}
```

---

## Phase 5: Deterministic Evaluator

**Objective:** Check a given product profile against approved rules. Do NOT use vector similarity for final answers. Use deterministic matching of `required_facts`.

```python
# services/evaluator.py
def evaluate_profile(profile_facts: dict, jurisdiction: str) -> dict:
    # 1. Fetch only APPROVED rules for the jurisdiction
    approved_rules = db.query(ComplianceRule).filter(
        ComplianceRule.jurisdiction == jurisdiction,
        ComplianceRule.status == "approved"
    ).all()
    
    results = []
    for rule in approved_rules:
        # 2. Check if all required facts for the rule exist in profile
        required = rule.rule_data.get("required_facts", [])
        missing_facts = [f for f in required if f not in profile_facts]
        
        if missing_facts:
            results.append({"rule": rule.rule_id, "status": "UNKNOWN", "reason": f"Missing facts: {missing_facts}"})
            continue
            
        # 3. Deterministic logic based on facts (Mock example)
        # E.g., if "allows_retail" == True and rule says "no retail" -> CONFLICT
        # This requires strict structured mapping of facts to conditions.
        
    return results
```

---

## Phase 6: Integration with TOPSIS Market Ranker

**Objective:** Map the extracted JSON variables to the **Multi-Criteria Decision Making (MCDM)** pipeline for sequential market ranking.

1. **Mapping to Matrix:** Pass `leverage_cap_retail`, `required_capital_local_currency`, and `presence_friction` into the TOPSIS decision matrix as quantitative/categorical inputs.
2. **Capital Burden Knockout:** Use `required_capital_local_currency` to execute a hard knockout if the capital burden exceeds the startup's runway constraints (Criterion C6).
3. **Stochastic Multicriteria Acceptability Analysis (SMAA):** Route the `evidence_tag` to the Evidence-Calibrated Monte Carlo engine. 'Verified Fact' receives tight Gaussian noise; 'Analyst Estimate' receives wider variance, ensuring mathematical robustness in the final ranking.

---

## Phase 7: Dashboard & Demo UI

**Objective:** End-to-end visualization.
- **Tools**: React/Next.js or Vanilla HTML/JS based on current stack preferences.
- **Views needed**:
  1. **Source Ingestion:** File upload + URL submit.
  2. **Review Queue:** Side-by-side view of rule candidate vs. original PDF/text highlight.
  3. **Evaluator Form:** Input JSON/form for `profile_facts` -> outputs `PASS`/`CONFLICT`/`UNKNOWN` with citations to approved rules and original source pages. 

**Note to Agent:** Treat this plan as the ultimate source of truth for your multi-step generation. Commit incremental implementations (e.g. DB models first, then parsing, then extraction endpoints). Ensure regression tests from `MarketSphere` v0.4 still pass as you build v5.
