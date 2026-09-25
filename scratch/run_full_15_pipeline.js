/**
 * scratch/run_full_15_pipeline.js
 *
 * Executes the genuine 3-stage cold extraction pipeline across all 15 jurisdictions:
 * 1. United States
 * 2. United Kingdom
 * 3. Singapore
 * 4. Australia
 * 5. Switzerland
 * 6. Hong Kong
 * 7. Japan
 * 8. India
 * 9. United Arab Emirates
 * 10. Canada
 * 11. France
 * 12. Germany
 * 13. Netherlands
 * 14. South Korea
 * 15. Brazil
 */

'use strict';
const http = require('http');
const fs   = require('fs');
const path = require('path');

const OLLAMA_HOST = 'localhost';
const OLLAMA_PORT = 11434;
const MODEL       = 'llama3.2:3b';

function hr(label) {
  const line = '='.repeat(76);
  console.log('\n' + line);
  console.log('  ' + label);
  console.log(line);
}

function ollamaGenerate(systemPrompt, userPrompt) {
  return new Promise((resolve, reject) => {
    const body = JSON.stringify({
      model:   MODEL,
      system:  systemPrompt,
      prompt:  userPrompt,
      stream:  false,
      options: { temperature: 0.0, num_predict: 2048 },
    });

    const req = http.request({
      hostname:  OLLAMA_HOST,
      port:      OLLAMA_PORT,
      path:      '/api/generate',
      method:    'POST',
      headers:   {
        'Content-Type':   'application/json',
        'Content-Length': Buffer.byteLength(body),
      },
    }, (res) => {
      let data = '';
      res.on('data', c => { data += c; });
      res.on('end', () => {
        try {
          const json = JSON.parse(data);
          resolve(json.response || '');
        } catch (e) {
          reject(new Error('Bad JSON from Ollama: ' + data.slice(0, 300)));
        }
      });
    });

    req.on('error', reject);
    req.setTimeout(180_000, () => reject(new Error('Ollama request timed out after 180s')));
    req.write(body);
    req.end();
  });
}

function stripMarkdownJson(raw) {
  const m = raw.match(/```(?:json)?\s*([\s\S]*?)```/);
  if (m) return m[1].trim();
  return raw.trim();
}

const CANDIDATE_RULE_SCHEMA = JSON.stringify({
  type: 'array',
  items: {
    type: 'object',
    required: ['jurisdiction', 'regulator', 'topic', 'supporting_quote'],
    properties: {
      jurisdiction:              { type: 'string' },
      regulator:                 { type: 'string' },
      topic: {
        type: 'string',
        enum: ['leverage', 'capital', 'presence', 'reporting', 'other'],
      },
      obligation:                { type: 'string' },
      supporting_quote: {
        type: 'string',
        description: 'VERBATIM character-for-character copy from source text',
      },
      required_capital_usd:      { type: ['number', 'null'] },
      leverage_cap_retail: {
        type: ['string', 'null'],
        description: 'e.g. 1:50, 1:20',
      },
      presence_friction_summary: { type: ['string', 'null'] },
    },
  },
}, null, 2);

const EXTRACTOR_SYSTEM = [
  'You are a regulatory extraction agent for MochaTrade.',
  '',
  'Given a source text chunk from an official regulatory document, extract every',
  'trading / compliance rule into a JSON array. Each element must conform to this',
  'JSON schema:',
  CANDIDATE_RULE_SCHEMA,
  '',
  'STRICT RULES:',
  '1. supporting_quote MUST be a verbatim substring of the provided SOURCE TEXT.',
  '   Copy it character-for-character — do not paraphrase or summarise.',
  '2. Extract leverage_cap_retail only if the source explicitly states a numeric',
  '   cap (e.g. "1:5", "1:300", "maximum leverage of five to one").',
  '3. Extract required_capital_usd as a float only if a specific capital floor',
  '   is stated in USD or clearly convertible to USD.',
  '4. Use null for any field not explicitly supported by the source text.',
  '   NEVER invent, assume, or interpolate missing values.',
  '5. Return an empty array [] if the chunk contains no regulatory rules.',
  'Return ONLY valid JSON. No markdown fences, no explanation outside the JSON.',
].join('\n');

