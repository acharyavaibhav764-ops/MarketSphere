# MochaTrade — Country Trading Policy Extraction & Compliance System
## Implementation Plan

**Module:** Regulatory Compliance Copilot (Module B)  
**Document type:** Technical implementation roadmap  
**Approach:** Source-grounded, human-reviewed, phased MVP

---

## 1. Objective

Build a system that collects official trading and investment regulations for selected countries, extracts relevant requirements into structured rules, and makes those rules usable by MochaTrade's compliance-checking workflow.

The system must preserve traceability from every extracted rule back to the original regulator document or webpage. AI-generated content is a **candidate**, not authoritative policy. A rule must pass validation and human review before it can be used by the compliance evaluator.

### Expected end-to-end workflow

1. Select a country, regulator, and regulatory topic.
2. Discover official regulator webpages and downloadable documents.
3. Fetch or upload the source and preserve the original.
4. Parse the source using the parser pipeline, including Docling where appropriate.
5. Extract candidate rules with supporting quotations and section/page references.
6. Validate the candidate's schema and evidence.
7. Send the candidate to a human reviewer.
8. Store approved, versioned rules.
9. Evaluate a MochaTrade product/activity profile against approved rules.
10. Return `PASS`, `CONFLICT`, or `UNKNOWN`, with the rule, evidence, and source version.

---

## 2. Scope and MVP Strategy

### MVP scope

- Start with **one country and one clearly defined regulatory topic**.
- Select a small set of official sources from the relevant regulator(s).
- Ingest a manageable pilot set of documents and webpages.
- Support HTML and text-based PDF first.
- Use Docling for documents where layout, tables, or reading order require it.
- Extract approximately 10–20 candidate rules for the initial demonstrator.
- Require human approval before rules become active.
- Implement a deterministic evaluator for a limited, explicit product profile.

### Not required for the first MVP

- Exhaustive coverage of every regulation in a country.
- Fully autonomous legal interpretation or approval.
- Every country at once.
- Automatic publication of newly discovered rules.
- Complex multi-agent orchestration.
- A universal OCR pipeline before real scanned documents are encountered.
- vLLM migration or GPU-dependent infrastructure.
- OPA unless the first rule set demonstrates a need for it.

### Definition of a successful MVP

A reviewer can trace a compliance finding from the dashboard to an approved rule, its supporting passage, the source document, and the source's retrieval/version metadata.

---

## 3. Define What “Country Trading Policies” Means

Before collecting documents, define the product and regulatory scope. “Trading policies” is too broad to scrape indiscriminately.

Create a country scope sheet containing:

- Country / jurisdiction
- Regulator or official issuing body
- MochaTrade activity being evaluated
- Instruments or asset classes in scope
- Customer types in scope
- Relevant topics (for example, licensing, onboarding/KYC, AML, custody, marketing, investor protection, reporting)
- Official source domains
- Relevant document types
- Known exclusions and unresolved questions

Do not assume every regulator's rules apply to every MochaTrade activity. Applicability must be recorded and reviewed.

---

## 4. Country Policy Discovery and Collection

### 4.1 Identify official sources

For each selected jurisdiction:

1. Identify the primary securities/markets regulator and any other official authority relevant to the scoped activity.
2. Locate official rulebooks, acts, regulations, circulars, notices, FAQs, guidance, and regulator-maintained webpages.
3. Prefer regulator-controlled domains and official gazettes or government repositories.
4. Record the exact URL and the issuing body for each source.
5. Record whether the source is binding legislation/regulation, regulator rule, guidance, FAQ, or another document type. Do not treat these categories as interchangeable.
6. Capture publication, commencement/effective, amendment, and repeal dates when stated.
7. Flag sources whose legal status or applicability is unclear for human review.

Avoid treating search-engine snippets, third-party summaries, blogs, or vendor articles as authoritative rule sources. They may help discover an official source, but should not be the evidence used to approve a rule.

### 4.2 Build a source registry

Maintain a registry before extraction begins.

