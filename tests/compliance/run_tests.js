/**
 * tests/compliance/run_tests.js
 * Node.js compliance test runner for MarketSphere / MochaTrade.
 */
'use strict';
const fs   = require('fs');
const path = require('path');

const GREEN  = s => '\x1b[32m' + s + '\x1b[0m';
const RED    = s => '\x1b[31m' + s + '\x1b[0m';
const YELLOW = s => '\x1b[33m' + s + '\x1b[0m';
const CYAN   = s => '\x1b[36m' + s + '\x1b[0m';
const BOLD   = s => '\x1b[1m' + s + '\x1b[0m';

let passed = 0, failed = 0, skipped = 0;
const failures = [];

function assert(cond, msg) { if (!cond) throw new Error('Assertion failed: ' + msg); }

function test(name, fn) {
  process.stdout.write('  ' + CYAN('o') + ' ' + name + ' ... ');
  try { fn(); console.log(GREEN('PASS')); passed++; }
  catch (err) { console.log(RED('FAIL')); console.log('    ' + RED('->') + ' ' + err.message); failed++; failures.push({name, error: err.message}); }
}

function describe(g, fn) { console.log('\n' + BOLD(g)); fn(); }

function parseRatio(s) {
  if (!s || typeof s !== 'string') return null;
  const parts = s.trim().split(':');
  if (parts.length === 2) { const v = parseInt(parts[1],10); return isNaN(v)?null:v; }
  return null;
}

function evaluateProfile(profile, rules) {
  const approved = rules.filter(r => r.review_status === 'approved' && r.jurisdiction === profile.jurisdiction);
  const results = [];
  for (const rule of approved) {
    const entry = {
      rule_id: rule.rule_id,
      rule_version: rule.rule_version ?? 1,
      topic: rule.topic,
      supporting_quote: rule.rule_data?.supporting_quote ?? rule.supporting_quote ?? '',
      status: 'PASS',
      reason: 'All checked statutory conditions satisfied',
    };
    const reqCap  = rule.required_capital ?? rule.required_capital_usd ?? null;
    const availCap = profile.capital_available_usd;
    if (reqCap !== null && reqCap !== undefined) {
      if (availCap === null || availCap === undefined || isNaN(availCap)) {
        entry.status = 'UNKNOWN'; entry.reason = 'capital_available_usd not provided in product profile'; results.push(entry); continue;
      }
      if (Number(availCap) < Number(reqCap)) {
        entry.status = 'CONFLICT'; entry.reason = 'Available capital USD ' + Number(availCap).toLocaleString() + ' is below statutory requirement of USD ' + Number(reqCap).toLocaleString(); results.push(entry); continue;
      }
    }
    const capStr = rule.leverage_cap ?? rule.leverage_cap_retail ?? null;
    const offeredStr = profile.leverage_offered ?? null;
    if (capStr) {
      if (!offeredStr) { entry.status = 'UNKNOWN'; entry.reason = 'leverage_offered not provided in product profile'; results.push(entry); continue; }
      const capRatio = parseRatio(capStr), offeredRatio = parseRatio(offeredStr);
      if (capRatio === null || offeredRatio === null) { entry.status = 'UNKNOWN'; entry.reason = 'Could not parse leverage ratio'; results.push(entry); continue; }
      if (offeredRatio > capRatio) { entry.status = 'CONFLICT'; entry.reason = 'Offered retail leverage ' + offeredStr + ' exceeds statutory cap of ' + capStr; results.push(entry); continue; }
    }
    results.push(entry);
  }
  return results;
}

function mkRule(o) {
  return { rule_id:'rule-test-01', rule_version:1, jurisdiction:'United States', regulator:'CFTC', topic:'capital', required_capital:null, leverage_cap:null, review_status:'approved', rule_data:{supporting_quote: o.supporting_quote ?? 'Quote.'}, ...o };
}

