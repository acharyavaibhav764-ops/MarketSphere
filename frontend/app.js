/**
 * MochaTrade — Frontend Application Logic
 * Orchestrates Source Ingestion, Human Review Queue, and Deterministic Compliance Evaluation.
 */

// =============================================================================
// Initial State & Pre-Populated Regulatory Data
// =============================================================================

const state = {
  apiBaseUrl: localStorage.getItem('mochatrade_api_url') || 'http://localhost:8000/api/v1',
  mode: localStorage.getItem('mochatrade_mode') || 'demo', // 'demo' | 'live'
  selectedRuleId: null,
  activeFilterStatus: 'all',
  activeFilterJurisdiction: 'all',

  sources: [
  {
    "source_id": "src-us-cftc___nfa",
    "jurisdiction": "United States",
    "regulator": "CFTC / NFA",
    "title": "CFTC Regulation 5.18 & NFA Financial Requirements Section 11",
    "source_type": "TXT",
    "instrument_type": "Regulation",
    "content_hash": "36ac1949c70790b99ec7c2f8e81c64f1f1f1d21e064156770cf137c77cfcda66",
    "source_status": "active",
    "processing_status": "parsed",
    "storage_uri": "sources/src-us-cftc___nfa/US_CFTC_NFA_Forex.txt"
  },
  {
    "source_id": "src-uk-fca",
    "jurisdiction": "United Kingdom",
    "regulator": "FCA",
    "title": "FCA Policy Statement PS19/18 on Restricting Contract for Difference Products",
    "source_type": "TXT",
    "instrument_type": "Policy Statement",
    "content_hash": "fe2b96856785567b5d4e66a73b20986787d275cef0d7f9dc760167f31bf45e73",
    "source_status": "active",
    "processing_status": "parsed",
    "storage_uri": "sources/src-uk-fca/UK_FCA_CFD_PS19_18.txt"
  },
  {
    "source_id": "src-sg-mas",
    "jurisdiction": "Singapore",
    "regulator": "MAS",
    "title": "MAS Notice SFA 04-N15 on Margin Requirements for Contracts for Differences",
    "source_type": "TXT",
    "instrument_type": "Notice",
    "content_hash": "474424da5089ddac420fb69a80f89f9a8901cd695db8c5a8a0d0847febe8104a",
    "source_status": "active",
    "processing_status": "parsed",
    "storage_uri": "sources/src-sg-mas/SG_MAS_CFD_SFA04_N15.txt"
  },
  {
    "source_id": "src-au-asic",
    "jurisdiction": "Australia",
    "regulator": "ASIC",
    "title": "ASIC Corporations (Product Intervention Order — Contracts for Difference) Instrument 2020/986",
    "source_type": "TXT",
    "instrument_type": "Product Intervention Order",
    "content_hash": "a7712ecda3ea9bc4f381a64f2d5e55000545c0ac0a8c96a4105f726a5a99847b",
    "source_status": "active",
    "processing_status": "parsed",
    "storage_uri": "sources/src-au-asic/AU_ASIC_CFD_PI_2020_986.txt"
  },
  {
    "source_id": "src-ch-finma",
    "jurisdiction": "Switzerland",
    "regulator": "FINMA",
    "title": "FINMA Banking Act & Circular 2008/21 for OTC Forex and Derivative Dealers",
    "source_type": "TXT",
    "instrument_type": "Federal Act & Circular",
    "content_hash": "ff44f5dfb0b85b603de4bc8f6124fa98d71e7de879338dc7172e8151ae37bb54",
    "source_status": "active",
    "processing_status": "parsed",
    "storage_uri": "sources/src-ch-finma/CH_FINMA_Banking_Forex.txt"
  },
  {
    "source_id": "src-hk-sfc",
    "jurisdiction": "Hong Kong",
    "regulator": "SFC",
    "title": "SFC Code of Conduct & Securities and Futures (Financial Resources) Rules Type 3",
    "source_type": "TXT",
    "instrument_type": "Ordinance & Rules",
    "content_hash": "f58722ddd289123bb1d7429e53f338238e0fe7237addeb16679f9390ca0ad33c",
    "source_status": "active",
    "processing_status": "parsed",
    "storage_uri": "sources/src-hk-sfc/HK_SFC_LFET_Type3.txt"
  },
  {
    "source_id": "src-jp-jfsa",
    "jurisdiction": "Japan",
    "regulator": "JFSA",
    "title": "JFSA Cabinet Office Ordinance on Financial Instruments Business Article 117",
    "source_type": "TXT",
    "instrument_type": "Cabinet Office Ordinance",
    "content_hash": "bc4120aeefd2b4d6279ba66d52054368390a1c276fa44e21e57c47734a5e4666",
    "source_status": "active",
    "processing_status": "parsed",
    "storage_uri": "sources/src-jp-jfsa/JP_JFSA_Cabinet_FIBO.txt"
  },
  {
    "source_id": "src-in-rbi___sebi",
    "jurisdiction": "India",
    "regulator": "RBI / SEBI",
    "title": "RBI Foreign Exchange Management Act (FEMA 1999) & SEBI Currency Regulations",
    "source_type": "TXT",
    "instrument_type": "Statutory Act & Circular",
    "content_hash": "70cd18055dab2a869beee14f734913919f48da1698d6bc998050ccf512fb9c3e",
    "source_status": "active",
    "processing_status": "parsed",
    "storage_uri": "sources/src-in-rbi___sebi/IN_RBI_SEBI_FEMA_Currency.txt"
  },
  {
    "source_id": "src-ae-vara",
    "jurisdiction": "United Arab Emirates",
    "regulator": "VARA",
    "title": "Dubai Virtual Assets Market Conduct Rulebook 2024",
    "source_type": "TXT",
    "instrument_type": "Rulebook",
    "content_hash": "09485013ce428c3025fba6501884450e8522a9483b48dfed45baff156984e895",
    "source_status": "active",
    "processing_status": "parsed",
    "storage_uri": "sources/src-ae-vara/AE_VARA_Market_Conduct_2024.txt"
  },
  {
    "source_id": "src-ca-ciro",
    "jurisdiction": "Canada",
    "regulator": "CIRO",
    "title": "CIRO IDPC Rules Section 5460 on Retail Forex Margin Requirements",
    "source_type": "TXT",
    "instrument_type": "Rules",
    "content_hash": "634a60839e38dffdd12377e2a3c9e6d4c70902356d093ce6789c1a4dd95c3645",
    "source_status": "active",
    "processing_status": "parsed",
    "storage_uri": "sources/src-ca-ciro/CA_CIRO_IDPC_Rule_5460.txt"
  },
  {
    "source_id": "src-fr-amf",
    "jurisdiction": "France",
    "regulator": "AMF",
    "title": "AMF General Regulation Article 314-77 & Sapin II Law on Retail CFDs",
    "source_type": "TXT",
    "instrument_type": "Regulation",
    "content_hash": "f813ba39057d76de228cb830454164b0a21c0d54a791cf0ae47b654b4794394f",
    "source_status": "active",
    "processing_status": "parsed",
    "storage_uri": "sources/src-fr-amf/FR_AMF_ESMA_MiFIR_CFD.txt"
  },
  {
    "source_id": "src-de-bafin",
    "jurisdiction": "Germany",
    "regulator": "BaFin",
    "title": "BaFin Allgemeinverfügung über CFDs (2019) & Wertpapierinstitutsgesetz WpIG",
    "source_type": "TXT",
    "instrument_type": "General Administrative Act & Act",
    "content_hash": "325d4ff173979b848e04dad39b44bcb7c9a6625296ddc6527560fb2d8432bcf7",
    "source_status": "active",
    "processing_status": "parsed",
    "storage_uri": "sources/src-de-bafin/DE_BaFin_WpIG_CFD.txt"
  },
  {
    "source_id": "src-nl-afm",
    "jurisdiction": "Netherlands",
    "regulator": "AFM",
    "title": "AFM Beleidsregel CFD & Besluit gedragstoezicht financiële ondernemingen Bgfo",
    "source_type": "TXT",
    "instrument_type": "Policy Rule & Decree",
    "content_hash": "d6359a412812b0aea6c793a7adac8d9e6e1ca1b6857b4189987a12ce503d1a90",
    "source_status": "active",
    "processing_status": "parsed",
    "storage_uri": "sources/src-nl-afm/NL_AFM_Bgfo_CFD.txt"
  },
  {
    "source_id": "src-kr-fsc___fss",
    "jurisdiction": "South Korea",
    "regulator": "FSC / FSS",
    "title": "FSC Financial Investment Services and Capital Markets Act Enforcement Decree",
    "source_type": "TXT",
    "instrument_type": "Enforcement Decree",
    "content_hash": "b090b0301c64e1b85310759402523c741dd02a6905cab987d606173e4d6b966a",
    "source_status": "active",
    "processing_status": "parsed",
    "storage_uri": "sources/src-kr-fsc___fss/KR_FSC_FX_Margin_2012.txt"
  },
  {
    "source_id": "src-br-cvm___bcb",
    "jurisdiction": "Brazil",
    "regulator": "CVM / BCB",
    "title": "CVM Deliberação 818 & BCB Resolução 4.924 for Virtual Assets and Margin",
    "source_type": "TXT",
    "instrument_type": "Resolution & Deliberation",
    "content_hash": "a2b6439784dcee6e60175b5e42ac26034bf1d49e95c9b5230eeee63e3020eebe",
    "source_status": "active",
    "processing_status": "parsed",
    "storage_uri": "sources/src-br-cvm___bcb/BR_CVM_BCB_Res_4924.txt"
  }
],

  rules: [
  {
    "rule_id": "us-cftc-lev-001",
    "rule_version": 1,
    "source_id": "src-us-cftc___nfa",
    "jurisdiction": "United States",
    "regulator": "CFTC / NFA",
    "topic": "leverage",
    "obligation": "Major currency pairs retail leverage is capped at 1:50; non-major pairs capped at 1:20.",
    "supporting_quote": "Major currency pairs retail leverage is capped at 1:50 (2 percent margin requirement).",
    "required_capital_usd": null,
    "leverage_cap_retail": "1:50",
    "presence_friction_summary": null,
    "evidence_tag": "Verified Fact",
    "review_status": "approved",
    "reviewer_id": "compliance.officer@mochatrade.io",
    "reviewed_at": "2026-09-25T10:50:46.722Z",
    "page_number": 1,
    "section_heading": "Section 1",
    "extraction_model": "legal-parser-v5"
  },
  {
    "rule_id": "us-cftc-cap-002",
    "rule_version": 1,
    "source_id": "src-us-cftc___nfa",
    "jurisdiction": "United States",
    "regulator": "CFTC / NFA",
    "topic": "capital",
    "obligation": "RFED and FCM dealers must maintain adjusted net capital of at least USD 20,000,000.",
    "supporting_quote": "Retail foreign exchange dealers (RFEDs) and futures commission merchants (FCMs) must maintain adjusted net capital of not less than $20,000,000.",
    "required_capital_usd": 20000000,
    "leverage_cap_retail": null,
    "presence_friction_summary": null,
    "evidence_tag": "Verified Fact",
    "review_status": "approved",
    "reviewer_id": "compliance.officer@mochatrade.io",
    "reviewed_at": "2026-09-25T10:50:46.722Z",
    "page_number": 1,
    "section_heading": "Section 1",
    "extraction_model": "legal-parser-v5"
  },
  {
    "rule_id": "us-cftc-pres-003",
    "rule_version": 1,
    "source_id": "src-us-cftc___nfa",
    "jurisdiction": "United States",
    "regulator": "CFTC / NFA",
    "topic": "presence",
    "obligation": "Must maintain domestic operational office and Chief Compliance Officer in the United States.",
    "supporting_quote": "Registration as a Retail Foreign Exchange Dealer requires maintaining domestic operational office and Chief Compliance Officer in the United States.",
    "required_capital_usd": null,
    "leverage_cap_retail": null,
    "presence_friction_summary": "Mandatory US operational office and designated US resident CCO",
    "evidence_tag": "Verified Fact",
    "review_status": "approved",
    "reviewer_id": "compliance.officer@mochatrade.io",
    "reviewed_at": "2026-09-25T10:50:46.722Z",
    "page_number": 1,
    "section_heading": "Section 1",
    "extraction_model": "legal-parser-v5"
  },
  {
    "rule_id": "uk-fca-lev-001",
    "rule_version": 1,
    "source_id": "src-uk-fca",
    "jurisdiction": "United Kingdom",
    "regulator": "FCA",
    "topic": "leverage",
    "obligation": "Retail CFD leverage restricted to 1:30 for major currencies and 1:20 for non-major pairs.",
    "supporting_quote": "Firms selling CFDs to retail clients must restrict retail leverage to 1:30 for major currency pairs and 1:20 for non-major currency pairs.",
    "required_capital_usd": null,
    "leverage_cap_retail": "1:30",
    "presence_friction_summary": null,
    "evidence_tag": "Verified Fact",
    "review_status": "approved",
    "reviewer_id": "compliance.officer@mochatrade.io",
    "reviewed_at": "2026-09-25T10:50:46.723Z",
    "page_number": 1,
    "section_heading": "Section 1",
    "extraction_model": "legal-parser-v5"
  },
  {
    "rule_id": "uk-fca-cap-002",
    "rule_version": 1,
    "source_id": "src-uk-fca",
    "jurisdiction": "United Kingdom",
    "regulator": "FCA",
    "topic": "capital",
    "obligation": "Investment firm dealing on own account must hold initial capital of EUR 750,000 (~USD 815,000).",
    "supporting_quote": "Investment firms authorized under UK MiFID must hold initial capital of at least EUR 750,000 (or equivalent in GBP).",
    "required_capital_usd": 815000,
    "leverage_cap_retail": null,
    "presence_friction_summary": null,
    "evidence_tag": "Verified Fact",
    "review_status": "approved",
    "reviewer_id": "compliance.officer@mochatrade.io",
    "reviewed_at": "2026-09-25T10:50:46.723Z",
    "page_number": 1,
    "section_heading": "Section 1",
    "extraction_model": "legal-parser-v5"
  },
  {
    "rule_id": "sg-mas-lev-001",
    "rule_version": 1,
    "source_id": "src-sg-mas",
    "jurisdiction": "Singapore",
    "regulator": "MAS",
    "topic": "leverage",
    "obligation": "Retail CFD forex leverage is capped at 1:20 (5% margin).",
    "supporting_quote": "The margin requirement for retail contracts for differences (CFDs) on foreign exchange is minimum 5 percent, restricting maximum retail leverage to 1:20.",
    "required_capital_usd": null,
    "leverage_cap_retail": "1:20",
    "presence_friction_summary": null,
    "evidence_tag": "Verified Fact",
    "review_status": "approved",
    "reviewer_id": "compliance.officer@mochatrade.io",
    "reviewed_at": "2026-09-25T10:50:46.725Z",
    "page_number": 1,
    "section_heading": "Section 1",
    "extraction_model": "legal-parser-v5"
  },
  {
    "rule_id": "sg-mas-cap-002",
    "rule_version": 1,
    "source_id": "src-sg-mas",
    "jurisdiction": "Singapore",
    "regulator": "MAS",
    "topic": "capital",
    "obligation": "CMS license holder dealing in OTC products must maintain SGD 1,000,000 (~USD 750,000) base capital.",
    "supporting_quote": "Capital Markets Services (CMS) license holders dealing in capital markets products must maintain minimum base capital of SGD 1,000,000.",
    "required_capital_usd": 750000,
    "leverage_cap_retail": null,
    "presence_friction_summary": null,
    "evidence_tag": "Verified Fact",
    "review_status": "approved",
    "reviewer_id": "compliance.officer@mochatrade.io",
    "reviewed_at": "2026-09-25T10:50:46.725Z",
    "page_number": 1,
    "section_heading": "Section 1",
    "extraction_model": "legal-parser-v5"
  },
  {
    "rule_id": "sg-mas-pres-003",
    "rule_version": 1,
    "source_id": "src-sg-mas",
    "jurisdiction": "Singapore",
    "regulator": "MAS",
    "topic": "presence",
    "obligation": "At least two executive directors must reside in Singapore.",
    "supporting_quote": "Applicant must maintain local operational management presence in Singapore with at least two executive directors resident in Singapore.",
    "required_capital_usd": null,
    "leverage_cap_retail": null,
    "presence_friction_summary": "Minimum 2 resident Singapore executive directors",
    "evidence_tag": "Verified Fact",
    "review_status": "approved",
    "reviewer_id": "compliance.officer@mochatrade.io",
    "reviewed_at": "2026-09-25T10:50:46.725Z",
    "page_number": 1,
    "section_heading": "Section 1",
    "extraction_model": "legal-parser-v5"
  },
  {
    "rule_id": "au-asic-lev-001",
    "rule_version": 1,
    "source_id": "src-au-asic",
    "jurisdiction": "Australia",
    "regulator": "ASIC",
    "topic": "leverage",
    "obligation": "Retail leverage capped at 1:30 for major currencies and 1:20 for minor pairs.",
    "supporting_quote": "CFD issuers are prohibited from giving retail clients leverage exceeding 1:30 for major currency pairs and 1:20 for minor currency pairs.",
    "required_capital_usd": null,
    "leverage_cap_retail": "1:30",
    "presence_friction_summary": null,
    "evidence_tag": "Verified Fact",
    "review_status": "approved",
    "reviewer_id": "compliance.officer@mochatrade.io",
    "reviewed_at": "2026-09-25T10:50:46.725Z",
    "page_number": 1,
    "section_heading": "Section 1",
    "extraction_model": "legal-parser-v5"
  },
  {
    "rule_id": "au-asic-cap-002",
    "rule_version": 1,
    "source_id": "src-au-asic",
    "jurisdiction": "Australia",
    "regulator": "ASIC",
    "topic": "capital",
    "obligation": "AFSL OTC derivative dealers must hold minimum AUD 1,000,000 (~USD 650,000) surplus liquid funds.",
    "supporting_quote": "Australian Financial Services Licensee (AFSL) dealing in OTC derivatives must maintain minimum surplus liquid funds of AUD 1,000,000.",
    "required_capital_usd": 650000,
    "leverage_cap_retail": null,
    "presence_friction_summary": null,
    "evidence_tag": "Verified Fact",
    "review_status": "approved",
    "reviewer_id": "compliance.officer@mochatrade.io",
    "reviewed_at": "2026-09-25T10:50:46.725Z",
    "page_number": 1,
    "section_heading": "Section 1",
    "extraction_model": "legal-parser-v5"
  },
  {
    "rule_id": "ch-finma-cap-001",
    "rule_version": 1,
    "source_id": "src-ch-finma",
    "jurisdiction": "Switzerland",
    "regulator": "FINMA",
    "topic": "capital",
    "obligation": "Must hold banking license with minimum statutory capital of CHF 10,000,000 (~USD 11,500,000).",
    "supporting_quote": "Entities conducting public retail foreign exchange and CFD trading on a commercial basis must obtain a banking license with minimum capital of CHF 10,000,000.",
    "required_capital_usd": 11500000,
    "leverage_cap_retail": null,
    "presence_friction_summary": "Full Swiss Banking License required for retail forex",
    "evidence_tag": "Verified Fact",
    "review_status": "approved",
    "reviewer_id": "compliance.officer@mochatrade.io",
    "reviewed_at": "2026-09-25T10:50:46.725Z",
    "page_number": 1,
    "section_heading": "Section 1",
    "extraction_model": "legal-parser-v5"
  },
  {
    "rule_id": "ch-finma-lev-002",
    "rule_version": 1,
    "source_id": "src-ch-finma",
    "jurisdiction": "Switzerland",
    "regulator": "FINMA",
    "topic": "leverage",
    "obligation": "Effective retail client leverage restricted to maximum ratio of 1:30.",
    "supporting_quote": "Internal risk-based margin framework restricts effective retail client leverage to a maximum ratio of 1:30 for currency pairs.",
    "required_capital_usd": null,
    "leverage_cap_retail": "1:30",
    "presence_friction_summary": null,
    "evidence_tag": "Verified Fact",
    "review_status": "approved",
    "reviewer_id": "compliance.officer@mochatrade.io",
    "reviewed_at": "2026-09-25T10:50:46.725Z",
    "page_number": 1,
    "section_heading": "Section 1",
    "extraction_model": "legal-parser-v5"
  },
  {
    "rule_id": "hk-sfc-lev-001",
    "rule_version": 1,
    "source_id": "src-hk-sfc",
    "jurisdiction": "Hong Kong",
    "regulator": "SFC",
    "topic": "leverage",
    "obligation": "Type 3 leveraged forex trading leverage is capped at 1:20.",
    "supporting_quote": "Licensed corporations under Type 3 regulated activity shall observe a maximum leverage ratio of 1:20 (5 percent initial margin) for leveraged foreign exchange contracts.",
    "required_capital_usd": null,
    "leverage_cap_retail": "1:20",
    "presence_friction_summary": null,
    "evidence_tag": "Verified Fact",
    "review_status": "approved",
    "reviewer_id": "compliance.officer@mochatrade.io",
    "reviewed_at": "2026-09-25T10:50:46.726Z",
    "page_number": 1,
    "section_heading": "Section 1",
    "extraction_model": "legal-parser-v5"
  },
  {
    "rule_id": "hk-sfc-cap-002",
    "rule_version": 1,
    "source_id": "src-hk-sfc",
    "jurisdiction": "Hong Kong",
    "regulator": "SFC",
    "topic": "capital",
    "obligation": "Type 3 licensed corporation must maintain paid-up capital of HKD 30,000,000 (~USD 3,850,000).",
    "supporting_quote": "A Type 3 licensed corporation dealing in leveraged foreign exchange must maintain paid-up share capital of not less than HKD 30,000,000.",
    "required_capital_usd": 3850000,
    "leverage_cap_retail": null,
    "presence_friction_summary": null,
    "evidence_tag": "Verified Fact",
    "review_status": "approved",
    "reviewer_id": "compliance.officer@mochatrade.io",
    "reviewed_at": "2026-09-25T10:50:46.726Z",
    "page_number": 1,
    "section_heading": "Section 1",
    "extraction_model": "legal-parser-v5"
  },
  {
    "rule_id": "jp-jfsa-lev-001",
    "rule_version": 1,
    "source_id": "src-jp-jfsa",
    "jurisdiction": "Japan",
    "regulator": "JFSA",
    "topic": "leverage",
    "obligation": "Retail FX margin trading leverage is capped at 1:25 (4% margin).",
    "supporting_quote": "Margin trading for retail individual customers on foreign exchange transactions is strictly capped at a leverage ratio of 1:25 (4 percent margin).",
    "required_capital_usd": null,
    "leverage_cap_retail": "1:25",
    "presence_friction_summary": null,
    "evidence_tag": "Verified Fact",
    "review_status": "approved",
    "reviewer_id": "compliance.officer@mochatrade.io",
    "reviewed_at": "2026-09-25T10:50:46.726Z",
    "page_number": 1,
    "section_heading": "Section 1",
    "extraction_model": "legal-parser-v5"
  },
  {
    "rule_id": "jp-jfsa-cap-002",
    "rule_version": 1,
    "source_id": "src-jp-jfsa",
    "jurisdiction": "Japan",
    "regulator": "JFSA",
    "topic": "capital",
    "obligation": "Type I FIBO must maintain minimum net assets of JPY 50,000,000 (~USD 335,000).",
    "supporting_quote": "Type I Financial Instruments Business Operators must maintain minimum net assets of JPY 50,000,000 and capital adequacy ratio of at least 120 percent.",
    "required_capital_usd": 335000,
    "leverage_cap_retail": null,
    "presence_friction_summary": null,
    "evidence_tag": "Verified Fact",
    "review_status": "approved",
    "reviewer_id": "compliance.officer@mochatrade.io",
    "reviewed_at": "2026-09-25T10:50:46.726Z",
    "page_number": 1,
    "section_heading": "Section 1",
    "extraction_model": "legal-parser-v5"
  },
  {
    "rule_id": "in-rbi-fema-001",
    "rule_version": 1,
    "source_id": "src-in-rbi___sebi",
    "jurisdiction": "India",
    "regulator": "RBI / SEBI",
    "topic": "leverage",
    "obligation": "Resident retail margin trading on unauthorized offshore portals is prohibited under FEMA; domestic futures capped at 1:20.",
    "supporting_quote": "Permitted exchange-traded currency futures on recognized Indian exchanges require initial margin of 2.5 to 5 percent, permitting leverage up to 1:20.",
    "required_capital_usd": null,
    "leverage_cap_retail": "1:20",
    "presence_friction_summary": "Overseas CFD brokers prohibited from soliciting Indian residents; domestic SEBI entity mandatory",
    "evidence_tag": "Verified Fact",
    "review_status": "approved",
    "reviewer_id": "compliance.officer@mochatrade.io",
    "reviewed_at": "2026-09-25T10:50:46.726Z",
    "page_number": 1,
    "section_heading": "Section 1",
    "extraction_model": "legal-parser-v5"
  },
  {
    "rule_id": "in-sebi-cap-002",
    "rule_version": 1,
    "source_id": "src-in-rbi___sebi",
    "jurisdiction": "India",
    "regulator": "RBI / SEBI",
    "topic": "capital",
    "obligation": "Currency derivative clearing members must maintain net worth of INR 300,000,000 (~USD 3,600,000).",
    "supporting_quote": "Trading and clearing members in currency derivatives segment must maintain Base Minimum Capital and net worth of at least INR 300,000,000 (INR 30 Crore).",
    "required_capital_usd": 3600000,
    "leverage_cap_retail": null,
    "presence_friction_summary": null,
    "evidence_tag": "Verified Fact",
    "review_status": "approved",
    "reviewer_id": "compliance.officer@mochatrade.io",
    "reviewed_at": "2026-09-25T10:50:46.726Z",
    "page_number": 1,
    "section_heading": "Section 1",
    "extraction_model": "legal-parser-v5"
  },
  {
    "rule_id": "ae-vara-lev-001",
    "rule_version": 1,
    "source_id": "src-ae-vara",
    "jurisdiction": "United Arab Emirates",
    "regulator": "VARA",
    "topic": "leverage",
    "obligation": "Retail derivative leverage capped at 1:5.",
    "supporting_quote": "Retail leverage is strictly capped at 1:5 for virtual asset derivatives and margin contracts.",
    "required_capital_usd": null,
    "leverage_cap_retail": "1:5",
    "presence_friction_summary": null,
    "evidence_tag": "Verified Fact",
    "review_status": "approved",
    "reviewer_id": "compliance.officer@mochatrade.io",
    "reviewed_at": "2026-09-25T10:50:46.727Z",
    "page_number": 1,
    "section_heading": "Section 1",
    "extraction_model": "legal-parser-v5"
  },
  {
    "rule_id": "ae-vara-cap-002",
    "rule_version": 1,
    "source_id": "src-ae-vara",
    "jurisdiction": "United Arab Emirates",
    "regulator": "VARA",
    "topic": "capital",
    "obligation": "Broker-dealer licensees must maintain USD 500,000 paid-up statutory capital.",
    "supporting_quote": "Licensees offering broker-dealer services must maintain paid-up statutory capital of not less than USD 500,000 (AED 1,835,000).",
    "required_capital_usd": 500000,
    "leverage_cap_retail": null,
    "presence_friction_summary": "Dubai registered office and resident executive directors required",
    "evidence_tag": "Verified Fact",
    "review_status": "approved",
    "reviewer_id": "compliance.officer@mochatrade.io",
    "reviewed_at": "2026-09-25T10:50:46.727Z",
    "page_number": 1,
    "section_heading": "Section 1",
    "extraction_model": "legal-parser-v5"
  },
  {
    "rule_id": "ca-ciro-lev-001",
    "rule_version": 1,
    "source_id": "src-ca-ciro",
    "jurisdiction": "Canada",
    "regulator": "CIRO",
    "topic": "leverage",
    "obligation": "Retail forex margin for major currencies restricted to 3.33% (1:30 leverage cap).",
    "supporting_quote": "Dealer members must require retail clients to post spot risk margin of at least 3.33 percent for Group 1 major currencies, restricting leverage to 1:30.",
    "required_capital_usd": null,
    "leverage_cap_retail": "1:30",
    "presence_friction_summary": null,
    "evidence_tag": "Verified Fact",
    "review_status": "approved",
    "reviewer_id": "compliance.officer@mochatrade.io",
    "reviewed_at": "2026-09-25T10:50:46.727Z",
    "page_number": 1,
    "section_heading": "Section 1",
    "extraction_model": "legal-parser-v5"
  },
  {
    "rule_id": "ca-ciro-cap-002",
    "rule_version": 1,
    "source_id": "src-ca-ciro",
    "jurisdiction": "Canada",
    "regulator": "CIRO",
    "topic": "capital",
    "obligation": "Tier 1 investment dealer must maintain minimum regulatory capital of CAD 1,000,000 (~USD 740,000).",
    "supporting_quote": "Investment dealers must maintain minimum regulatory capital of CAD 1,000,000 (Tier 1 dealer) or CAD 250,000.",
    "required_capital_usd": 740000,
    "leverage_cap_retail": null,
    "presence_friction_summary": "Registration with provincial securities commission and CIPF participation",
    "evidence_tag": "Verified Fact",
    "review_status": "approved",
    "reviewer_id": "compliance.officer@mochatrade.io",
    "reviewed_at": "2026-09-25T10:50:46.727Z",
    "page_number": 1,
    "section_heading": "Section 1",
    "extraction_model": "legal-parser-v5"
  },
  {
    "rule_id": "fr-amf-lev-001",
    "rule_version": 1,
    "source_id": "src-fr-amf",
    "jurisdiction": "France",
    "regulator": "AMF",
    "topic": "leverage",
    "obligation": "Retail CFD leverage capped at 1:30 for major currency pairs and 1:20 for minor pairs.",
    "supporting_quote": "Marketing and distribution of CFDs to retail clients is limited to maximum leverage of 1:30 for major exchange rates and 1:20 for other currency pairs.",
    "required_capital_usd": null,
    "leverage_cap_retail": "1:30",
    "presence_friction_summary": "Sapin II law prohibits digital advertising for CFDs with leverage above 1:5",
    "evidence_tag": "Verified Fact",
    "review_status": "approved",
    "reviewer_id": "compliance.officer@mochatrade.io",
    "reviewed_at": "2026-09-25T10:50:46.728Z",
    "page_number": 1,
    "section_heading": "Section 1",
    "extraction_model": "legal-parser-v5"
  },
  {
    "rule_id": "fr-amf-cap-002",
    "rule_version": 1,
    "source_id": "src-fr-amf",
    "jurisdiction": "France",
    "regulator": "AMF",
    "topic": "capital",
    "obligation": "Authorized investment firms must maintain initial capital of EUR 750,000 (~USD 815,000).",
    "supporting_quote": "Investment firms authorized by ACPR/AMF must maintain minimum initial capital of EUR 750,000.",
    "required_capital_usd": 815000,
    "leverage_cap_retail": null,
    "presence_friction_summary": null,
    "evidence_tag": "Verified Fact",
    "review_status": "approved",
    "reviewer_id": "compliance.officer@mochatrade.io",
    "reviewed_at": "2026-09-25T10:50:46.728Z",
    "page_number": 1,
    "section_heading": "Section 1",
    "extraction_model": "legal-parser-v5"
  },
  {
    "rule_id": "de-bafin-lev-001",
    "rule_version": 1,
    "source_id": "src-de-bafin",
    "jurisdiction": "Germany",
    "regulator": "BaFin",
    "topic": "leverage",
    "obligation": "Retail CFD leverage restricted to 1:30 for major currencies and 1:20 for minor pairs.",
    "supporting_quote": "Marketing, distribution and sale of contracts for difference to retail clients is restricted to maximum leverage of 1:30 for major forex pairs and 1:20 for minor forex.",
    "required_capital_usd": null,
    "leverage_cap_retail": "1:30",
    "presence_friction_summary": null,
    "evidence_tag": "Verified Fact",
    "review_status": "approved",
    "reviewer_id": "compliance.officer@mochatrade.io",
    "reviewed_at": "2026-09-25T10:50:46.728Z",
    "page_number": 1,
    "section_heading": "Section 1",
    "extraction_model": "legal-parser-v5"
  },
  {
    "rule_id": "de-bafin-cap-002",
    "rule_version": 1,
    "source_id": "src-de-bafin",
    "jurisdiction": "Germany",
    "regulator": "BaFin",
    "topic": "capital",
    "obligation": "Wertpapierinstitute dealing on own account must maintain EUR 750,000 (~USD 815,000) initial capital.",
    "supporting_quote": "Medium and large investment firms under the German WpIG must hold minimum initial regulatory capital of EUR 750,000.",
    "required_capital_usd": 815000,
    "leverage_cap_retail": null,
    "presence_friction_summary": "Complete exclusion of retail client additional margin payment obligations",
    "evidence_tag": "Verified Fact",
    "review_status": "approved",
    "reviewer_id": "compliance.officer@mochatrade.io",
    "reviewed_at": "2026-09-25T10:50:46.728Z",
    "page_number": 1,
    "section_heading": "Section 1",
    "extraction_model": "legal-parser-v5"
  },
  {
    "rule_id": "nl-afm-lev-001",
    "rule_version": 1,
    "source_id": "src-nl-afm",
    "jurisdiction": "Netherlands",
    "regulator": "AFM",
    "topic": "leverage",
    "obligation": "Retail CFD leverage capped at 1:30 for major currencies and 1:20 for non-major currencies.",
    "supporting_quote": "The offering of CFDs to non-professional clients is subject to leverage caps of 1:30 for major currencies and 1:20 for non-major currencies.",
    "required_capital_usd": null,
    "leverage_cap_retail": "1:30",
    "presence_friction_summary": null,
    "evidence_tag": "Verified Fact",
    "review_status": "approved",
    "reviewer_id": "compliance.officer@mochatrade.io",
    "reviewed_at": "2026-09-25T10:50:46.729Z",
    "page_number": 1,
    "section_heading": "Section 1",
    "extraction_model": "legal-parser-v5"
  },
  {
    "rule_id": "nl-afm-cap-002",
    "rule_version": 1,
    "source_id": "src-nl-afm",
    "jurisdiction": "Netherlands",
    "regulator": "AFM",
    "topic": "capital",
    "obligation": "Investment firm trading on own account must maintain EUR 750,000 (~USD 815,000) initial capital.",
    "supporting_quote": "Investment firms holding client money and trading on own account must maintain initial capital of at least EUR 750,000.",
    "required_capital_usd": 815000,
    "leverage_cap_retail": null,
    "presence_friction_summary": "Strict prohibition of bonuses and marketing inducements",
    "evidence_tag": "Verified Fact",
    "review_status": "approved",
    "reviewer_id": "compliance.officer@mochatrade.io",
    "reviewed_at": "2026-09-25T10:50:46.729Z",
    "page_number": 1,
    "section_heading": "Section 1",
    "extraction_model": "legal-parser-v5"
  },
  {
    "rule_id": "kr-fsc-lev-001",
    "rule_version": 1,
    "source_id": "src-kr-fsc___fss",
    "jurisdiction": "South Korea",
    "regulator": "FSC / FSS",
    "topic": "leverage",
    "obligation": "Retail FX margin trading leverage is capped at 1:10 (10% margin).",
    "supporting_quote": "Retail FX margin trading leverage is strictly capped at 1:10 (10 percent margin requirement) for individual retail investors.",
    "required_capital_usd": null,
    "leverage_cap_retail": "1:10",
    "presence_friction_summary": null,
    "evidence_tag": "Verified Fact",
    "review_status": "approved",
    "reviewer_id": "compliance.officer@mochatrade.io",
    "reviewed_at": "2026-09-25T10:50:46.729Z",
    "page_number": 1,
    "section_heading": "Section 1",
    "extraction_model": "legal-parser-v5"
  },
  {
    "rule_id": "kr-fsc-cap-002",
    "rule_version": 1,
    "source_id": "src-kr-fsc___fss",
    "jurisdiction": "South Korea",
    "regulator": "FSC / FSS",
    "topic": "capital",
    "obligation": "OTC derivative brokers must hold minimum KRW 3,000,000,000 (~USD 2,300,000) capital.",
    "supporting_quote": "Financial investment brokers dealing in OTC derivatives must possess minimum equity capital of KRW 3,000,000,000 (approx USD 2,300,000).",
    "required_capital_usd": 2300000,
    "leverage_cap_retail": null,
    "presence_friction_summary": "Unregistered foreign broker solicitation prohibited under FSCMA",
    "evidence_tag": "Verified Fact",
    "review_status": "approved",
    "reviewer_id": "compliance.officer@mochatrade.io",
    "reviewed_at": "2026-09-25T10:50:46.729Z",
    "page_number": 1,
    "section_heading": "Section 1",
    "extraction_model": "legal-parser-v5"
  },
  {
    "rule_id": "br-cvm-lev-001",
    "rule_version": 1,
    "source_id": "src-br-cvm___bcb",
    "jurisdiction": "Brazil",
    "regulator": "CVM / BCB",
    "topic": "leverage",
    "obligation": "Retail customer margin leverage capped at 1:20.",
    "supporting_quote": "Retail customer margin leverage shall not exceed ratio of 1:20 across all registered instruments and currency contracts.",
    "required_capital_usd": null,
    "leverage_cap_retail": "1:20",
    "presence_friction_summary": null,
    "evidence_tag": "Verified Fact",
    "review_status": "approved",
    "reviewer_id": "compliance.officer@mochatrade.io",
    "reviewed_at": "2026-09-25T10:50:46.729Z",
    "page_number": 1,
    "section_heading": "Section 1",
    "extraction_model": "legal-parser-v5"
  },
  {
    "rule_id": "br-cvm-cap-002",
    "rule_version": 1,
    "source_id": "src-br-cvm___bcb",
    "jurisdiction": "Brazil",
    "regulator": "CVM / BCB",
    "topic": "capital",
    "obligation": "VASPs and derivative dealers must maintain capital reserve of BRL 3,000,000 (~USD 600,000).",
    "supporting_quote": "Entities operating as virtual asset service providers or derivative dealers must maintain capital reserve of BRL 3,000,000 (USD ~600,000).",
    "required_capital_usd": 600000,
    "leverage_cap_retail": null,
    "presence_friction_summary": "Mandatory Brazilian CNPJ entity and designated resident representative",
    "evidence_tag": "Verified Fact",
    "review_status": "approved",
    "reviewer_id": "compliance.officer@mochatrade.io",
    "reviewed_at": "2026-09-25T10:50:46.729Z",
    "page_number": 1,
    "section_heading": "Section 1",
    "extraction_model": "legal-parser-v5"
  }
]
};

