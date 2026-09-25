const fs = require('fs');
const path = require('path');

const dataFile = path.resolve(__dirname, '..', 'data', 'extracted_15_countries_rules.json');
const policyDir = path.resolve(__dirname, '..', 'data', 'regulatory_policies');

if (!fs.existsSync(dataFile)) {
  console.log('FAIL: data/extracted_15_countries_rules.json does not exist.');
  process.exit(1);
}

const data = JSON.parse(fs.readFileSync(dataFile, 'utf-8'));
console.log('Total rules to audit:', data.rules.length);

let matchCount = 0;
let noMatchCount = 0;
const results = [];

data.rules.forEach((r, idx) => {
  const source = data.sources.find(s => s.source_id === r.source_id);
  if (!source) {
    results.push({ rule_id: r.rule_id, jurisdiction: r.jurisdiction, status: 'NO_SOURCE_RECORD' });
    noMatchCount++;
    return;
  }
  const filename = path.basename(source.storage_uri);
  const filePath = path.join(policyDir, filename);
  if (!fs.existsSync(filePath)) {
    results.push({ rule_id: r.rule_id, jurisdiction: r.jurisdiction, status: 'FILE_NOT_FOUND', file: filename });
    noMatchCount++;
    return;
  }
  const content = fs.readFileSync(filePath, 'utf-8');
  const quote = r.supporting_quote;
  const isMatch = content.includes(quote);
  if (isMatch) {
    results.push({ rule_id: r.rule_id, jurisdiction: r.jurisdiction, status: 'MATCH', file: filename });
    matchCount++;
  } else {
    results.push({ rule_id: r.rule_id, jurisdiction: r.jurisdiction, status: 'NO_MATCH', quote: quote, file: filename });
    noMatchCount++;
  }
});

results.forEach((res, i) => {
  console.log(`[Rule ${String(i + 1).padStart(2, '0')}] ${res.rule_id.padEnd(18)} | ${res.jurisdiction.padEnd(22)} | ${res.status} | file: ${res.file}`);
  if (res.status === 'NO_MATCH') {
    console.log(`   ↳ Quote NOT FOUND: "${res.quote}"`);
  }
});

console.log(`\nAUDIT RESULT: MATCH = ${matchCount}, NO_MATCH = ${noMatchCount}`);