// PHASE 5 EVALUATOR TESTS
describe('Phase 5 - Evaluator Unit Tests (6 cases)', () => {
  test('PASS: capital and leverage both satisfy statutory constraints', () => {
    const rules = [
      mkRule({rule_id:'us-cap',topic:'capital',required_capital:20000000,supporting_quote:'RFEDs must maintain adjusted net capital of not less than USD 20,000,000.'}),
      mkRule({rule_id:'us-lev',topic:'leverage',required_capital:null,leverage_cap:'1:50',supporting_quote:'Major currency pairs retail leverage is capped at 1:50.'}),
    ];
    const r = evaluateProfile({jurisdiction:'United States',capital_available_usd:25000000,leverage_offered:'1:30'}, rules);
    assert(r.length===2, 'Expected 2 results, got '+r.length);
    assert(r.every(x=>x.status==='PASS'), 'All should be PASS');
    assert(r[0].rule_id==='us-cap', 'First rule_id should be us-cap');
    assert(r[0].supporting_quote.includes('20,000,000'), 'Quote should mention capital amount');
  });
  test('CONFLICT: capital_available_usd below statutory floor', () => {
    const rules = [mkRule({rule_id:'us-cap-002',topic:'capital',required_capital:20000000,supporting_quote:'Adjusted net capital of not less than \,000,000.'})];
    const r = evaluateProfile({jurisdiction:'United States',capital_available_usd:5000000}, rules);
    assert(r.length===1, 'Expected 1 result');
    assert(r[0].status==='CONFLICT', 'Expected CONFLICT, got '+r[0].status);
    assert(r[0].reason.includes('below statutory requirement'), 'Reason: '+r[0].reason);
    assert(r[0].rule_id==='us-cap-002', 'rule_id must be preserved');
  });
  test('CONFLICT: leverage_offered exceeds statutory cap', () => {
    const rules = [mkRule({rule_id:'uk-lev-001',jurisdiction:'United Kingdom',topic:'leverage',leverage_cap:'1:30',supporting_quote:'Retail leverage to 1:30 for major currency pairs.'})];
    const r = evaluateProfile({jurisdiction:'United Kingdom',leverage_offered:'1:100'}, rules);
    assert(r.length===1, 'Expected 1 result');
    assert(r[0].status==='CONFLICT', 'Expected CONFLICT, got '+r[0].status);
    assert(r[0].reason.includes('exceeds statutory cap of 1:30'), 'Reason: '+r[0].reason);
  });
  test('UNKNOWN: capital_available_usd missing from profile', () => {
    const rules = [mkRule({rule_id:'sg-cap-001',jurisdiction:'Singapore',topic:'capital',required_capital:1000000,supporting_quote:'Minimum base capital of SGD 1,000,000.'})];
    const r = evaluateProfile({jurisdiction:'Singapore'}, rules);
    assert(r.length===1, 'Expected 1 result');
    assert(r[0].status==='UNKNOWN', 'Expected UNKNOWN, got '+r[0].status);
    assert(r[0].reason.includes('capital_available_usd not provided'), 'Reason: '+r[0].reason);
  });
  test('Draft/rejected rules are strictly excluded', () => {
    const rules = [mkRule({rule_id:'draft-001',review_status:'draft',required_capital:1000000})];
    const r = evaluateProfile({jurisdiction:'United States',capital_available_usd:5000000}, rules);
    assert(r.length===0, 'Draft rule should be excluded; got '+r.length+' result(s)');
  });
  test('rule_id, rule_version, and supporting_quote are preserved in output', () => {
    const rules = [mkRule({rule_id:'citation-001',rule_version:3,topic:'capital',required_capital:500000,supporting_quote:'Registrant must maintain capital of at least \,000 at all times.'})];
    const r = evaluateProfile({jurisdiction:'United States',capital_available_usd:1000000}, rules);
    assert(r.length===1, 'Expected 1 result');
    assert(r[0].rule_id==='citation-001', 'rule_id must be preserved');
    assert(r[0].rule_version===3, 'rule_version must be preserved');
    assert(r[0].supporting_quote.includes('\,000'), 'supporting_quote must be preserved');
    assert(r[0].status==='PASS', 'Status should be PASS, got '+r[0].status);
  });
});