| Field | Purpose |
|---|---|
| `source_id` | Internal stable identifier |
| `jurisdiction` | Country/market |
| `regulator` | Issuing authority |
| `title` | Official title |
| `source_url` | Canonical source URL |
| `source_type` | HTML, PDF, DOCX, etc. |
| `instrument_type` | Act, regulation, rulebook, circular, guidance, etc. |
| `published_at` | Publication date, if available |
| `effective_at` | Effective date, if available |
| `amended_at` | Amendment date, if available |
| `retrieved_at` | When MochaTrade collected it |
| `content_hash` | Detects identical/changed content |
| `storage_uri` | Location of preserved original |
| `source_status` | Active, superseded, repealed, unknown, etc. |
| `processing_status` | Discovered, fetched, parsed, failed, reviewed |

Unknown dates or statuses must remain unknown—not be guessed.

### 4.3 Fetch and preserve

Implement a source ingestion service that:

- Accepts an official URL or manual upload.
- Fetches HTML or downloads the document where permitted.
- Stores the original bytes in MinIO.
- Saves the canonical URL, retrieval timestamp, response metadata where available, and content hash.
- Detects duplicate content using the hash.
- Creates a new source version when content changes.
- Records fetch failures, redirects, inaccessible pages, and unsupported formats.
- Respects site terms, access restrictions, and reasonable request rates.

For HTML, preserve the page URL and relevant page metadata. For downloaded files, preserve the original file—not only extracted text.

### 4.4 Source discovery should be controlled

For the MVP, use a curated list of official regulator pages and document links rather than broad, uncontrolled web crawling. Add automated discovery only after the team can reliably identify source authority, document type, version, and applicability.

---

## 5. Document Parsing with Docling

### 5.1 Docling's role

Docling is the document-understanding/parsing component. It can help extract structured content from PDFs and Office documents, including layout and tables. It does **not** determine legal authority, applicability, or compliance, and it should not approve rules.

### 5.2 Recommended parser routing

```text
Source document
     |
     v
File/type detection
     |
     +--> HTML ----------------> HTML parser
     |
     +--> TXT / MD ------------> Text parser
     |
     +--> Text-based PDF ------> Baseline PDF parser
     |                               |
     |                       Quality check fails?
     |                               |
     |                         Docling fallback
     |
     +--> Complex PDF/table ---> Docling
     |
     +--> DOCX / PPTX ---------> Docling (when needed)
     |
     +--> Scanned PDF ---------> OCR-capable route, only when needed
                                     |
                                     v
                     Normalized text + structure + anchors
```

The routing above is a recommended policy, not a claim that every parser path is already implemented. Confirm supported formats and behavior against the installed Docling version and actual source files.

### 5.3 Parsing implementation steps

1. Define a common parser interface and normalized output schema.
2. Detect file type and select a parser through `ParserRouter`.
3. Run the baseline parser for simple sources.
4. Route complex PDFs, tables, or poor-quality output to Docling.
5. Preserve headings, lists, tables, page numbers, and section identifiers where available.
6. Normalize text without discarding the original parsed representation.
7. Store parser name/version, warnings, and processing status.
8. Compare output with manually checked sample pages.
9. Add OCR only for sources confirmed to be scanned or unreadable by the baseline path.

### 5.4 Required parser output

Each parsed block should retain:

- `source_id` and source version
- `block_id`
- `text`
- `block_type` (heading, paragraph, table, list, etc.)
- `page_number` when available
- `section_heading` / section identifier when available
- `sequence_index`
- `parser_name` and `parser_version`
- parsing warnings or confidence indicators, if available

Never silently drop a table, page, or parsing error. Mark uncertain or incomplete extraction for review.

### 5.5 Chunking

Use structure-aware chunking rather than arbitrary fixed-size splitting alone.

- Keep a heading with its relevant paragraphs.
- Keep table headers with their rows.
- Preserve nearby exceptions, definitions, and cross-references.
- Attach source and page/section anchors to every chunk.
- Avoid merging unrelated sections or different documents.
- Store chunk IDs so candidate rules can cite exact source chunks.

Use the existing HybridChunker if it preserves these properties and passes tests; otherwise adapt it additively.

---

## 6. AI-Assisted Rule Extraction

### 6.1 Extraction flow

```text
Parsed, anchored chunks
        |
        v
Topic / relevance filtering
        |
        v
LLM extraction with strict schema
        |
        v
Schema validation (Pydantic)
        |
        v
Evidence/quotation validation
        |
        v
Candidate rule queue (draft)
        |
        v
Human review
```