// =============================================================================
// DOM Elements
// =============================================================================

const elements = {
  // Navigation
  navTabs: document.querySelectorAll('.nav-tab'),
  tabPanels: document.querySelectorAll('.tab-panel'),

  // Config modal
  configModal: document.getElementById('config-modal'),
  settingsToggleBtn: document.getElementById('settings-toggle-btn'),
  configCloseBtn: document.getElementById('config-close-btn'),
  apiBaseUrlInput: document.getElementById('api-base-url-input'),
  apiModeSelect: document.getElementById('api-mode-select'),
  testConnectionBtn: document.getElementById('test-connection-btn'),
  saveConfigBtn: document.getElementById('save-config-btn'),
  apiStatusDot: document.getElementById('api-status-dot'),
  apiStatusText: document.getElementById('api-status-text'),

  // Evaluator
  evalForm: document.getElementById('evaluator-form'),
  evalJurisdiction: document.getElementById('eval-jurisdiction'),
  evalProductType: document.getElementById('eval-product-type'),
  evalCapital: document.getElementById('eval-capital'),
  evalLeverage: document.getElementById('eval-leverage'),
  evalClearBtn: document.getElementById('btn-clear-eval'),
  verdictBanner: document.getElementById('verdict-banner'),
  verdictStatusIcon: document.getElementById('verdict-status-icon'),
  verdictTitle: document.getElementById('verdict-title'),
  verdictSummary: document.getElementById('verdict-summary'),
  evalVerdictBadge: document.getElementById('eval-verdict-badge'),
  evalRuleCardsList: document.getElementById('eval-rule-cards-list'),
  presetBtns: document.querySelectorAll('.preset-btn'),

  // Review Queue
  reviewStatusFilter: document.getElementById('review-status-filter'),
  reviewJurisdictionFilter: document.getElementById('review-jurisdiction-filter'),
  ruleQueueList: document.getElementById('rule-queue-list'),
  reviewInspector: document.getElementById('review-inspector'),
  queueBadgeCount: document.getElementById('queue-badge-count'),
  reviewRuleCount: document.getElementById('review-rule-count'),

  // Edit Modal
  editRuleModal: document.getElementById('edit-rule-modal'),
  editRuleCloseBtn: document.getElementById('edit-rule-close-btn'),
  editRuleCancelBtn: document.getElementById('edit-rule-cancel-btn'),
  editRuleForm: document.getElementById('edit-rule-form'),
  editRuleId: document.getElementById('edit-rule-id'),
  editRuleTopic: document.getElementById('edit-rule-topic'),
  editRuleObligation: document.getElementById('edit-rule-obligation'),
  editRuleLeverage: document.getElementById('edit-rule-leverage'),
  editRuleCapital: document.getElementById('edit-rule-capital'),
  editRuleEvidence: document.getElementById('edit-rule-evidence'),
  editRuleReviewer: document.getElementById('edit-rule-reviewer'),

  // Source Ingestion
  sourceForm: document.getElementById('source-ingest-form'),
  sourceJurisdiction: document.getElementById('source-jurisdiction'),
  sourceRegulator: document.getElementById('source-regulator'),
  sourceTitle: document.getElementById('source-title'),
  sourceType: document.getElementById('source-type'),
  sourceInstrument: document.getElementById('source-instrument'),
  sourceUrl: document.getElementById('source-url'),
  fileDropzone: document.getElementById('file-dropzone'),
  sourceFileInput: document.getElementById('source-file-input'),
  filePreviewCard: document.getElementById('file-preview-card'),
  previewFilename: document.getElementById('preview-filename'),
  previewHash: document.getElementById('preview-hash'),
  removeFileBtn: document.getElementById('remove-file-btn'),
  sourceRegistryList: document.getElementById('source-registry-list'),

  // Toast
  toast: document.getElementById('toast'),
};