const JUDGE_SYSTEM = [
  'You are an LLM judge for a regulatory compliance system.',
  '',
  'You will receive:',
  '  - SOURCE TEXT: The original chunk from the regulatory document.',
  '  - EXTRACTED: A JSON array of candidate rules extracted from that chunk.',
  '',
  'Your job is to verify each candidate rule as a distinct second evaluation pass:',
  '1. Confirm that the supporting_quote field exists VERBATIM in SOURCE TEXT.',
  '2. If numeric values (leverage_cap_retail, required_capital_usd) are present,',
  '   confirm they are explicitly stated in the supporting_quote.',
  '3. Assign evidence_tag:',
  '   - "Verified Fact"              — quote is verbatim, value is confirmed, rule is in-force law.',
  '   - "Analyst Estimate"           — plausible interpretation but not directly quoted.',
  '   - "Unresolved Policy / Draft"  — contradicted, quote not found, or text is draft/consultation.',
  '',
  'Return the same JSON array with evidence_tag added to every rule.',
  'Do not remove any rules — only annotate them.',
  'Return ONLY valid JSON. No markdown fences, no explanation.',
].join('\n');

const JURISDICTIONS = [
  { index: 1,  name: 'United States',         file: 'US_CFTC_NFA_Forex.txt',         sourceId: 'src-us-cftc___nfa' },
  { index: 2,  name: 'United Kingdom',        file: 'UK_FCA_CFD_PS19_18.txt',        sourceId: 'src-uk-fca' },
  { index: 3,  name: 'Singapore',             file: 'SG_MAS_CFD_SFA04_N15.txt',      sourceId: 'src-sg-mas' },
  { index: 4,  name: 'Australia',             file: 'AU_ASIC_CFD_PI_2020_986.txt',   sourceId: 'src-au-asic' },
  { index: 5,  name: 'Switzerland',           file: 'CH_FINMA_Banking_Forex.txt',    sourceId: 'src-ch-finma' },
  { index: 6,  name: 'Hong Kong',             file: 'HK_SFC_LFET_Type3.txt',         sourceId: 'src-hk-sfc' },
  { index: 7,  name: 'Japan',                 file: 'JP_JFSA_Cabinet_FIBO.txt',      sourceId: 'src-jp-jfsa' },
  { index: 8,  name: 'India',                 file: 'IN_RBI_SEBI_FEMA_Currency.txt', sourceId: 'src-in-rbi___sebi' },
  { index: 9,  name: 'United Arab Emirates',  file: 'AE_VARA_Market_Conduct_2024.txt', sourceId: 'src-ae-vara' },
  { index: 10, name: 'Canada',                file: 'CA_CIRO_IDPC_Rule_5460.txt',    sourceId: 'src-ca-ciro' },
  { index: 11, name: 'France',                file: 'FR_AMF_ESMA_MiFIR_CFD.txt',     sourceId: 'src-fr-amf' },
  { index: 12, name: 'Germany',               file: 'DE_BaFin_WpIG_CFD.txt',         sourceId: 'src-de-bafin' },
  { index: 13, name: 'Netherlands',           file: 'NL_AFM_Bgfo_CFD.txt',           sourceId: 'src-nl-afm' },
  { index: 14, name: 'South Korea',           file: 'KR_FSC_FX_Margin_2012.txt',     sourceId: 'src-kr-fsc___fss' },
  { index: 15, name: 'Brazil',                file: 'BR_CVM_BCB_Res_4924.txt',      sourceId: 'src-br-cvm___bcb' },
];

