/**
 * MarketSphere — AI Rule Analyzer: country-specific compliance analysis.
 * Flow: country + context -> rules (text/upload) -> review -> compatibility
 * report (vs approved country requirements) -> follow-up chat.
 * Backend: /compliance/countries | /analyze/extract | /compliance/analyze | /compliance/chat
 */

const AZ = {
  stage: 'input',
  country: 'Brazil',
  countries: [],
  file: null,
  extracted: [],
  review: [],
  report: null,
  busy: false,
};

const AZ_FALLBACK_COUNTRIES = [
  'United States', 'United Kingdom', 'Singapore', 'Australia', 'Switzerland',
  'Hong Kong', 'Japan', 'India', 'United Arab Emirates', 'Canada', 'France',
  'Germany', 'Netherlands', 'South Korea', 'Brazil',
];

const AZ_VERDICT = {
  COMPLIANT: { icon: '🟢', label: 'Compliant', cls: 'ok' },
  PARTIALLY_COMPLIANT: { icon: '🟡', label: 'Partially compliant', cls: 'warn' },
  NON_COMPLIANT: { icon: '🔴', label: 'Non-compliant', cls: 'bad' },
  MISSING_REQUIREMENT: { icon: '⚠️', label: 'Missing requirement', cls: 'warn' },
  CONTRADICTORY: { icon: '🔴', label: 'Contradictory', cls: 'bad' },
  NOT_APPLICABLE: { icon: '⚪', label: 'Not applicable', cls: 'mute' },
  UNDETERMINED: { icon: '⚪', label: 'Undetermined', cls: 'mute' },
};

const AZ_SEV = {
  CRITICAL: 'sev-critical',
  HIGH: 'sev-high',
  MEDIUM: 'sev-medium',
  LOW: 'sev-low',
};

const AZ_SAMPLE = [
  'Our retail leverage offering is capped at 1:10.',
  'We also offer select clients leverage of up to 1:50.',
  'Product must be certified before sale.',
  'No import license is required.',
];

// =============================================================================
// Helpers
// =============================================================================

function azApiBase() {
  const stored = localStorage.getItem('mochatrade_api_url');
  if (stored && stored.trim()) return stored.trim().replace(/\/$/, '');
  return window.location.origin + '/api/v1';
}

function azEl(id) {
  return document.getElementById(id);
}