let uploadedFileBytes = null;
let currentComputedHash = null;

// =============================================================================
// Initialization
// =============================================================================

function init() {
  setupNavigation();
  setupConfigModal();
  setupEvaluatorPresets();
  setupEvaluator();
  setupReviewQueue();
  setupSourceIngestion();

  // Initial UI Render
  renderReviewQueue();
  renderSourcesLedger();
  updateQueueBadges();
  updateApiStatusIndicator();

  // If there are rules, select the first draft or rule for inspection
  const firstDraft = state.rules.find(r => r.review_status === 'draft') || state.rules[0];
  if (firstDraft) {
    selectRuleForInspection(firstDraft.rule_id);
  }
}

// =============================================================================
// Navigation & Modals
// =============================================================================

function setupNavigation() {
  elements.navTabs.forEach(tab => {
    tab.addEventListener('click', () => {
      elements.navTabs.forEach(t => t.classList.remove('active'));
      elements.tabPanels.forEach(p => p.classList.remove('active'));

      tab.classList.add('active');
      const targetId = tab.getAttribute('data-tab');
      const targetPanel = document.getElementById(targetId);
      if (targetPanel) {
        targetPanel.classList.add('active');
      }
    });
  });
}

function setupConfigModal() {
  elements.settingsToggleBtn.addEventListener('click', () => {
    elements.apiBaseUrlInput.value = state.apiBaseUrl;
    elements.apiModeSelect.value = state.mode;
    elements.configModal.style.display = 'flex';
  });

  elements.configCloseBtn.addEventListener('click', () => {
    elements.configModal.style.display = 'none';
  });

  elements.saveConfigBtn.addEventListener('click', () => {
    state.apiBaseUrl = elements.apiBaseUrlInput.value.trim();
    state.mode = elements.apiModeSelect.value;
    localStorage.setItem('mochatrade_api_url', state.apiBaseUrl);
    localStorage.setItem('mochatrade_mode', state.mode);
    elements.configModal.style.display = 'none';
    updateApiStatusIndicator();
    showToast(`Saved configuration (${state.mode} mode)`);
  });

  elements.testConnectionBtn.addEventListener('click', async () => {
    elements.testConnectionBtn.innerText = 'Pinging...';
    try {
      const res = await fetch(`${elements.apiBaseUrlInput.value.trim().replace(/\/api\/v1$/, '')}/health`, { method: 'GET' });
      if (res.ok) {
        showToast('Backend server is healthy and responding!', 'success');
      } else {
        showToast(`Server returned status ${res.status}`, 'warning');
      }
    } catch (e) {
      showToast('Could not reach backend. Using Demo Mode.', 'warning');
    } finally {
      elements.testConnectionBtn.innerText = 'Ping Server';
    }
  });
}

