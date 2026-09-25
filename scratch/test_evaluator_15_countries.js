const fs = require('fs');
const path = require('path');

const dataFile = path.resolve(__dirname, '..', 'data', 'extracted_15_countries_rules.json');
const data = JSON.parse(fs.readFileSync(dataFile, 'utf-8'));

function parseRatioDenominator(ratioStr) {
  if (!ratioStr || typeof ratioStr !== 'string') return null;
  const parts = ratioStr.trim().split(':');
  if (parts.length === 2) {
    const val = parseInt(parts[1], 10);
    return isNaN(val) ? null : val;
  }
  return null;
}

function evaluateProfileDeterministically(profile, rules) {
  const jurisdiction = profile.jurisdiction;
  const approvedRules = rules.filter(
    r => r.jurisdiction === jurisdiction && r.review_status === 'approved'
  );

  const results = [];

  for (const rule of approvedRules) {
    const entry = {
      rule_id: rule.rule_id,
      topic: rule.topic,
      supporting_quote: rule.supporting_quote,
      status: 'PASS',
      reason: 'All checked statutory conditions satisfied',
    };

    // Capital floor check
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

    // Leverage cap check
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

  const hasConflict = results.some(r => r.status === 'CONFLICT');
  const hasUnknown = results.some(r => r.status === 'UNKNOWN');
  let overall = 'PASS';
  if (hasConflict) overall = 'CONFLICT';
  else if (hasUnknown) overall = 'UNKNOWN';

  return { jurisdiction, overall, total_evaluated: results.length, results };
}

// Test cases for each of the 15 countries
const testScenarios = [
  // 1. United States: capital floor is $20M, leverage cap is 1:50
  { jurisdiction: "United States", capital_available_usd: 5000000, leverage_offered: "1:30" }, // should be CONFLICT (capital $5M < $20M)
  // 2. United Kingdom: capital $815k, leverage 1:30
  { jurisdiction: "United Kingdom", capital_available_usd: 1000000, leverage_offered: "1:30" }, // should be PASS
  // 3. Singapore: capital $750k, leverage 1:20
  { jurisdiction: "Singapore", capital_available_usd: 1000000, leverage_offered: "1:50" }, // should be CONFLICT (leverage 1:50 > 1:20)
  // 4. Australia: capital $650k, leverage 1:30
  { jurisdiction: "Australia", capital_available_usd: 1000000, leverage_offered: "1:30" }, // should be PASS
  // 5. Switzerland: capital $11.5M, leverage 1:30
  { jurisdiction: "Switzerland", capital_available_usd: 2000000, leverage_offered: "1:20" }, // should be CONFLICT (capital $2M < $11.5M)
  // 6. Hong Kong: capital $3.85M, leverage 1:20
  { jurisdiction: "Hong Kong", capital_available_usd: 5000000, leverage_offered: "1:20" }, // should be PASS
  // 7. Japan: capital $335k, leverage 1:25
  { jurisdiction: "Japan", capital_available_usd: 500000, leverage_offered: "1:20" }, // should be PASS
  // 8. India: capital $3.6M, leverage 1:20
  { jurisdiction: "India", capital_available_usd: 500000, leverage_offered: "1:10" }, // should be CONFLICT (capital $500k < $3.6M)
  // 9. United Arab Emirates: capital $500k, leverage 1:5
  { jurisdiction: "United Arab Emirates", capital_available_usd: 600000, leverage_offered: "1:5" }, // should be PASS
  // 10. Canada: capital $740k, leverage 1:30
  { jurisdiction: "Canada", capital_available_usd: 1000000, leverage_offered: "1:20" }, // should be PASS
  // 11. France: capital $815k, leverage 1:30
  { jurisdiction: "France", capital_available_usd: 1000000, leverage_offered: "1:20" }, // should be PASS
  // 12. Germany: capital $815k, leverage 1:30
  { jurisdiction: "Germany", capital_available_usd: 1000000, leverage_offered: "1:20" }, // should be PASS
  // 13. Netherlands: capital $815k, leverage 1:30
  { jurisdiction: "Netherlands", capital_available_usd: 1000000, leverage_offered: "1:20" }, // should be PASS
  // 14. South Korea: capital $2.3M, leverage 1:10
  { jurisdiction: "South Korea", capital_available_usd: 3000000, leverage_offered: "1:10" }, // should be PASS
  // 15. Brazil: capital $600k, leverage 1:20
  { jurisdiction: "Brazil", capital_available_usd: 1000000, leverage_offered: "1:20" }, // should be PASS
];

console.log("=== EVALUATING ALL 15 JURISDICTIONS ===");
for (const sc of testScenarios) {
  const res = evaluateProfileDeterministically(sc, data.rules);
  console.log(`[${res.overall.padEnd(8)}] ${res.jurisdiction.padEnd(22)} | Rules Evaluated: ${res.total_evaluated}`);
  for (const r of res.results) {
    if (r.status !== 'PASS') {
      console.log(`         ↳ [${r.status}] ${r.topic}: ${r.reason}`);
    }
  }
}