### 6.2 Candidate rule schema

Minimum fields:

- `candidate_id`
- `jurisdiction`
- `regulator`
- `topic`
- `obligation_or_restriction`
- `applicability_conditions`
- `required_facts`
- `exceptions`
- `effective_from` / `effective_to` (nullable)
- `source_id` and source version
- `source_section` / page number
- `supporting_quote` (verbatim)
- `source_chunk_id`
- `extraction_model`
- `prompt_version`
- `validation_status`
- `review_status`

### 6.3 Extraction rules

- Provide the LLM only relevant source passages plus enough surrounding context.
- Ask it to extract only what the supplied evidence supports.
- Require a verbatim quotation for every candidate.
- Require source chunk and section/page references.
- Represent missing dates, exceptions, or applicability details as unknown/null.
- Do not let the model invent missing legal details or combine separate provisions without references.
- Keep the original wording alongside any normalized summary.
- Label all model outputs as `draft`.
- Validate the quote against the stored source text (exact match or a carefully defined normalization).
- Route failed or ambiguous candidates to human review rather than silently accepting them.

### 6.4 Extraction evaluation

Before scaling, create a small manually annotated gold set. Measure:

- Whether the candidate is a real rule in the passage.
- Correctness of obligation/restriction.
- Correctness of applicability and exceptions.
- Date/status extraction accuracy.
- Evidence quotation and location accuracy.
- Reviewer correction/rejection rate.

Compare extraction approaches on the same gold set: baseline prompt, strict-schema prompt, and strict schema plus evidence validation. Choose based on measured results—not intuition alone.

---

## 7. Human Review and Approved Rule Store

### 7.1 Review interface

Show the reviewer:

- Candidate rule and normalized summary
- Original supporting quotation
- Surrounding source text
- Source title, regulator, URL, version, page/section
- Extracted dates and applicability
- Validation warnings

Allow reviewer actions: approve, edit, reject, or request more context.

### 7.2 Approval requirements

A rule cannot become active unless a reviewer confirms:

- The source is official and relevant.
- The passage supports the rule.
- The rule's scope and exceptions are represented correctly.
- The effective/status metadata is accurate or explicitly unknown.
- The rule is not a duplicate or superseded version.

Store reviewer identity, review timestamp, edits, and approval decision. Preserve previous versions rather than overwriting them.

### 7.3 Rule store

Use a relational database as the source of truth for approved rules and their versions. ChromaDB can support semantic retrieval, but should not be the authoritative rule registry.

Minimum rule fields:

- `rule_id`, `rule_version`
- jurisdiction, regulator, topic
- normalized rule text
- applicability conditions
- required facts and exceptions
- effective dates and status
- source ID/version, quote, page/section, chunk ID
- approval status, reviewer, review timestamp
- supersedes/superseded-by references

---

## 8. Compliance Evaluation

The evaluator should use approved, structured rules and explicit product facts. Do not use free-form LLM output or vector similarity as the final decision.

### Product/activity profile

Define only the facts needed by the pilot rules. Depending on scope, these may include:

- Jurisdiction(s) served
- Product/activity type
- Instruments supported
- Customer category
- Custody or execution model
- Onboarding and transaction workflow
- Relevant licensing/authorization facts

Do not assume a fact that the product team has not supplied.

### Result semantics

- `CONFLICT`: known product facts violate an applicable approved rule.
- `PASS`: all required facts are present and the defined rule conditions are satisfied.
- `UNKNOWN`: required facts, applicability, source status, or interpretation are missing/ambiguous.

A `PASS` means only that the evaluated rule checks passed for the supplied facts. It is not a declaration of complete legal compliance or legal clearance.

Every result must include rule ID/version, facts used, reason, source quotation, and source reference.

---

## 9. System Architecture

```text
                 OFFICIAL REGULATOR SOURCES
                 HTML pages / PDF / DOCX
                           |
                           v
              Source Registry + Ingestion API
                           |
                fetch / upload / hash / version
                           |
                           v
                    MinIO (originals)
                           |
                           v
                     ParserRouter
             HTML / Text / PDF / Docling
                           |
                           v
              Normalized, anchored content
                           |
                           v
             Structure-aware chunking
                           |
                           v
          Relevance filtering + LLM extraction
                           |
                           v
             Pydantic + evidence validation
                           |
                           v
                  Human review UI
                           |
                           v
              PostgreSQL: approved rules
                + versions + audit trail
                           |
                           v
                Deterministic evaluator
                           |
                           v
                 FastAPI evaluation API
                           |
                           v
             Dashboard / cited compliance report

ChromaDB: optional semantic retrieval over source chunks.
Ollama: initial LLM runtime for extraction.
```