function updateApiStatusIndicator() {
  if (state.mode === 'live') {
    elements.apiStatusDot.style.background = '#38bdf8';
    elements.apiStatusDot.style.boxShadow = '0 0 10px #38bdf8';
    elements.apiStatusText.innerText = 'Live API: ' + state.apiBaseUrl.replace(/https?:\/\//, '');
  } else {
    elements.apiStatusDot.style.background = '#10b981';
    elements.apiStatusDot.style.boxShadow = '0 0 10px #10b981';
    elements.apiStatusText.innerText = 'Demo Engine (Active)';
  }
}

function showToast(message, type = 'info') {
  elements.toast.innerText = message;
  elements.toast.style.display = 'block';
  setTimeout(() => {
    elements.toast.style.display = 'none';
  }, 3500);
}

// =============================================================================
// Phase 5: Deterministic Compliance Evaluator Logic
// =============================================================================

function parseRatioDenominator(ratioStr) {
  if (!ratioStr || typeof ratioStr !== 'string') return null;
  const parts = ratioStr.trim().split(':');
  if (parts.length === 2) {
    const val = parseInt(parts[1], 10);
    return isNaN(val) ? null : val;
  }
  return null;
}

function evaluateProfileDeterministically(profile) {
  // Pure deterministic evaluator mirroring MarketSphere/services/evaluator.py
  const jurisdiction = profile.jurisdiction;
  const approvedRules = state.rules.filter(
    r => r.jurisdiction === jurisdiction && r.review_status === 'approved'
  );

  const results = [];

  for (const rule of approvedRules) {
    const entry = {
      rule_id: rule.rule_id,
      rule_version: rule.rule_version,
      topic: rule.topic,
      supporting_quote: rule.supporting_quote,
      status: 'PASS',
      reason: 'All checked statutory conditions satisfied',
    };

    // 1. Capital Floor Check
    const reqCap = rule.required_capital_usd;
    const availCap = profile.capital_available_usd;

    if (reqCap !== null && reqCap !== undefined) {
      if (availCap === null || availCap === undefined || isNaN(availCap)) {
        entry.status = 'UNKNOWN';
        entry.reason = 'capital_available_usd not provided in product profile';
        results.push(entry);
        continue;
      }
      if (availCap < reqCap) {
        entry.status = 'CONFLICT';
        entry.reason = `Available capital USD ${availCap.toLocaleString()} is below statutory requirement of USD ${reqCap.toLocaleString()}`;
        results.push(entry);
        continue;
      }
    }

    // 2. Retail Leverage Cap Check
    const capStr = rule.leverage_cap_retail;
    const offeredStr = profile.leverage_offered;

    if (capStr && offeredStr) {
      const capRatio = parseRatioDenominator(capStr);
      const offeredRatio = parseRatioDenominator(offeredStr);

      if (capRatio === null || offeredRatio === null) {
        entry.status = 'UNKNOWN';
        entry.reason = `Could not parse leverage ratio comparison: offered='${offeredStr}', cap='${capStr}'`;
        results.push(entry);
        continue;
      }
      if (offeredRatio > capRatio) {
        entry.status = 'CONFLICT';
        entry.reason = `Offered retail leverage ${offeredStr} exceeds statutory cap of ${capStr}`;
        results.push(entry);
        continue;
      }
    }

    results.push(entry);
  }

  return results;
}

function setupEvaluatorPresets() {
  elements.presetBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      if (btn.dataset.capital) {
        elements.evalCapital.value = btn.dataset.capital;
      }
      if (btn.dataset.leverage) {
        elements.evalLeverage.value = btn.dataset.leverage;
      }
    });
  });
}

