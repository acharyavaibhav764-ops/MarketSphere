/**
 * scratch/run_extraction_trio.js
 *
 * Runs the cold extraction pipeline on Japan, Singapore, and Switzerland:
 *   Stage 1: Extractor LLM call (llama3.2:3b via Ollama)
 *   Stage 2: Judge LLM call (llama3.2:3b via Ollama)
 *   Stage 3: Deterministic Verbatim Gate (verify_verbatim_quote)
 *   Comparison against existing extracted_15_countries_rules.json
 */

'use strict';
const http = require('http');
const fs   = require('fs');
const path = require('path');

const OLLAMA_HOST = 'localhost';
const OLLAMA_PORT = 11434;
const MODEL       = 'llama3.2:3b';

function hr(label) {
  const line = '='.repeat(72);
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

async function processCountry(countryConfig) {
  const { name, filename, jurisdiction } = countryConfig;
  const sourcePath = path.resolve(__dirname, '..', 'data', 'regulatory_policies', filename);
  const chunkText = fs.readFileSync(sourcePath, 'utf-8');

  hr(`JURISDICTION: ${name.toUpperCase()} (${filename} — ${chunkText.length} chars)`);
  console.log(chunkText);

  // STAGE 1
  hr(`[${name.toUpperCase()}] STAGE 1 — EXTRACTOR LLM CALL (model: ${MODEL})`);
  console.log(`[STAGE 1] Extracting rules for ${name}...`);
  const extractionUserPrompt = 'SOURCE TEXT:\n' + chunkText + '\n\nExtract rules as a JSON array.';
  const raw_extraction = await ollamaGenerate(EXTRACTOR_SYSTEM, extractionUserPrompt);

  console.log('--- RAW EXTRACTOR LLM OUTPUT (character-for-character, unmodified) ---');
  console.log(raw_extraction);
  console.log('--- END RAW EXTRACTOR OUTPUT ---');

  let extracted;
  try {
    const cleaned = stripMarkdownJson(raw_extraction);
    extracted = JSON.parse(cleaned);
    if (!Array.isArray(extracted)) {
      throw new Error('Not an array');
    }
    console.log(`\n[STAGE 1] Successfully parsed: ${extracted.length} candidate rule(s)`);
  } catch (e) {
    console.error(`[STAGE 1 FATAL] Parse error: ${e.message}`);
    return;
  }

  // STAGE 2
  hr(`[${name.toUpperCase()}] STAGE 2 — LLM JUDGE (second independent call)`);
  console.log(`[STAGE 2] Sending Stage 1 output to judge...`);
  const judgeUserPrompt =
    'SOURCE TEXT:\n' + chunkText +
    '\n\nEXTRACTED:\n' + JSON.stringify(extracted, null, 2);

  const raw_judged = await ollamaGenerate(JUDGE_SYSTEM, judgeUserPrompt);

  console.log('--- RAW JUDGE LLM OUTPUT (character-for-character, unmodified) ---');
  console.log(raw_judged);
  console.log('--- END RAW JUDGE OUTPUT ---');

  let judged;
  try {
    const cleaned = stripMarkdownJson(raw_judged);
    judged = JSON.parse(cleaned);
    if (!Array.isArray(judged)) {
      console.log('[STAGE 2] Judge output not array — using extractor output');
      judged = extracted;
    } else {
      console.log(`\n[STAGE 2] Successfully parsed: ${judged.length} judged rule(s)`);
    }
  } catch (e) {
    console.log(`[STAGE 2] Parse error (${e.message}) — using extractor output`);
    judged = extracted;
  }

  // STAGE 3
  hr(`[${name.toUpperCase()}] STAGE 3 — DETERMINISTIC VERBATIM GATE`);
  let hallucinations = 0;
  const validated = [];

  for (let i = 0; i < judged.length; i++) {
    const rule  = judged[i];
    const quote = rule.supporting_quote || '';
    const pass  = Boolean(quote && chunkText.includes(quote));

    console.log(`Rule ${i + 1}/${judged.length}  topic=${(rule.topic || '?').toUpperCase()}`);
    console.log(`  quote    : ${JSON.stringify(quote.slice(0, 110))}${quote.length > 110 ? '...' : ''}`);
    console.log(`  gate     : ${pass ? 'PASS' : 'FAIL'}`);

    if (!pass) {
      hallucinations++;
      console.log(`  ValueError: Hallucination detected: supporting_quote is not a verbatim substring of source chunk.`);
    } else {
      console.log(`  evidence : ${rule.evidence_tag || '(not set)'}`);
      validated.push(rule);
    }
    console.log('');
  }

  // VERDICT
  hr(`[${name.toUpperCase()}] FINAL VERDICT`);
  console.log(`Rules submitted to gate : ${judged.length}`);
  console.log(`Passed (verbatim)        : ${validated.length}`);
  console.log(`Would raise ValueError   : ${hallucinations}`);

  if (hallucinations > 0) {
    console.log(`\nVERDICT: pipeline RAISES ValueError for ${hallucinations} hallucinated quote(s) (raise_on_hallucination=True mode).`);
  } else {
    console.log(`\nVERDICT: All ${validated.length} rules passed the verbatim gate — zero hallucinations.`);
  }

  // COMPARISON
  hr(`[${name.toUpperCase()}] COMPARISON vs existing extracted_15_countries_rules.json`);
  const existingPath = path.resolve(__dirname, '..', 'data', 'extracted_15_countries_rules.json');
  const existing = JSON.parse(fs.readFileSync(existingPath, 'utf-8')).rules
    .filter(r => r.jurisdiction === jurisdiction);

  console.log(`Existing ${name} rules in JSON : ${existing.length}`);
  console.log(`Freshly extracted              : ${validated.length}`);
  console.log('');

  const freshQuotes = validated.map(r => r.supporting_quote);

  for (const fr of validated) {
    const same = existing.find(e => e.supporting_quote === fr.supporting_quote);
    if (same) {
      console.log(`[IDENTICAL QUOTE]  topic=${fr.topic}  rule_id=${same.rule_id}`);
    } else {
      console.log(`[DIFFERENT / NEW QUOTE]  topic=${fr.topic}`);
      console.log(`  fresh    : ${JSON.stringify((fr.supporting_quote || '').slice(0, 90))}`);
      const partial = existing.find(e => e.topic === fr.topic);
      if (partial) {
        console.log(`  existing : ${JSON.stringify((partial.supporting_quote || '').slice(0, 90))}`);
      }
    }
    console.log('');
  }

  for (const old of existing) {
    if (!freshQuotes.includes(old.supporting_quote)) {
      console.log(`[MISSING IN FRESH]  rule_id=${old.rule_id}  topic=${old.topic}`);
      console.log(`  quote: ${JSON.stringify(old.supporting_quote.slice(0, 90))}`);
      console.log('');
    }
  }

  const outPath = path.resolve(__dirname, `fresh_${name.toLowerCase()}_extraction.json`);
  fs.writeFileSync(outPath, JSON.stringify({ validated, hallucinations }, null, 2));
  console.log(`Fresh output saved to: ${outPath}\n`);
}

async function main() {
  const countries = [
    { name: 'Japan', filename: 'JP_JFSA_Cabinet_FIBO.txt', jurisdiction: 'Japan' },
    { name: 'Singapore', filename: 'SG_MAS_CFD_SFA04_N15.txt', jurisdiction: 'Singapore' },
    { name: 'Switzerland', filename: 'CH_FINMA_Banking_Forex.txt', jurisdiction: 'Switzerland' },
  ];

  for (const country of countries) {
    await processCountry(country);
  }
}

main().catch(err => {
  console.error('\nFATAL ERROR: ' + err.message);
  process.exit(1);
});