### Component responsibilities

| Component | Responsibility |
|---|---|
| FastAPI | Source ingestion, extraction, review, and evaluation endpoints |
| MinIO | Original documents and retained artifacts |
| ParserRouter | Select parser based on type/quality |
| Docling | Structured parsing for supported complex documents |
| HybridChunker | Structure-aware chunking, if validated |
| Ollama | Candidate rule extraction |
| Pydantic/evidence validator | Enforce schema and source traceability |
| PostgreSQL/relational DB | Source registry, approved rules, versions, audit events |
| ChromaDB | Optional semantic search over chunks |
| Dashboard | Source status, review queue, evaluation results |

Keep the current API contracts intact. Add functionality incrementally and cover existing behavior with regression tests.

---

## 10. Suggested API Endpoints

Adapt route names to the existing backend conventions.

- `POST /sources/ingest` — ingest official URL or upload
- `GET /sources` — list sources and processing status
- `GET /sources/{source_id}` — source metadata/version details
- `POST /sources/{source_id}/parse` — trigger/retry parsing
- `POST /sources/{source_id}/extract-rules` — create candidate rules
- `GET /rules?status=draft` — review queue
- `GET /rules/{rule_id}` — rule and evidence
- `POST /rules/{rule_id}/review` — approve/edit/reject
- `GET /rules?status=approved` — approved rules
- `POST /evaluations` — evaluate a product profile
- `GET /evaluations/{evaluation_id}` — retrieve report

---

## 11. Phased Implementation Roadmap

### Phase 0 — Scope and baseline audit

**Tasks**
- Choose one pilot jurisdiction and topic.
- Identify official regulator sources.
- Audit existing FastAPI, MinIO, ChromaDB, Ollama, parser, and chunking code.
- Confirm API contracts and runtime constraints.
- Assemble a small sample corpus and manually inspect representative pages.

**Deliverables**
- Country scope sheet
- Official source list
- Existing-component inventory
- Baseline test set

**Exit gate:** One sample source can be ingested and retrieved without breaking existing behavior.

### Phase 1 — Source registry and ingestion

**Tasks**
- Implement source metadata model.
- Fetch official HTML/PDF or accept manual upload.
- Store originals in MinIO.
- Calculate hashes and record retrieval/version metadata.
- Detect duplicates and record failures explicitly.

**Deliverables:** Source registry, ingestion endpoint, preserved originals.

**Exit gate:** Every source has provenance, retrieval metadata, and a stable identifier.

### Phase 2 — Parsing and Docling integration

**Tasks**
- Stabilize parser interface and ParserRouter.
- Parse HTML/text and ordinary PDFs.
- Integrate Docling for complex PDFs/tables or supported Office files.
- Preserve page/section anchors and table structure.
- Add parser quality checks and regression fixtures.
- Add OCR only when scanned-source tests require it.

**Deliverables:** Normalized anchored text, Docling adapter, parser tests.

**Exit gate:** Representative source passages can be traced back to the correct source location; failures are visible.

### Phase 3 — Rule extraction and evidence validation

**Tasks**
- Define candidate-rule Pydantic schema.
- Implement relevance filtering and LLM extraction.
- Require quotations and chunk/page/section references.
- Validate schema and evidence against stored source text.
- Log model/prompt versions and mark all outputs as draft.

**Deliverables:** Extraction service, candidate-rule records, validation report.

**Exit gate:** Unsupported or untraceable candidates are rejected/flagged and cannot be activated.

### Phase 4 — Human review and rule versioning

**Tasks**
- Build the review queue.
- Display source passage and metadata beside each candidate.
- Implement approve/edit/reject/request-context actions.
- Store reviewer decisions and immutable rule versions.
- Prevent draft/rejected rules from entering evaluation.

**Deliverables:** Review UI, approved rule store, audit trail.

**Exit gate:** Only approved, evidence-linked rules are available to the evaluator.