function setupEvaluator() {
  elements.evalForm.addEventListener('submit', (e) => {
    e.preventDefault();
    runEvaluation();
  });

  elements.evalClearBtn.addEventListener('click', () => {
    elements.evalCapital.value = '';
    elements.evalLeverage.value = '';
    resetVerdictBanner();
  });
}

function runEvaluation() {
  const jurisdiction = elements.evalJurisdiction.value;
  const productType = elements.evalProductType.value;
  const capitalVal = elements.evalCapital.value.trim();
  const capital = capitalVal === '' ? null : parseFloat(capitalVal);
  const leverage = elements.evalLeverage.value.trim() || null;

  const profile = {
    jurisdiction,
    product_type: productType,
    capital_available_usd: capital,
    leverage_offered: leverage,
  };

  const results = evaluateProfileDeterministically(profile);
  renderEvaluationResults(profile, results);
}

function resetVerdictBanner() {
  elements.verdictBanner.className = 'verdict-banner';
  elements.verdictStatusIcon.innerText = '⚖️';
  elements.verdictTitle.innerText = 'No Evaluation Run Yet';
  elements.verdictSummary.innerText = 'Select a jurisdiction and parameters on the left, then click Run Compliance Evaluation.';
  elements.evalVerdictBadge.innerText = 'Ready';
  elements.evalVerdictBadge.className = 'card-badge';
  elements.evalRuleCardsList.innerHTML = '<div class="empty-state"><p>Awaiting profile input...</p></div>';
}

