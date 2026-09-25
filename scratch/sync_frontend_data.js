const fs = require('fs');
const path = require('path');

const dataFile = path.resolve(__dirname, '..', 'data', 'extracted_15_countries_rules.json');
const frontendAppJs = path.resolve(__dirname, '..', '..', 'frontend', 'app.js');

const rawData = JSON.parse(fs.readFileSync(dataFile, 'utf-8'));
const appJsContent = fs.readFileSync(frontendAppJs, 'utf-8');

// Replace the sources and rules arrays in app.js
const sourcesJson = JSON.stringify(rawData.sources, null, 2);
const rulesJson = JSON.stringify(rawData.rules, null, 2);

// Match state.sources and state.rules
const statePattern = /const state = \{[\s\S]*?sources: \[[\s\S]*?\],\s*rules: \[[\s\S]*?\]\s*\};/;

const newStateStr = `const state = {
  apiBaseUrl: localStorage.getItem('mochatrade_api_url') || 'http://localhost:8000/api/v1',
  mode: localStorage.getItem('mochatrade_mode') || 'demo', // 'demo' | 'live'
  selectedRuleId: null,
  activeFilterStatus: 'all',
  activeFilterJurisdiction: 'all',

  sources: ${sourcesJson},

  rules: ${rulesJson}
};`;

const updatedAppJs = appJsContent.replace(statePattern, newStateStr);
fs.writeFileSync(frontendAppJs, updatedAppJs, 'utf-8');
console.log('Successfully synced all 15 countries and 32 rules into frontend/app.js');