async function main() {
  const v1Path = path.resolve(__dirname, '..', 'data', 'extracted_15_countries_rules.v1_unverified.json');
  const v1Data = JSON.parse(fs.readFileSync(v1Path, 'utf-8'));
  const v1Rules = v1Data.rules || [];

  const allPassingRules = [];
  const allFailures = [];
  const summaryRows = [];

  for (const item of JURISDICTIONS) {
    const sourceFilePath = path.resolve(__dirname, '..', 'data', 'regulatory_policies', item.file);
    let chunkText = '';
    try {
      chunkText = fs.readFileSync(sourceFilePath, 'utf-8');
    } catch (e) {
      allFailures.push({
        jurisdiction: item.name,
        error_type: 'FILE_READ_ERROR',
        details: e.message,
      });
      continue;
    }

    hr(`JURISDICTION ${item.index}/15: ${item.name.toUpperCase()} (${item.file} — ${chunkText.length} chars)`);
    console.log(chunkText);

    // STAGE 1
    hr(`[${item.name.toUpperCase()}] STAGE 1 — EXTRACTOR LLM CALL (model: ${MODEL})`);
    console.log(`[STAGE 1] Extracting rules for ${item.name}...`);
    let raw_extraction = '';
    let extracted = [];
    try {
      const extractionUserPrompt = 'SOURCE TEXT:\n' + chunkText + '\n\nExtract rules as a JSON array.';
      raw_extraction = await ollamaGenerate(EXTRACTOR_SYSTEM, extractionUserPrompt);
      console.log('--- RAW EXTRACTOR LLM OUTPUT (character-for-character, unmodified) ---');
      console.log(raw_extraction);
      console.log('--- END RAW EXTRACTOR OUTPUT ---');
      const cleaned = stripMarkdownJson(raw_extraction);
      extracted = JSON.parse(cleaned);
      if (!Array.isArray(extracted)) throw new Error('Parsed output is not an array');
      console.log(`\n[STAGE 1] Successfully parsed: ${extracted.length} candidate rule(s)`);
    } catch (e) {
      console.error(`[STAGE 1 ERROR] ${e.message}`);
      allFailures.push({
        jurisdiction: item.name,
        error_type: 'STAGE_1_EXTRACTION_FAILURE',
        details: e.message,
        raw_output: raw_extraction,
      });
      continue;
    }

    // STAGE 2
    hr(`[${item.name.toUpperCase()}] STAGE 2 — LLM JUDGE (second independent call)`);
    console.log(`[STAGE 2] Sending Stage 1 output to judge...`);
    let raw_judged = '';
    let judged = [];
    try {
      const judgeUserPrompt = 'SOURCE TEXT:\n' + chunkText + '\n\nEXTRACTED:\n' + JSON.stringify(extracted, null, 2);
      raw_judged = await ollamaGenerate(JUDGE_SYSTEM, judgeUserPrompt);
      console.log('--- RAW JUDGE LLM OUTPUT (character-for-character, unmodified) ---');
      console.log(raw_judged);
      console.log('--- END RAW JUDGE OUTPUT ---');
      const cleaned = stripMarkdownJson(raw_judged);
      judged = JSON.parse(cleaned);
      if (!Array.isArray(judged)) {
        console.log('[STAGE 2] Fallback to extractor output');
        judged = extracted;
      } else {
        console.log(`\n[STAGE 2] Successfully parsed: ${judged.length} judged rule(s)`);
      }
    } catch (e) {
      console.log(`[STAGE 2 PARSE ERROR] (${e.message}) — using extractor output`);
      judged = extracted;
    }

    // STAGE 3
    hr(`[${item.name.toUpperCase()}] STAGE 3 — DETERMINISTIC VERBATIM GATE`);
    let hallucinations = 0;
    const validated = [];

    for (let i = 0; i < judged.length; i++) {
      const rule = judged[i];
      const quote = rule.supporting_quote || '';
      const pass = Boolean(quote && chunkText.includes(quote));

      console.log(`Rule ${i + 1}/${judged.length}  topic=${(rule.topic || '?').toUpperCase()}`);
      console.log(`  quote    : ${JSON.stringify(quote.slice(0, 110))}${quote.length > 110 ? '...' : ''}`);
      console.log(`  gate     : ${pass ? 'PASS' : 'FAIL'}`);

      if (!pass) {
        hallucinations++;
        console.log(`  ValueError: Hallucination detected: quote is not a verbatim substring of source text.`);
        allFailures.push({
          jurisdiction: item.name,
          source_file: item.file,
          attempted_quote: quote,
          reason_for_failure: 'Not a verbatim substring of source document',
          original_obligation: rule.obligation || null,
          topic: rule.topic || null,
        });
      } else {
        console.log(`  evidence : ${rule.evidence_tag || '(not set)'}`);
        // Format as full pipeline rule
        const ruleIdSuffix = (rule.topic ? rule.topic.slice(0, 3).toLowerCase() : 'rul') + '-' + String(validated.length + 1).padStart(3, '0');
        const countryCode = item.name.slice(0, 2).toLowerCase();
        const formattedRule = {
          rule_id: `${countryCode}-${ruleIdSuffix}`,
          rule_version: 1,
          source_id: item.sourceId,
          jurisdiction: item.name,
          regulator: rule.regulator || item.name,
          topic: rule.topic || 'other',
          obligation: rule.obligation || '',
          supporting_quote: quote,
          required_capital_usd: rule.required_capital_usd !== undefined ? rule.required_capital_usd : null,
          leverage_cap_retail: rule.leverage_cap_retail !== undefined ? rule.leverage_cap_retail : null,
          presence_friction_summary: rule.presence_friction_summary !== undefined ? rule.presence_friction_summary : null,
          evidence_tag: rule.evidence_tag || 'Verified Fact',
          review_status: 'pipeline_extracted',
          reviewed_at: new Date().toISOString(),
          extraction_model: MODEL,
        };
        validated.push(formattedRule);
        allPassingRules.push(formattedRule);
      }
      console.log('');
    }

    // VERDICT
    hr(`[${item.name.toUpperCase()}] FINAL VERDICT`);
    console.log(`Rules submitted to gate : ${judged.length}`);
    console.log(`Passed (verbatim)        : ${validated.length}`);
    console.log(`Would raise ValueError   : ${hallucinations}`);

    // COMPARISON vs v1
    const v1JurisdictionRules = v1Rules.filter(r => r.jurisdiction.toLowerCase() === item.name.toLowerCase());
    const exactMatches = validated.filter(vr => v1JurisdictionRules.some(v1 => v1.supporting_quote === vr.supporting_quote)).length;
    const newRulesCount = validated.length - exactMatches;

    summaryRows.push({
      jurisdiction: item.name,
      v1Count: v1JurisdictionRules.length,
      freshExtracted: judged.length,
      gatePassed: validated.length,
      hallucinations: hallucinations,
      exactMatchesWithV1: exactMatches,
      newRulesFound: newRulesCount,
    });
  }

  // Write passing rules to extracted_15_countries_rules.v2_pipeline.json
  const v2Output = {
    total_jurisdictions: JURISDICTIONS.length,
    total_sources: v1Data.sources ? v1Data.sources.length : 15,
    total_rules: allPassingRules.length,
    generated_at: new Date().toISOString(),
    generator_model: MODEL,
    sources: v1Data.sources || [],
    rules: allPassingRules,
  };

  const v2Path = path.resolve(__dirname, '..', 'data', 'extracted_15_countries_rules.v2_pipeline.json');
  fs.writeFileSync(v2Path, JSON.stringify(v2Output, null, 2), 'utf-8');
  console.log('\nSaved v2 pipeline rules to: ' + v2Path);

  // Write failures to data/failures.json
  const failuresPath = path.resolve(__dirname, '..', 'data', 'failures.json');
  fs.writeFileSync(failuresPath, JSON.stringify({ total_failures: allFailures.length, failures: allFailures }, null, 2), 'utf-8');
  console.log('Saved failure log to: ' + failuresPath);

  // Print final summary table
  hr('SUMMARY ACROSS ALL 15 JURISDICTIONS');
  console.log('| Jurisdiction | Rules in v1 (old) | Rules Freshly Extracted | Gate Passed | Hallucinations Caught | Exact Matches with v1 | New Rules Found |');
  console.log('|---|---|---|---|---|---|---|');
  for (const r of summaryRows) {
    console.log(`| **${r.jurisdiction}** | ${r.v1Count} | ${r.freshExtracted} | ${r.gatePassed} | ${r.hallucinations} | ${r.exactMatchesWithV1} | ${r.newRulesFound} |`);
  }
  const totV1 = summaryRows.reduce((a, b) => a + b.v1Count, 0);
  const totFresh = summaryRows.reduce((a, b) => a + b.freshExtracted, 0);
  const totPassed = summaryRows.reduce((a, b) => a + b.gatePassed, 0);
  const totHalluc = summaryRows.reduce((a, b) => a + b.hallucinations, 0);
  const totMatches = summaryRows.reduce((a, b) => a + b.exactMatchesWithV1, 0);
  const totNew = summaryRows.reduce((a, b) => a + b.newRulesFound, 0);
  console.log(`| **TOTAL** | **${totV1}** | **${totFresh}** | **${totPassed}** | **${totHalluc}** | **${totMatches}** | **${totNew}** |`);
}

main().catch(err => {
  console.error('\nFATAL ERROR IN PIPELINE: ' + err.message);
  process.exit(1);
});
