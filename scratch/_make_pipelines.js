/**
 * scratch/_make_pipelines.js
 * Generates run_extraction_uae.js and run_extraction_br.js from the US template.
 */
'use strict';
const fs = require('fs');
const path = require('path');

const template = fs.readFileSync(path.join(__dirname, 'run_extraction_us.js'), 'utf-8');

const configs = [
  {
    out:          'run_extraction_uae.js',
    sourceFile:   'AE_VARA_Market_Conduct_2024.txt',
    jurisdiction: 'United Arab Emirates',
    freshOut:     'fresh_uae_extraction.json',
  },
  {
    out:          'run_extraction_br.js',
    sourceFile:   'BR_CVM_BCB_Res_4924.txt',
    jurisdiction: 'Brazil',
    freshOut:     'fresh_br_extraction.json',
  },
];

for (const cfg of configs) {
  let script = template;
  script = script.replace(
    `'US_CFTC_NFA_Forex.txt'`,
    `'${cfg.sourceFile}'`
  );
  script = script.replace(
    `.filter(r => r.jurisdiction === 'United States')`,
    `.filter(r => r.jurisdiction === '${cfg.jurisdiction}')`
  );
  script = script.replace(
    `'fresh_us_extraction.json'`,
    `'${cfg.freshOut}'`
  );
  const outPath = path.join(__dirname, cfg.out);
  fs.writeFileSync(outPath, script, 'utf-8');
  console.log('Written:', outPath, '(' + script.length + ' bytes)');

  // Quick sanity check
  const checks = [cfg.sourceFile, cfg.jurisdiction, cfg.freshOut];
  for (const c of checks) {
    if (!script.includes(c)) console.error('  MISSING:', c);
    else console.log('  OK: contains', JSON.stringify(c));
  }
}