// SCHEMA TESTS
describe('Phase 3 - Schema Validation Tests', () => {
  const REQUIRED = ['rule_id','jurisdiction','regulator','topic','rule_version','review_status'];
  const dataPath = path.resolve(__dirname,'..','..','data','extracted_15_countries_rules.json');
  let allRules = [];
  try { allRules = JSON.parse(fs.readFileSync(dataPath,'utf-8')).rules; } catch(e) {}

  test('Rules file loads with exactly 32 rules', () => {
    assert(allRules.length===32, 'Expected 32 rules, got '+allRules.length);
  });
  test('All 15 jurisdictions are present', () => {
    const EXPECTED = ['United States','United Kingdom','Singapore','Australia','Switzerland','Hong Kong','Japan','India','United Arab Emirates','Canada','France','Germany','Netherlands','South Korea','Brazil'];
    const found = [...new Set(allRules.map(r=>r.jurisdiction))];
    const missing = EXPECTED.filter(j=>!found.includes(j));
    assert(missing.length===0, 'Missing jurisdictions: '+missing.join(', '));
  });
  test('Every rule has all required fields non-empty', () => {
    const bad = [];
    for (const rule of allRules) {
      for (const f of REQUIRED) {
        if (rule[f]===undefined||rule[f]===null||rule[f]==='') bad.push(rule.rule_id+': missing '+f);
      }
      const q = rule.supporting_quote ?? rule.rule_data?.supporting_quote;
      if (!q || q.trim()==='') bad.push(rule.rule_id+': missing supporting_quote');
    }
    assert(bad.length===0, 'Rules with issues:\n    '+bad.join('\n    '));
  });
  test('review_status is one of: approved | draft | rejected', () => {
    const VALID = new Set(['approved','draft','rejected']);
    const bad = allRules.filter(r=>!VALID.has(r.review_status));
    assert(bad.length===0, 'Invalid review_status: '+bad.map(r=>r.rule_id).join(', '));
  });
  test('All rule_ids are unique', () => {
    const ids = allRules.map(r=>r.rule_id);
    const dupes = ids.filter((id,i)=>ids.indexOf(id)!==i);
    assert(dupes.length===0, 'Duplicate rule_ids: '+dupes.join(', '));
  });
  test('No placeholder/fabricated quotes', () => {
    const sus = allRules.filter(r=>{
      const q = (r.supporting_quote ?? r.rule_data?.supporting_quote ?? '').toLowerCase();
      return q.includes('lorem ipsum')||q.includes('[placeholder]')||q.trim()==='';
    });
    assert(sus.length===0, 'Suspicious quotes in: '+sus.map(r=>r.rule_id).join(', '));
  });
});

// INTEGRATION SMOKE TESTS
describe('Integration Smoke Tests - Real Rules x Evaluator', () => {
  const dataPath = path.resolve(__dirname,'..','..','data','extracted_15_countries_rules.json');
  let allRules = [];
  try { allRules = JSON.parse(fs.readFileSync(dataPath,'utf-8')).rules; } catch(e) {}
  const normed = allRules.map(r=>({...r, required_capital:r.required_capital_usd??null, leverage_cap:r.leverage_cap_retail??null, rule_data:{supporting_quote:r.supporting_quote??r.rule_data?.supporting_quote??''}}));

  test('US with ample capital + compliant leverage -> all PASS or UNKNOWN', () => {
    const r = evaluateProfile({jurisdiction:'United States',capital_available_usd:50000000,leverage_offered:'1:10'}, normed);
    assert(r.length>0, 'Should evaluate at least 1 US rule');
    const conflicts = r.filter(x=>x.status==='CONFLICT');
    assert(conflicts.length===0, 'Expected no CONFLICT; got: '+JSON.stringify(conflicts.map(x=>x.reason)));
  });
  test('UK with leverage 1:500 -> CONFLICT on leverage rule', () => {
    const r = evaluateProfile({jurisdiction:'United Kingdom',capital_available_usd:999999999,leverage_offered:'1:500'}, normed);
    const conflicts = r.filter(x=>x.status==='CONFLICT');
    assert(conflicts.length>0, 'UK with 1:500 leverage should produce at least 1 CONFLICT');
  });
  test('All 15 jurisdictions produce >=1 evaluation result', () => {
    const JURS = ['United States','United Kingdom','Singapore','Australia','Switzerland','Hong Kong','Japan','India','United Arab Emirates','Canada','France','Germany','Netherlands','South Korea','Brazil'];
    const empty = JURS.filter(j=>evaluateProfile({jurisdiction:j,capital_available_usd:999999999,leverage_offered:'1:2'},normed).length===0);
    assert(empty.length===0, 'Empty results for: '+empty.join(', '));
  });
});

// SUMMARY
console.log('\n' + '-'.repeat(60));
console.log(BOLD('Results: ' + GREEN(passed+' passed') + '  ' + RED(failed+' failed') + '  ' + YELLOW(skipped+' skipped')));
if (failures.length > 0) {
  console.log(RED('\nFailed tests:'));
  failures.forEach(f => console.log('  x ' + f.name + '\n    ' + f.error));
}
console.log('-'.repeat(60));
process.exit(failed > 0 ? 1 : 0);
