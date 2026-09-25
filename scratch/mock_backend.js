/**
 * scratch/mock_backend.js — Standalone API server for MochaTrade / MarketSphere.
 * Provides /api/v1/rules, /api/v1/rules/:id/review, and /api/v1/rules/evaluate
 * with pure deterministic evaluation logic mirroring services/evaluator.py.
 */
const http = require('http');
const fs = require('fs');
const path = require('path');

const dataFile = path.resolve(__dirname, '..', 'data', 'extracted_15_countries_rules.json');
let dbData = JSON.parse(fs.readFileSync(dataFile, 'utf-8'));

function parseRatioDenominator(ratioStr) {
  if (!ratioStr || typeof ratioStr !== 'string') return null;
  const parts = ratioStr.trim().split(':');
  if (parts.length === 2) {
    const val = parseInt(parts[1], 10);
    return isNaN(val) ? null : val;
  }
  return null;
}

function evaluateProfile(profile) {
  const jurisdiction = profile.jurisdiction;
  const approvedRules = dbData.rules.filter(
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

    // Capital check
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

    // Leverage check
    const capStr = rule.leverage_cap_retail;
    const offeredStr = profile.leverage_offered;
    if (capStr) {
      if (!offeredStr) {
        entry.status = 'UNKNOWN';
        entry.reason = 'leverage_offered not provided in product profile';
        results.push(entry);
        continue;
      }
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

  const hasConflict = results.some(r => r.status === 'CONFLICT');
  const hasUnknown = results.some(r => r.status === 'UNKNOWN');
  let verdict = 'PASS';
  if (hasConflict) verdict = 'CONFLICT';
  else if (hasUnknown) verdict = 'UNKNOWN';

  return {
    jurisdiction,
    verdict,
    rules_evaluated: results.length,
    results,
  };
}

const server = http.createServer((req, res) => {
  // CORS
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    res.writeHead(204);
    res.end();
    return;
  }

  const url = new URL(req.url, `http://${req.headers.host}`);

  // GET /health
  if (url.pathname === '/health') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ status: 'ok', server: 'MochaTrade Regulatory Engine' }));
    return;
  }

  // GET /api/v1/rules
  if (req.method === 'GET' && url.pathname === '/api/v1/rules') {
    const statusFilter = url.searchParams.get('status');
    const jurisdictionFilter = url.searchParams.get('jurisdiction');

    let filtered = dbData.rules;
    if (statusFilter) filtered = filtered.filter(r => r.review_status === statusFilter);
    if (jurisdictionFilter) filtered = filtered.filter(r => r.jurisdiction === jurisdictionFilter);

    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ total: filtered.length, rules: filtered }));
    return;
  }

  // POST /api/v1/rules/evaluate
  if (req.method === 'POST' && url.pathname === '/api/v1/rules/evaluate') {
    let body = '';
    req.on('data', chunk => { body += chunk; });
    req.on('end', () => {
      try {
        const profile = JSON.parse(body);
        const evalResult = evaluateProfile(profile);
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(evalResult, null, 2));
      } catch (err) {
        res.writeHead(400, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: err.message }));
      }
    });
    return;
  }

  res.writeHead(404, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify({ error: 'Endpoint not found' }));
});

const PORT = 8000;
server.listen(PORT, () => {
  console.log(`MochaTrade Backend API server listening on http://localhost:${PORT}`);
});