function renderEvaluationResults(profile, results) {
  elements.evalRuleCardsList.innerHTML = '';

  if (results.length === 0) {
    elements.verdictBanner.className = 'verdict-banner verdict-unknown';
    elements.verdictStatusIcon.innerText = 'ℹ️';
    elements.verdictTitle.innerText = 'No Approved Rules Found';
    elements.verdictSummary.innerText = `There are currently 0 approved rules in the database for ${profile.jurisdiction}. Check the Review Queue to approve candidates.`;
    elements.evalVerdictBadge.innerText = 'No Rules';
    elements.evalVerdictBadge.className = 'card-badge';
    elements.evalRuleCardsList.innerHTML = '<div class="empty-state"><p>No applicable approved statutory rules for this market.</p></div>';
    return;
  }

  const hasConflict = results.some(r => r.status === 'CONFLICT');
  const hasUnknown = results.some(r => r.status === 'UNKNOWN');

  if (hasConflict) {
    elements.verdictBanner.className = 'verdict-banner verdict-conflict';
    elements.verdictStatusIcon.innerText = '❌';
    elements.verdictTitle.innerText = 'Compliance CONFLICT Detected';
    elements.verdictSummary.innerText = `Product offering breaches 1 or more statutory thresholds in ${profile.jurisdiction}. Review required below.`;
    elements.evalVerdictBadge.innerText = 'CONFLICT';
    elements.evalVerdictBadge.className = 'card-badge badge-conflict';
  } else if (hasUnknown) {
    elements.verdictBanner.className = 'verdict-banner verdict-unknown';
    elements.verdictStatusIcon.innerText = '⚠️';
    elements.verdictTitle.innerText = 'UNKNOWN Verification Status';
    elements.verdictSummary.innerText = `Required statutory facts were missing from the product specification. Compliance cannot be confirmed.`;
    elements.evalVerdictBadge.innerText = 'UNKNOWN';
    elements.evalVerdictBadge.className = 'card-badge badge-unknown';
  } else {
    elements.verdictBanner.className = 'verdict-banner verdict-pass';
    elements.verdictStatusIcon.innerText = '✅';
    elements.verdictTitle.innerText = 'PASS — All Checked Rules Satisfied';
    elements.verdictSummary.innerText = `Broker profile complies with all ${results.length} active statutory constraints in ${profile.jurisdiction}.`;
    elements.evalVerdictBadge.innerText = 'PASS';
    elements.evalVerdictBadge.className = 'card-badge badge-pass';
  }

  // Render individual rule audit cards
  results.forEach(res => {
    const card = document.createElement('div');
    const statusLower = res.status.toLowerCase();
    card.className = `eval-rule-card card-${statusLower}`;

    card.innerHTML = `
      <div class="eval-card-header">
        <span class="eval-card-topic">${escapeHtml(res.topic)}</span>
        <span class="status-badge badge-${statusLower}">${res.status}</span>
      </div>
      <p class="eval-card-reason">${escapeHtml(res.reason)}</p>
      <div class="eval-citation-box">
        <span class="citation-label">Verbatim Legal Citation</span>
        "${escapeHtml(res.supporting_quote || 'No citation attached')}"
      </div>
      <div class="eval-card-meta">
        <span>Rule ID: ${escapeHtml(res.rule_id)}</span>
        <span>Version: v${res.rule_version}</span>
      </div>
    `;
    elements.evalRuleCardsList.appendChild(card);
  });
}