function azEscape(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/** Minimal markdown renderer (chat replies). Input is escaped first. */
function azMd(src) {
  const lines = azEscape(src).split('\n');
  let html = '';
  let listTag = null;

  function closeList() {
    if (listTag) {
      html += `</${listTag}>`;
      listTag = null;
    }
  }

  function inline(s) {
    return s
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\[([^\]]+)\]\((https?:[^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/(^|[\s(])\*([^*\n]+)\*/g, '$1<em>$2</em>');
  }

  for (const line of lines) {
    const t = line.trim();
    if (/^####\s+/.test(t)) {
      closeList();
      html += `<h4>${inline(t.replace(/^####\s+/, ''))}</h4>`;
    } else if (/^###\s+/.test(t)) {
      closeList();
      html += `<h3>${inline(t.replace(/^###\s+/, ''))}</h3>`;
    } else if (/^&gt;\s?/.test(t)) {
      closeList();
      html += `<blockquote>${inline(t.replace(/^&gt;\s?/, ''))}</blockquote>`;
    } else if (/^[-*•]\s+/.test(t)) {
      if (listTag !== 'ul') {
        closeList();
        html += '<ul>';
        listTag = 'ul';
      }
      html += `<li>${inline(t.replace(/^[-*•]\s+/, ''))}</li>`;
    } else if (/^\d+[.)]\s+/.test(t)) {
      if (listTag !== 'ol') {
        closeList();
        html += '<ol>';
        listTag = 'ol';
      }
      html += `<li>${inline(t.replace(/^\d+[.)]\s+/, ''))}</li>`;
    } else if (t === '') {
      closeList();
    } else {
      closeList();
      html += `<p>${inline(t)}</p>`;
    }
  }
  closeList();
  return html;
}

function azShowStage(name) {
  AZ.stage = name;
  ['input', 'review', 'result'].forEach((s) => {
    azEl(`az-stage-${s}`).style.display = s === name ? 'block' : 'none';
  });
}

function azInputError(msg) {
  const box = azEl('az-input-error');
  if (!msg) {
    box.style.display = 'none';
    box.innerText = '';
    return;
  }
  box.innerText = msg;
  box.style.display = 'block';
}

function azBackendError() {
  return (
    'Could not reach the MarketSphere backend. ' +
    'Start it first: double-click run-demo.bat, or run ' +
    '`python -m uvicorn main:app --port 8000` in the project folder, then try again.'
  );
}

function azFormatSize(bytes) {
  if (!bytes && bytes !== 0) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function azExtLabel(filename) {
  return (filename.split('.').pop() || '').toUpperCase() || 'FILE';
}

function azContext() {
  return {
    product: (azEl('az-ctx-product').value || '').trim() || null,
    operation: azEl('az-ctx-operation').value || null,
    ncm: (azEl('az-ctx-ncm').value || '').trim() || null,
    destination: (azEl('az-ctx-destination').value || '').trim() || null,
    origin: null,
    industry: null,
  };
}

// =============================================================================
// Countries
// =============================================================================

async function azLoadCountries() {
  const sel = azEl('az-country');
  const note = azEl('az-country-note');
  let list = [];
  try {
    const res = await fetch(`${azApiBase()}/compliance/countries`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    list = await res.json();
  } catch (e) {
    list = [];
  }
  AZ.countries = list;
  sel.innerHTML = '';
  const names = list.length ? list.map((c) => c.country) : AZ_FALLBACK_COUNTRIES;
  names.forEach((name) => {
    const opt = document.createElement('option');
    opt.value = name;
    opt.innerText = name;
    sel.appendChild(opt);
  });
  if (names.includes('Brazil')) sel.value = 'Brazil';
  AZ.country = sel.value;
  azRefreshCountryNote();
  sel.addEventListener('change', () => {
    AZ.country = sel.value;
    azRefreshCountryNote();
  });
}

function azRefreshCountryNote() {
  const note = azEl('az-country-note');
  const info = AZ.countries.find((c) => c.country === AZ.country);
  if (info) {
    const regs = info.regulators.length ? ` · ${info.regulators.join(', ')}` : '';
    note.innerText =
      `${info.approved_requirements} approved requirement${info.approved_requirements === 1 ? '' : 's'} · ` +
      `${info.sources} source${info.sources === 1 ? '' : 's'}${regs}`;
  } else {
    note.innerText = 'Requirement coverage loads from the live backend when available.';
  }
}

// =============================================================================
// Stage 1: input
// =============================================================================

function azCountTextareaRules() {
  return (azEl('az-text').value || '').split('\n').map((l) => l.trim()).filter(Boolean);
}

function azRefreshCount() {
  const n = azCountTextareaRules().length + AZ.extracted.length;
  azEl('az-text-count').innerText = n === 0 ? '0 rules detected' : `${n} rule${n === 1 ? '' : 's'} detected`;
}

function azSetupInput() {
  azEl('az-text').addEventListener('input', () => {
    azInputError(null);
    azRefreshCount();
  });

  azEl('az-sample-btn').addEventListener('click', () => {
    azEl('az-text').value = AZ_SAMPLE.map((r, i) => `${i + 1}. ${r}`).join('\n');
    azInputError(null);
    azRefreshCount();
  });

  const dz = azEl('az-dropzone');
  const fi = azEl('az-file-input');
  dz.addEventListener('click', () => fi.click());
  dz.addEventListener('dragover', (e) => {
    e.preventDefault();
    dz.classList.add('dragover');
  });
  dz.addEventListener('dragleave', () => dz.classList.remove('dragover'));
  dz.addEventListener('drop', (e) => {
    e.preventDefault();
    dz.classList.remove('dragover');
    if (e.dataTransfer.files && e.dataTransfer.files[0]) azSelectFile(e.dataTransfer.files[0]);
  });
  fi.addEventListener('change', (e) => {
    if (e.target.files && e.target.files[0]) azSelectFile(e.target.files[0]);
  });

  azEl('az-file-remove').addEventListener('click', (e) => {
    e.stopPropagation();
    azClearFile();
  });
  azEl('az-file-replace').addEventListener('click', (e) => {
    e.stopPropagation();
    fi.click();
  });

  azEl('az-btn-review').addEventListener('click', azGoToReview);
}

function azClearFile() {
  AZ.file = null;
  AZ.extracted = [];
  azEl('az-file-input').value = '';
  azEl('az-file-chip').style.display = 'none';
  azEl('az-dropzone').style.display = 'block';
  azRefreshCount();
}

function azSetFileState(text, cls) {
  const el = azEl('az-file-state');
  el.innerText = text;
  el.className = `az-file-state ${cls || ''}`;
}

async function azSelectFile(file) {
  const allowed = ['.pdf', '.docx', '.doc', '.txt', '.md'];
  const ext = `.${(file.name.split('.').pop() || '').toLowerCase()}`;
  if (!allowed.includes(ext)) {
    azInputError(`Unsupported file type '${ext}'. Please upload a PDF, DOCX, or TXT document. Your file is your rule set — it is evaluated, never treated as law.`);
    return;
  }
  if (file.size > 10 * 1024 * 1024) {
    azInputError('The document exceeds the 10 MB limit. Please upload a smaller file.');
    return;
  }
  if (file.size === 0) {
    azInputError('The selected file is empty.');
    return;
  }

  AZ.file = file;
  AZ.extracted = [];
  azInputError(null);
  azEl('az-file-chip').style.display = 'flex';
  azEl('az-dropzone').style.display = 'none';
  azEl('az-file-name').innerText = file.name;
  azEl('az-file-sub').innerText = `${azExtLabel(file.name)} · ${azFormatSize(file.size)}`;
  azSetFileState('Extracting your rules…', 'busy');
  azRefreshCount();

  try {
    const form = new FormData();
    form.append('file', file, file.name);
    const res = await fetch(`${azApiBase()}/analyze/extract`, { method: 'POST', body: form });
    if (!res.ok) {
      const detail = await res.json().then((d) => d.detail).catch(() => '');
      throw new Error(detail || `Server returned status ${res.status}`);
    }
    const data = await res.json();
    AZ.extracted = (data.rules || []).map((r) => r.text);
    azSetFileState(
      `✓ ${data.total} rule${data.total === 1 ? '' : 's'} detected${data.truncated ? ' (truncated at 200)' : ''} — review next`,
      'ok',
    );
  } catch (e) {
    AZ.extracted = [];
    azSetFileState(`Unable to read this document. ${e.message || 'Unknown error.'}`, 'err');
  }
  azRefreshCount();
}

function azGoToReview() {
  if (!AZ.country) {
    azInputError('Select a country first.');
    return;
  }
  const typed = azCountTextareaRules().map((l) => l.replace(/^\d{1,3}[.)\]\-:]\s*/, ''));
  const merged = [...typed, ...AZ.extracted];
  if (merged.length === 0) {
    azInputError('Nothing to review yet — type or paste rules, or upload a document first.');
    return;
  }
  azInputError(null);
  AZ.review = merged;
  azRenderReview();
  azShowStage('review');
}

// =============================================================================
// Stage 2: review
// =============================================================================

function azRenderReview() {
  const list = azEl('az-review-list');
  list.innerHTML = '';
  azEl('az-review-count').innerText = `${AZ.review.length} rule${AZ.review.length === 1 ? '' : 's'}`;

  if (AZ.review.length === 0) {
    list.innerHTML = '<div class="empty-state"><p>No rules — go back and add some, or use “+ Add rule”.</p></div>';
  }

  AZ.review.forEach((rule, i) => {
    const row = document.createElement('div');
    row.className = 'az-review-row';
    const num = document.createElement('span');
    num.className = 'az-review-num';
    num.innerText = `${i + 1}`;
    const ta = document.createElement('textarea');
    ta.value = rule;
    ta.rows = 2;
    ta.setAttribute('aria-label', `Rule ${i + 1}`);
    ta.addEventListener('input', () => {
      AZ.review[i] = ta.value;
    });
    const del = document.createElement('button');
    del.type = 'button';
    del.className = 'az-review-del';
    del.title = `Delete rule ${i + 1}`;
    del.setAttribute('aria-label', `Delete rule ${i + 1}`);
    del.innerText = '✕';
    del.addEventListener('click', () => {
      AZ.review.splice(i, 1);
      azRenderReview();
    });
    row.appendChild(num);
    row.appendChild(ta);
    row.appendChild(del);
    list.appendChild(row);
  });

  azEl('az-btn-analyze').innerText = `Analyze against ${AZ.country}`;
}

function azSetupReview() {
  azEl('az-btn-back-input').addEventListener('click', () => azShowStage('input'));
  azEl('az-btn-add-rule').addEventListener('click', () => {
    AZ.review.push('');
    azRenderReview();
    const rows = azEl('az-review-list').querySelectorAll('textarea');
    if (rows.length) rows[rows.length - 1].focus();
  });
  azEl('az-btn-analyze').addEventListener('click', () => {
    AZ.review = AZ.review.map((r) => (r || '').trim()).filter(Boolean);
    if (AZ.review.length === 0) {
      azRenderReview();
      return;
    }
    azRunCompliance(AZ.review);
  });
  azEl('az-btn-edit-rules').addEventListener('click', () => {
    azRenderReview();
    azShowStage('review');
  });
}

// =============================================================================
// Stage 3: compliance report + follow-up chat
// =============================================================================

function azAddMessage(role, html) {
  const chat = azEl('az-chat');
  const msg = document.createElement('div');
  msg.className = `az-msg ${role}`;
  const sender = document.createElement('div');
  sender.className = 'az-sender';
  sender.innerText = role === 'user' ? 'You' : 'MarketSphere';
  const bubble = document.createElement('div');
  bubble.className = 'az-bubble';
  bubble.innerHTML = html;
  msg.appendChild(sender);
  msg.appendChild(bubble);
  chat.appendChild(msg);
  msg.scrollIntoView({ behavior: 'smooth', block: 'end' });
  return bubble;
}

function azAddTyping(steps) {
  const bubble = azAddMessage('ai', '<div class="az-typing"><span></span><span></span><span></span></div>');
  let stepBox = null;
  if (steps && steps.length) {
    stepBox = document.createElement('div');
    stepBox.className = 'az-steps';
    stepBox.innerHTML = steps.map((s, i) => `<div class="az-step" data-i="${i}">○ ${azEscape(s)}</div>`).join('');
    bubble.appendChild(stepBox);
  }
  return {
    bubble,
    mark(i, done) {
      if (!stepBox) return;
      const el = stepBox.querySelector(`[data-i="${i}"]`);
      if (el) {
        el.className = `az-step ${done ? 'done' : 'busy'}`;
        el.innerText = `${done ? '✓' : '●'} ${steps[i]}`;
      }
    },
    remove() {
      bubble.parentElement.remove();
    },
  };
}

function azVerdictBadge(status) {
  const meta = AZ_VERDICT[status] || AZ_VERDICT.UNDETERMINED;
  return `<span class="az-badge cp-${status.toLowerCase()}">${meta.icon} ${meta.label}</span>`;
}

function azSourceRow(s) {
  const verified = s.verified
    ? '<span class="cp-verified">Verified</span>'
    : '<span class="cp-unverified">Unverified</span>';
  const date = s.reviewed_at ? ` · Reviewed ${azEscape(s.reviewed_at)}` : '';
  const link = s.url
    ? ` · <a href="${azEscape(s.url)}" target="_blank" rel="noopener">View official source</a>`
    : '';
  return `<div class="cp-source"><strong>${azEscape(s.authority || 'Unknown authority')}</strong> — ${azEscape(s.title || 'Untitled source')}${date} ${verified}${link}</div>`;
}

function azRenderReport(rep) {
  const c = rep.compatibility;
  const s = rep.summary;
  const ctxBits = [];
  if (rep.context) {
    if (rep.context.product) ctxBits.push(`Product: ${azEscape(rep.context.product)}`);
    if (rep.context.operation) ctxBits.push(`Operation: ${azEscape(rep.context.operation)}`);
    if (rep.context.ncm) ctxBits.push(`NCM: ${azEscape(rep.context.ncm)}`);
    if (rep.context.destination) ctxBits.push(`Destination: ${azEscape(rep.context.destination)}`);
  }

  let html = `
    <div class="cp-country">${azEscape(rep.country)}</div>
    <h3 class="cp-title">Compliance Analysis</h3>
    <div class="cp-checked">Regulatory information checked: ${azEscape(rep.analysis_date)}${ctxBits.length ? ' · ' + ctxBits.join(' · ') : ''}</div>

    <div class="cp-score">
      <div class="cp-score-num">${c.score}<span>%</span></div>
      <div class="cp-score-bar"><i style="width: ${c.score}%"></i></div>
      <div class="cp-score-label">${azEscape(c.label)}</div>
      <div class="cp-score-sub">${s.total_rules} rules analyzed · ${s.compliant} compliant · ${s.partially_compliant} partial · ${s.non_compliant} non-compliant · ${s.undetermined} undetermined</div>
      <details class="cp-method"><summary>How is this score calculated?</summary><p>${azEscape(c.methodology)} Compatibility means alignment with identified requirements — not government approval.</p></details>
    </div>`;

  const critical = rep.violations.filter((v) => v.severity === 'CRITICAL' || v.severity === 'HIGH');
  if (critical.length || rep.missing_information.length) {
    html += '<h3>Critical Issues</h3>';
    if (!critical.length && !rep.missing_information.length) {
      html += '<p>No critical issues.</p>';
    }
    critical.forEach((v) => {
      html += `<div class="cp-issue"><span class="cp-sev ${AZ_SEV[v.severity] || ''}">${azEscape(v.severity)}</span> <strong>Rule ${v.rule_id}</strong> — ${azEscape(v.explanation)}</div>`;
    });
    if (rep.missing_information.length) {
      html += '<h4>Information required</h4><ul>' + rep.missing_information.map((m) => `<li>${azEscape(m)}</li>`).join('') + '</ul>';
    }
  }

  const realViolations = rep.violations;
  if (realViolations.length) {
    html += '<h3>Violations</h3>';
    realViolations.forEach((v) => {
      html += `
        <div class="cp-rule">
          <div class="cp-rule-head"><span class="az-rule-title">Rule ${v.rule_id}</span><span class="cp-sev ${AZ_SEV[v.severity] || ''}">${azEscape(v.severity)}</span></div>
          <div class="cp-field"><span>User rule:</span><blockquote>${azEscape(v.user_rule)}</blockquote></div>
          <div class="cp-field"><span>Country requirement:</span><p>${azEscape(v.country_requirement)}</p></div>
          <div class="cp-field"><span>Why:</span><p>${azEscape(v.explanation)}</p></div>
          <div class="cp-field"><span>Required action:</span><p>${azEscape(v.required_action)}</p></div>
          ${v.sources.map(azSourceRow).join('')}
        </div>`;
    });
  }

  if (rep.gaps.length) {
    html += '<h3>Compliance Gaps</h3><p>Requirements the rules never address — different from violations.</p>';
    rep.gaps.forEach((g) => {
      html += `
        <div class="cp-rule">
          <div class="cp-rule-head"><span class="az-rule-title">Missing: ${azEscape(g.topic)}</span></div>
          <div class="cp-field"><span>Requirement:</span><p>${azEscape(g.requirement)}</p></div>
          <div class="cp-field"><span>Why it matters:</span><p>${azEscape(g.why_it_matters)}</p></div>
          ${g.sources.map(azSourceRow).join('')}
        </div>`;
    });
  }

  html += '<h3>Rule-by-Rule Analysis</h3>';
  rep.rules.forEach((r) => {
    const sev = r.severity ? ` <span class="cp-sev ${AZ_SEV[r.severity] || ''}">${azEscape(r.severity)}</span>` : '';
    html += `
      <div class="cp-rule">
        <div class="cp-rule-head"><span class="az-rule-title">Rule ${String(r.id).padStart(2, '0')}</span><span>${azVerdictBadge(r.status)}${sev}</span></div>
        <div class="cp-field"><span>User rule:</span><blockquote>${azEscape(r.user_rule)}</blockquote></div>
        ${r.country_requirement ? `<div class="cp-field"><span>Country requirement:</span><p>${azEscape(r.country_requirement)}</p></div>` : ''}
        <div class="cp-field"><span>Why:</span><p>${azEscape(r.explanation)}</p></div>
        ${r.required_action ? `<div class="cp-field"><span>Required change:</span><p>${azEscape(r.required_action)}</p></div>` : ''}
        ${r.missing_information && r.missing_information.length ? `<div class="cp-field"><span>Missing:</span><ul>${r.missing_information.map((m) => `<li>${azEscape(m)}</li>`).join('')}</ul></div>` : ''}
        ${r.sources.map(azSourceRow).join('')}
      </div>`;
  });

  const internal = rep.conflicts.filter((x) => x.kind === 'internal');
  if (internal.length) {
    html += '<h3>Internal Rule Conflicts</h3>';
    internal.forEach((x) => {
      html += `<div class="cp-note">Rules ${x.rules.join(' & ')}: ${azEscape(x.explanation)}</div>`;
    });
  }

  if (rep.required_actions.length) {
    html += '<h3>Required Actions</h3><ol>' + rep.required_actions.map((a) => `<li>${azEscape(a)}</li>`).join('') + '</ol>';
  }

  if (rep.sources.length) {
    html += '<h3>Sources</h3>' + rep.sources.map(azSourceRow).join('');
  }

  return html;
}

async function azRunCompliance(rules) {
  if (AZ.busy) return;
  AZ.busy = true;
  azShowStage('result');
  azEl('az-report-title').innerText = `${AZ.country} — Compliance Analysis`;
  azEl('az-chat').innerHTML = '';

  azAddMessage('user', `<p>Analyze these ${rules.length} rule${rules.length === 1 ? '' : 's'} against ${azEscape(AZ.country)}.</p>`);
  const typing = azAddTyping(['Sending rules', 'Matching country requirements', 'Calculating compatibility', 'Preparing report']);

  try {
    typing.mark(0, false);
    const res = await fetch(`${azApiBase()}/compliance/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ country: AZ.country, rules, context: azContext() }),
    });
    typing.mark(0, true);
    typing.mark(1, false);
    if (!res.ok) {
      const detail = await res.json().then((d) => d.detail).catch(() => '');
      throw new Error(detail || `Server returned status ${res.status}`);
    }
    const data = await res.json();
    typing.mark(1, true);
    typing.mark(2, true);
    typing.mark(3, false);
    AZ.report = data;
    typing.remove();
    azAddMessage('ai', azRenderReport(data));
  } catch (e) {
    typing.remove();
    const isNetwork = e instanceof TypeError;
    azAddMessage('ai', `<div class="az-error">${azEscape(isNetwork ? azBackendError() : e.message)}</div>`);
  } finally {
    AZ.busy = false;
  }
}

async function azSendChat(e) {
  e.preventDefault();
  if (AZ.busy) return;
  const input = azEl('az-chat-input');
  const question = (input.value || '').trim();
  if (!question) return;
  input.value = '';

  azAddMessage('user', `<p>${azEscape(question)}</p>`);
  AZ.busy = true;
  const typing = azAddTyping(null);

  try {
    const res = await fetch(`${azApiBase()}/compliance/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        country: AZ.country,
        rules: AZ.review,
        context: azContext(),
        report: AZ.report,
        question,
      }),
    });
    if (!res.ok) {
      const detail = await res.json().then((d) => d.detail).catch(() => '');
      throw new Error(detail || `Server returned status ${res.status}`);
    }
    const data = await res.json();
    typing.remove();
    azAddMessage('ai', azMd(data.content));
    if (data.action === 'reanalyze') {
      const current = AZ.review.map((r) => (r || '').trim()).filter(Boolean);
      if (current.length) {
        setTimeout(() => azRunCompliance(current), 600);
      }
    }
  } catch (err) {
    typing.remove();
    const isNetwork = err instanceof TypeError;
    azAddMessage('ai', `<div class="az-error">${azEscape(isNetwork ? azBackendError() : err.message)}</div>`);
  } finally {
    AZ.busy = false;
  }
}

// =============================================================================
// Init
// =============================================================================

function azInit() {
  if (!azEl('az-text')) return;
  azLoadCountries();
  azSetupInput();
  azSetupReview();
  azEl('az-composer').addEventListener('submit', azSendChat);
  azRefreshCount();
}

document.addEventListener('DOMContentLoaded', azInit);
