const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const dataFile = path.resolve(__dirname, '..', 'data', 'extracted_15_countries_rules.json');
const policyDir = path.resolve(__dirname, '..', 'data', 'regulatory_policies');

const data = JSON.parse(fs.readFileSync(dataFile, 'utf-8'));

let matchCount = 0;
let mismatchCount = 0;

console.log('=== AUDITING SHA-256 HASHES FOR ALL SOURCES ===\n');

data.sources.forEach((source, idx) => {
  const filename = path.basename(source.storage_uri);
  const filePath = path.join(policyDir, filename);

  if (!fs.existsSync(filePath)) {
    console.log(`[Source ${idx + 1}] ${source.source_id}: FILE MISSING (${filename})`);
    mismatchCount++;
    return;
  }

  const content = fs.readFileSync(filePath);
  const calculatedHash = crypto.createHash('sha256').update(content).digest('hex');
  const recordedHash = source.content_hash;

  const isMatch = calculatedHash.toLowerCase() === recordedHash.toLowerCase();
  const status = isMatch ? 'MATCH' : 'MISMATCH';

  if (isMatch) {
    matchCount++;
  } else {
    mismatchCount++;
  }

  console.log(`[Source ${String(idx + 1).padStart(2, '0')}] ${filename.padEnd(35)} | ${status}`);
  console.log(`   Recorded:   ${recordedHash}`);
  console.log(`   Recomputed: ${calculatedHash}\n`);
});

console.log(`TOTAL AUDIT: MATCH = ${matchCount}, MISMATCH = ${mismatchCount}`);