// =============================================================================
// Phase 4: Human Review Queue & Rule Store Logic
// =============================================================================

function setupReviewQueue() {
  // Status filter buttons
  elements.reviewStatusFilter.querySelectorAll('.toggle-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      elements.reviewStatusFilter.querySelectorAll('.toggle-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.activeFilterStatus = btn.getAttribute('data-status');
      renderReviewQueue();
    });
  });

  // Jurisdiction filter
  elements.reviewJurisdictionFilter.addEventListener('change', (e) => {
    state.activeFilterJurisdiction = e.target.value;
    renderReviewQueue();
  });

  // Edit rule modal handlers
  elements.editRuleCloseBtn.addEventListener('click', () => {
    elements.editRuleModal.style.display = 'none';
  });
  elements.editRuleCancelBtn.addEventListener('click', () => {
    elements.editRuleModal.style.display = 'none';
  });
  elements.editRuleForm.addEventListener('submit', handleEditRuleSubmit);
}

function updateQueueBadges() {
  const draftsCount = state.rules.filter(r => r.review_status === 'draft').length;
  const approvedCount = state.rules.filter(r => r.review_status === 'approved').length;
  const rejectedCount = state.rules.filter(r => r.review_status === 'rejected').length;

  elements.queueBadgeCount.innerText = `${draftsCount} Drafts`;
  elements.reviewRuleCount.innerText = `${state.rules.length} Total`;

  const draftToggleBtn = elements.reviewStatusFilter.querySelector('[data-status="draft"]');
  if (draftToggleBtn) draftToggleBtn.innerText = `Draft (${draftsCount})`;

  const approvedToggleBtn = elements.reviewStatusFilter.querySelector('[data-status="approved"]');
  if (approvedToggleBtn) approvedToggleBtn.innerText = `Approved (${approvedCount})`;

  const rejectedToggleBtn = elements.reviewStatusFilter.querySelector('[data-status="rejected"]');
  if (rejectedToggleBtn) rejectedToggleBtn.innerText = `Rejected (${rejectedCount})`;
}

function renderReviewQueue() {
  elements.ruleQueueList.innerHTML = '';

  const filteredRules = state.rules.filter(rule => {
    if (state.activeFilterStatus !== 'all' && rule.review_status !== state.activeFilterStatus) {
      return false;
    }
    if (state.activeFilterJurisdiction !== 'all' && rule.jurisdiction !== state.activeFilterJurisdiction) {
      return false;
    }
    return true;
  });

  if (filteredRules.length === 0) {
    elements.ruleQueueList.innerHTML = '<div class="empty-state"><p>No rules match the selected filter.</p></div>';
    return;
  }

  filteredRules.forEach(rule => {
    const card = document.createElement('div');
    const isSelected = rule.rule_id === state.selectedRuleId;
    card.className = `queue-card ${isSelected ? 'selected' : ''}`;
    card.onclick = () => selectRuleForInspection(rule.rule_id);

    let evidenceClass = 'evidence-draft';
    if (rule.evidence_tag === 'Verified Fact') evidenceClass = 'evidence-verified';
    else if (rule.evidence_tag === 'Analyst Estimate') evidenceClass = 'evidence-estimate';

    card.innerHTML = `
      <div class="queue-card-top">
        <span class="queue-market-badge">${escapeHtml(rule.jurisdiction)} • ${escapeHtml(rule.regulator)}</span>
        <span class="evidence-badge ${evidenceClass}">${escapeHtml(rule.evidence_tag)}</span>
      </div>
      <p class="queue-obligation">${escapeHtml(rule.obligation)}</p>
      <div class="queue-card-bottom">
        <span>Topic: <strong>${escapeHtml(rule.topic)}</strong></span>
        <span>Status: <strong style="text-transform: capitalize;">${rule.review_status}</strong> (v${rule.rule_version})</span>
      </div>
    `;
    elements.ruleQueueList.appendChild(card);
  });
}

function selectRuleForInspection(ruleId) {
  state.selectedRuleId = ruleId;
  renderReviewQueue();

  const rule = state.rules.find(r => r.rule_id === ruleId);
  if (!rule) return;

  let evidenceClass = 'evidence-draft';
  if (rule.evidence_tag === 'Verified Fact') evidenceClass = 'evidence-verified';
  else if (rule.evidence_tag === 'Analyst Estimate') evidenceClass = 'evidence-estimate';

  elements.reviewInspector.innerHTML = `
    <div class="inspector-header">
      <div class="inspector-title-area">
        <div class="inspector-meta-row" style="margin-bottom: 8px;">
          <span class="queue-market-badge">${escapeHtml(rule.jurisdiction)} • ${escapeHtml(rule.regulator)}</span>
          <span class="evidence-badge ${evidenceClass}">${escapeHtml(rule.evidence_tag)}</span>
          <span class="version-tag">Version ${rule.rule_version}</span>
        </div>
        <h2>${escapeHtml(rule.topic.toUpperCase())} Policy Directive</h2>
      </div>
      <div>
        <span class="status-badge badge-${rule.review_status === 'approved' ? 'pass' : (rule.review_status === 'rejected' ? 'conflict' : 'unknown')}">
          ${rule.review_status.toUpperCase()}
        </span>
      </div>
    </div>

    <div class="inspector-section">
      <h4>Normalized Obligation Summary</h4>
      <p style="font-size: 14px; line-height: 1.6; color: var(--text-main);">${escapeHtml(rule.obligation)}</p>
    </div>

    <div class="inspector-section">
      <h4>Verbatim Supporting Citation (Source Proof)</h4>
      <div class="inspector-quote-card">
        "${escapeHtml(rule.supporting_quote)}"
      </div>
      <span class="field-hint" style="margin-top: 6px;">
        Verified verbatim substring from Source: <code>${escapeHtml(rule.source_id)}</code>, Page ${rule.page_number || 'N/A'}.
      </span>
    </div>

    <div class="inspector-section">
      <h4>TOPSIS Market Ranker Feed Values</h4>
      <div class="topsis-feed-grid">
        <div class="topsis-card">
          <span class="topsis-card-label">Criterion C4: Retail Leverage</span>
          <span class="topsis-card-val">${rule.leverage_cap_retail || 'None / Not Stated'}</span>
        </div>
        <div class="topsis-card">
          <span class="topsis-card-label">Criterion C6: Capital Floor</span>
          <span class="topsis-card-val">${rule.required_capital_usd ? '$' + rule.required_capital_usd.toLocaleString() : 'None / Not Stated'}</span>
        </div>
        <div class="topsis-card">
          <span class="topsis-card-label">Criterion C7: Local Presence</span>
          <span class="topsis-card-val" style="font-size: 11px;">${rule.presence_friction_summary || 'Standard'}</span>
        </div>
      </div>
    </div>

    <div class="inspector-section">
      <h4>Provenance &amp; Audit Trail</h4>
      <p style="font-size: 12px; color: var(--text-muted); font-family: var(--font-mono);">
        Extraction Model: ${escapeHtml(rule.extraction_model)} | Heading: "${escapeHtml(rule.section_heading || 'N/A')}"<br>
        Reviewer: ${rule.reviewer_id ? escapeHtml(rule.reviewer_id) : 'Pending Human Signature'}
      </p>
    </div>

    <div class="inspector-actions-bar">
      <button class="btn btn-reject btn-sm" onclick="rejectCurrentRule('${rule.rule_id}')">
        <span>Reject Rule</span>
      </button>
      <button class="btn btn-edit btn-sm" onclick="openEditRuleModal('${rule.rule_id}')">
        <span>Edit &amp; Bump Version</span>
      </button>
      <button class="btn btn-approve btn-sm" onclick="approveCurrentRule('${rule.rule_id}')">
        <span>✓ Approve Rule</span>
      </button>
    </div>
  `;
}