### Phase 5 — Deterministic evaluator

**Tasks**
- Define the pilot product/activity profile.
- Encode conditions and required facts for the approved pilot rules.
- Implement `PASS`, `CONFLICT`, and `UNKNOWN`.
- Include citations, facts used, and rule/source versions in results.
- Add tests for missing facts, exceptions, and conflicting rules.

**Deliverables:** Evaluator API and explainable report.

**Exit gate:** Identical inputs and rule versions produce identical outputs; missing facts never default to `PASS`.

### Phase 6 — Dashboard and end-to-end demo

**Tasks**
- Display sources and parsing status.
- Display draft and approved rules.
- Enable human review.
- Submit a product profile for evaluation.
- Show results, citations, versions, and unknowns.

**Deliverables:** Working demonstrator and setup documentation.

**Exit gate:** A user can complete the full source-to-report workflow through the application.

### Phase 7 — Quality measurement and expansion

**Tasks**
- Evaluate extraction against a human-annotated gold set.
- Track parser failures, evidence accuracy, reviewer correction rate, and evaluator test results.
- Add a second jurisdiction only after the pilot meets agreed thresholds.
- Add scheduled source checks and change detection.
- Require human review of changed sources/rules.
- Reassess OCR, OPA, and model/runtime upgrades based on measured need.

**Deliverables:** Quality report, regression suite, prioritized expansion backlog.

**Exit gate:** The team can demonstrate measured quality, traceability, and known limitations before increasing coverage.

---

## 12. Testing and Acceptance Criteria

### Source/ingestion
- Official HTML page
- Official text-based PDF
- Duplicate source with identical hash
- Updated source with changed hash
- Unavailable URL / failed download
- Unsupported file type

### Parsing
- Headings and section order preserved
- Table headers remain connected to table rows
- Page/section anchors retained where available
- Scanned PDF fails visibly or uses an explicitly configured OCR route
- Parser warnings are recorded

### Extraction
- Clear obligation
- Conditional rule
- Exception or exemption
- Effective date
- Non-binding explanatory passage
- Insufficient-context passage
- Unsupported model-generated detail

### Review and evaluation
- Draft/rejected rule excluded from evaluation
- Approved rule includes source and reviewer history
- Missing product facts return `UNKNOWN`
- Superseded rule is not silently treated as current
- Conflicting rules are surfaced for review
- Every finding identifies the rule version and source version

### MVP acceptance checklist

- [ ] One jurisdiction and topic defined
- [ ] Official source registry populated
- [ ] Original files preserved with hashes
- [ ] Parsing produces anchored text
- [ ] Docling route tested on representative documents
- [ ] Candidate rules include verbatim evidence
- [ ] Human approval required
- [ ] Approved rules are versioned
- [ ] Evaluator returns explainable `PASS` / `CONFLICT` / `UNKNOWN`
- [ ] End-to-end demo works
- [ ] Limitations and test results documented

---

## 13. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Wrong or unofficial source | Curated regulator source registry; human source review |
| Regulation is outdated or superseded | Preserve retrieval dates, hashes, effective dates, and version history |
| Parser loses exceptions or table context | Structure-aware parsing/chunking, Docling where needed, manual fixtures |
| LLM invents or distorts a rule | Strict schema, quote validation, evidence anchors, human approval |
| Applicability is unclear | Explicit applicability fields; mark unknown; reviewer decision |
| False `PASS` | Deterministic evaluator; missing facts return `UNKNOWN`; narrow MVP scope |
| Scope grows across too many countries | One-jurisdiction vertical slice before expansion |
| Heavy infrastructure delays delivery | Reuse existing stack; defer vLLM/OCR/OPA until justified |

---

## 14. Final Recommended Build Order

**Build in this order:**

1. Country scope + official source registry
2. Ingestion + original document/version preservation
3. ParserRouter + Docling adapter + anchored output
4. LLM candidate extraction + evidence validation
5. Human review + versioned rule database
6. Deterministic compliance evaluator
7. Dashboard + end-to-end demo
8. Quality measurement, source-change monitoring, and additional countries

The most important milestone is not “extract every country's regulations.” It is proving that a small, well-scoped set of official rules can be collected, parsed, verified, approved, and evaluated with full traceability. Expand coverage only after that workflow is reliable.