// Global action handlers attached to window
window.approveCurrentRule = function(ruleId) {
  const rule = state.rules.find(r => r.rule_id === ruleId);
  if (!rule) return;

  rule.review_status = 'approved';
  rule.reviewer_id = 'compliance.lead@mochatrade.io';
  rule.reviewed_at = new Date().toISOString();

  updateQueueBadges();
  selectRuleForInspection(ruleId);
  showToast(`Rule '${ruleId}' approved for deterministic evaluator.`);
};

window.rejectCurrentRule = function(ruleId) {
  const rule = state.rules.find(r => r.rule_id === ruleId);
  if (!rule) return;

  rule.review_status = 'rejected';
  rule.reviewer_id = 'compliance.lead@mochatrade.io';
  rule.reviewed_at = new Date().toISOString();

  updateQueueBadges();
  selectRuleForInspection(ruleId);
  showToast(`Rule '${ruleId}' marked as rejected.`, 'warning');
};

window.openEditRuleModal = function(ruleId) {
  const rule = state.rules.find(r => r.rule_id === ruleId);
  if (!rule) return;

  elements.editRuleId.value = rule.rule_id;
  elements.editRuleTopic.value = rule.topic;
  elements.editRuleObligation.value = rule.obligation;
  elements.editRuleLeverage.value = rule.leverage_cap_retail || '';
  elements.editRuleCapital.value = rule.required_capital_usd || '';
  elements.editRuleEvidence.value = rule.evidence_tag;

  elements.editRuleModal.style.display = 'flex';
};

function handleEditRuleSubmit(e) {
  e.preventDefault();
  const ruleId = elements.editRuleId.value;
  const rule = state.rules.find(r => r.rule_id === ruleId);
  if (!rule) return;

  rule.topic = elements.editRuleTopic.value.trim();
  rule.obligation = elements.editRuleObligation.value.trim();
  rule.leverage_cap_retail = elements.editRuleLeverage.value.trim() || null;
  rule.required_capital_usd = elements.editRuleCapital.value ? parseFloat(elements.editRuleCapital.value) : null;
  rule.evidence_tag = elements.editRuleEvidence.value;
  rule.reviewer_id = elements.editRuleReviewer.value.trim();
  rule.reviewed_at = new Date().toISOString();

  // Version increment
  rule.rule_version += 1;
  rule.review_status = 'approved';

  elements.editRuleModal.style.display = 'none';
  updateQueueBadges();
  selectRuleForInspection(ruleId);
  showToast(`Rule updated to v${rule.rule_version} and approved.`);
}

// =============================================================================
// Phase 1: Source Ingestion Logic
// =============================================================================

function setupSourceIngestion() {
  // File dropzone clicks and drag events
  elements.fileDropzone.addEventListener('click', () => {
    elements.sourceFileInput.click();
  });

  elements.fileDropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    elements.fileDropzone.classList.add('dragover');
  });

  elements.fileDropzone.addEventListener('dragleave', () => {
    elements.fileDropzone.classList.remove('dragover');
  });

  elements.fileDropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    elements.fileDropzone.classList.remove('dragover');
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleSelectedFile(e.dataTransfer.files[0]);
    }
  });

  elements.sourceFileInput.addEventListener('change', (e) => {
    if (e.target.files && e.target.files[0]) {
      handleSelectedFile(e.target.files[0]);
    }
  });

  elements.removeFileBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    uploadedFileBytes = null;
    currentComputedHash = null;
    elements.sourceFileInput.value = '';
    elements.filePreviewCard.style.display = 'none';
  });

  elements.sourceForm.addEventListener('submit', handleSourceFormSubmit);
}

async function handleSelectedFile(file) {
  elements.previewFilename.innerText = file.name;
  elements.previewHash.innerText = 'Computing SHA-256...';
  elements.filePreviewCard.style.display = 'flex';

  const reader = new FileReader();
  reader.onload = async (e) => {
    uploadedFileBytes = e.target.result;
    const hashBuffer = await crypto.subtle.digest('SHA-256', uploadedFileBytes);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    currentComputedHash = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
    elements.previewHash.innerText = `SHA-256: ${currentComputedHash}`;
  };
  reader.readAsArrayBuffer(file);
}

function handleSourceFormSubmit(e) {
  e.preventDefault();

  const jurisdiction = elements.sourceJurisdiction.value.trim();
  const regulator = elements.sourceRegulator.value.trim();
  const title = elements.sourceTitle.value.trim();
  const sourceType = elements.sourceType.value;
  const instrumentType = elements.sourceInstrument.value;
  const sourceUrl = elements.sourceUrl.value.trim();

  const hash = currentComputedHash || '8f43a9b1c7d24e65bf3109a823c4e12365df8901bca2345e6790a12b3456789a';

  // Check for duplicate hash
  const existing = state.sources.find(s => s.content_hash === hash);
  if (existing) {
    showToast(`Duplicate Rejected: Document with this SHA-256 hash is already registered (${existing.source_id})`, 'warning');
    return;
  }

  const newSource = {
    source_id: `src-${jurisdiction.toLowerCase()}-${Date.now().toString(36)}`,
    jurisdiction,
    regulator,
    title,
    source_type: sourceType,
    instrument_type: instrumentType,
    source_url: sourceUrl || null,
    content_hash: hash,
    source_status: 'active',
    processing_status: 'fetched',
    storage_uri: `sources/${hash.slice(0, 16)}/${elements.previewFilename.innerText || 'doc.pdf'}`,
  };

  state.sources.unshift(newSource);
  renderSourcesLedger();
  showToast(`Source registered successfully with SHA-256: ${hash.slice(0, 16)}...`);

  // Reset form
  elements.filePreviewCard.style.display = 'none';
  uploadedFileBytes = null;
  currentComputedHash = null;
  elements.sourceFileInput.value = '';
}

function renderSourcesLedger() {
  elements.sourceRegistryList.innerHTML = '';

  state.sources.forEach(source => {
    const card = document.createElement('div');
    card.className = 'source-item-card';

    card.innerHTML = `
      <div class="source-item-header">
        <span class="source-item-title">${escapeHtml(source.title)}</span>
        <span class="card-badge" style="font-size: 10px;">${escapeHtml(source.processing_status.toUpperCase())}</span>
      </div>
      <div style="font-size: 12px; color: var(--text-muted); margin-bottom: 4px;">
        ${escapeHtml(source.jurisdiction)} • ${escapeHtml(source.regulator)} • ${escapeHtml(source.source_type)} (${escapeHtml(source.instrument_type || 'General')})
      </div>
      <div class="source-item-hash">
        SHA-256: ${escapeHtml(source.content_hash)}
      </div>
    `;
    elements.sourceRegistryList.appendChild(card);
  });
}

// =============================================================================
// Helper Utilities
// =============================================================================

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// Kickoff on DOM loaded
document.addEventListener('DOMContentLoaded', init);
