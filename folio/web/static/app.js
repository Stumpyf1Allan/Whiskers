/* Whiskers — the interface.

   Rules this file keeps, each learned in Mittens & Pence:
   - Every amount of money goes through money(), which wraps it in <span class="pv">,
     so "Hide amounts" can blur it with one class on <html> — including figures drawn
     after the switch was flipped.
   - Unknown is never zero: a missing figure prints "—" and says what is missing.
   - Two numbers on one screen that ought to agree must come from the same source.
   - A top-level "error" in an API reply means the request failed. The server never
     uses that word for anything else. */
'use strict';

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const S = { boot: null, view: 'overview', period: { history: 1825, holding: 365, compare: 365 },
            histMode: 'backdated', compare: ['WORLD', 'NDX', 'FTSE100'], refreshTimer: null,
            lastFinished: null, holdingsFilter: { q: '', platform: '' } };

// ============================================================================ API

// On a phone the server answers only requests carrying this copy's key. The start-up
// link carries it once, after the '#', a part of an address browsers never send to a
// server; from then on Chrome keeps it for this app alone.
const KEY = (() => {
  const m = location.hash.match(/key=([0-9a-f]+)/);
  try {
    if (m) { localStorage.setItem('whiskers-key', m[1]); history.replaceState(null, '', location.pathname); }
    return localStorage.getItem('whiskers-key') || '';
  } catch (e) { return m ? m[1] : ''; }
})();

async function api(path, opts = {}) {
  const init = { method: opts.method || 'GET', headers: {} };
  if (KEY) init.headers['X-Whiskers-Key'] = KEY;
  if (opts.body !== undefined) {
    if (opts.raw) { init.body = opts.body; init.headers['Content-Type'] = 'application/octet-stream'; }
    else { init.body = JSON.stringify(opts.body); init.headers['Content-Type'] = 'application/json'; }
  }
  let res;
  try { res = await fetch(path, init); }
  catch (e) { throw new Error('Whiskers isn\u2019t answering. Is its window still open?'); }
  const ct = res.headers.get('Content-Type') || '';
  if (ct.includes('application/json')) {
    const data = await res.json();
    if (!res.ok || (data && data.error)) throw new Error((data && data.error) || `That didn\u2019t work (${res.status}).`);
    return data;
  }
  if (!res.ok) throw new Error(`That didn\u2019t work (${res.status}).`);
  return res;
}

// ============================================================================ formatting

const GBP0 = new Intl.NumberFormat('en-GB', { style: 'currency', currency: 'GBP', maximumFractionDigits: 0 });
const GBP2 = new Intl.NumberFormat('en-GB', { style: 'currency', currency: 'GBP', minimumFractionDigits: 2, maximumFractionDigits: 2 });
const known = v => v !== null && v !== undefined && !Number.isNaN(v);

function moneyText(v, dp) {
  if (!known(v)) return '\u2014';
  const whole = dp === 0 || (dp === undefined && Math.abs(v) >= 1000);
  return (whole ? GBP0 : GBP2).format(v);
}
function money(v, o = {}) {
  if (!known(v)) return '<span class="muted">\u2014</span>';
  const txt = (o.sign && v > 0 ? '+' : '') + moneyText(v, o.dp);
  return `<span class="pv${o.cls ? ' ' + o.cls : ''}">${txt}</span>`;
}
function pct(f, o = {}) {
  if (!known(f)) return '\u2014';
  const dp = o.dp ?? (Math.abs(f) < 0.1 ? 1 : 1);
  return (o.sign && f > 0 ? '+' : '') + (f * 100).toFixed(dp) + '%';
}
const pts = (v, dp = 1) => known(v) ? `${(+v).toFixed(dp)}%` : '\u2014';
const signCls = v => !known(v) ? '' : v > 0 ? 'up' : v < 0 ? 'down' : '';
// A rate or a spread moves in percentage points, not per cent of itself.
const ptsChange = v => !known(v) ? '\u2014' : `${v > 0 ? '+' : v < 0 ? '\u2212' : ''}${Math.abs(v).toFixed(2)} pts`;
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
function fmtDate(iso) {
  if (!iso) return '\u2014';
  const [y, m, d] = String(iso).slice(0, 10).split('-').map(Number);
  return `${d} ${MONTHS[m - 1]} ${y}`;
}
function ago(iso) {
  if (!iso) return 'never';
  const t = Date.parse(String(iso).replace(' ', 'T'));
  if (Number.isNaN(t)) return fmtDate(iso);
  const s = (Date.now() - t) / 1000;
  if (s < 90) return 'just now';
  if (s < 3600) return `${Math.round(s / 60)} minutes ago`;
  if (s < 86400) return `${Math.round(s / 3600)} hour${Math.round(s / 3600) === 1 ? '' : 's'} ago`;
  const d = Math.round(s / 86400);
  return d === 1 ? 'yesterday' : d < 30 ? `${d} days ago` : fmtDate(iso);
}
const plural = (n, one, many) => `${n} ${n === 1 ? one : (many || one + 's')}`;
const compactMoney = v => '\u00a3' + (Number.isInteger(v) ? (Math.abs(v) >= 1000 ? Charts.compact(v) : String(v)) : Charts.compact(v));
const colourOf = level => ({ red: 'var(--red)', amber: 'var(--amber)', info: 'var(--cyan)',
  green: 'var(--green)', ok: 'var(--green)' }[level] || 'var(--grey)');

// ============================================================================ chrome

const ICONS = {
  overview: '<path d="M4 16a8 8 0 0 1 16 0"/><path d="M12 16l4.2-5"/>',
  holdings: '<path d="M4 6h16M4 12h16M4 18h10"/>',
  allocation: '<circle cx="12" cy="12" r="8.5"/><path d="M12 3.5V12h8.5"/>',
  ai: '<path d="M3 12h4l2.2-5.5 4.2 11 2.2-5.5H21"/>',
  markets: '<path d="M4 4v16h16"/><path d="M7.5 15l3.5-4 3 2.5 5-6"/>',
  activity: '<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 10h16M9 3v4M15 3v4"/>',
  settings: '<path d="M4 7h16M4 12h16M4 17h16"/><circle cx="9" cy="7" r="2" fill="var(--panel)"/><circle cx="15" cy="12" r="2" fill="var(--panel)"/><circle cx="8" cy="17" r="2" fill="var(--panel)"/>',
};
const icon = (k, size = 18) => `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[k] || ''}</svg>`;

const VIEWS = {
  overview: { title: 'Overview', sub: 'Everything at a glance, and anything that needs a look.', render: vOverview },
  holdings: { title: 'Holdings', sub: 'Every holding, grouped by sleeve. Click one for its chart and settings.', render: vHoldings },
  allocation: { title: 'Allocation', sub: 'What you meant to hold against what you hold, and your own rules.', render: vAllocation },
  ai: { title: 'Market watch', sub: 'Your eight signals and your ladder, warning lights for markets in general and for the AI trade, and what a fall would cost.', render: vAI },
  markets: { title: 'Markets', sub: 'The indices and prices behind your sleeves, and what each one tells you.', render: vMarkets },
  activity: { title: 'Activity', sub: 'Money in, dividends, trades and the ISA allowance.', render: vActivity },
  settings: { title: 'Settings', sub: 'Platforms, your plan, rules, data sources and updates.', render: vSettings },
};

function buildNav() {
  $('#nav').innerHTML = Object.entries(VIEWS).map(([k, v]) =>
    `<button type="button" data-view="${k}"><span class="ic">${icon(k)}</span><span class="lbl">${v.title}</span><span class="dot" data-dot="${k}"></span></button>`).join('');
  $$('#nav button').forEach(b => b.addEventListener('click', () => go(b.dataset.view)));
}

function go(view) {
  if (!VIEWS[view]) view = 'overview';
  S.view = view;
  history.replaceState(null, '', '#' + view);
  render();
}

let renderSeq = 0;
async function render() {
  const seq = ++renderSeq;
  const v = VIEWS[S.view];
  $$('#nav button').forEach(b => b.classList.toggle('on', b.dataset.view === S.view));
  $('#title').textContent = v.title;
  $('#subtitle').textContent = v.sub;
  const el = $('#view');
  if (!el.children.length || el.dataset.view !== S.view) {
    el.innerHTML = '<div style="padding:40px 0"><div class="spinner"></div></div>';
  }
  el.dataset.view = S.view;
  try {
    const out = document.createElement('div');
    await v.render(out);
    if (seq !== renderSeq) return;            // somebody clicked elsewhere meanwhile
    $('#title').textContent = out.dataset.title || v.title;
    $('#subtitle').textContent = out.dataset.sub || v.sub;
    el.replaceChildren(...out.childNodes);
    Charts.mount(el);
    wire(el);
    document.dispatchEvent(new CustomEvent('whiskers:rendered'));
  } catch (e) {
    if (seq !== renderSeq) return;
    el.innerHTML = `<div class="panel"><h2>This screen couldn\u2019t load</h2><p class="lede">${esc(e.message)}</p><button class="btn" data-act="retry">Try again</button></div>`;
    wire(el);
  }
}

// Buttons carry data-act; handlers are looked up here, so re-rendering never stacks
// listeners on top of each other.
const ACTS = {};
function wire(root) {
  $$('[data-act]', root).forEach(b => {
    if (b._wired) return;
    b._wired = true;
    const ev = b.tagName === 'SELECT' || b.type === 'checkbox' || b.type === 'range' ? 'change' : 'click';
    b.addEventListener(ev, e => {
      const fn = ACTS[b.dataset.act];
      if (fn) fn(b, e);
    });
  });
  $$('[data-go]', root).forEach(b => {
    if (b._wiredGo) return;
    b._wiredGo = true;
    b.addEventListener('click', () => go(b.dataset.go));
  });
  $$('[data-holding]', root).forEach(b => {
    if (b._wiredH) return;
    b._wiredH = true;
    b.addEventListener('click', e => { e.preventDefault(); openHolding(+b.dataset.holding); });
  });
}
ACTS.retry = () => render();

// ---------------------------------------------------------------------------- modal, toast

function toast(msg, err = false) {
  const t = document.createElement('div');
  t.className = 'toast' + (err ? ' err' : '');
  t.textContent = msg;
  t.onclick = () => t.remove();
  $('#toasts').append(t);
  setTimeout(() => t.remove(), err ? 9000 : 4500);
}

function openModal({ title, body, foot = '', wide = false }) {
  $('#modal-title').textContent = title;
  $('#modal-body').innerHTML = body;
  $('#modal-foot').innerHTML = foot;
  $('.modal-card').classList.toggle('wide', wide);
  $('#modal').hidden = false;
  $('#modal-body').scrollTop = 0;
  Charts.mount($('#modal'));
  wire($('#modal'));
  const first = $('#modal-body input, #modal-body select, #modal-body textarea');
  if (first) setTimeout(() => first.focus(), 30);
  return $('#modal');
}
function closeModal() { $('#modal').hidden = true; $('#modal-body').innerHTML = ''; }
ACTS.close = closeModal;

function confirmBox(title, text, ok = 'Continue', danger = false) {
  return new Promise(resolve => {
    openModal({ title, body: `<p style="max-width:60ch">${text}</p>`,
      foot: `<button class="btn" data-act="cb-no">Cancel</button><button class="btn ${danger ? 'danger' : 'primary'}" data-act="cb-yes">${esc(ok)}</button>` });
    ACTS['cb-no'] = () => { closeModal(); resolve(false); };
    ACTS['cb-yes'] = () => { closeModal(); resolve(true); };
  });
}

function pickFile(accept) {
  return new Promise(resolve => {
    const inp = document.createElement('input');
    inp.type = 'file';
    inp.accept = accept;
    inp.onchange = () => resolve(inp.files[0] || null);
    inp.click();
  });
}

async function busy(btn, fn) {
  const old = btn ? btn.innerHTML : '';
  if (btn) { btn.disabled = true; btn.innerHTML = 'Working\u2026'; }
  try { return await fn(); }
  catch (e) { toast(e.message, true); return null; }
  finally { if (btn && btn.isConnected) { btn.disabled = false; btn.innerHTML = old; } }
}

// ---------------------------------------------------------------------------- theme, privacy

function effectiveTheme() {
  const t = S.boot.settings.theme || 'clock';
  if (t === 'light' || t === 'dark') return t;
  if (t === 'system') return matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  const h = new Date().getHours();
  return h >= 19 || h < 7 ? 'dark' : 'light';
}
function applyTheme() {
  const eff = effectiveTheme();
  const changed = document.documentElement.dataset.theme !== eff;
  document.documentElement.dataset.theme = eff;
  const labels = { clock: 'Theme: by the clock', system: 'Theme: like the computer', light: 'Theme: light', dark: 'Theme: dark' };
  $('#theme-btn').textContent = labels[S.boot.settings.theme || 'clock'];
  return changed;
}
async function cycleTheme() {
  const order = ['clock', 'system', 'light', 'dark'];
  const next = order[(order.indexOf(S.boot.settings.theme || 'clock') + 1) % order.length];
  S.boot.settings.theme = next;
  if (applyTheme()) render();
  api('/api/settings', { method: 'PATCH', body: { theme: next } }).catch(() => {});
}
function applyHide() {
  const on = !!S.boot.settings.hide_amounts;
  document.documentElement.classList.toggle('hide', on);
  $('#hide-btn').textContent = on ? 'Show amounts' : 'Hide amounts';
  $('#hide-btn').setAttribute('aria-pressed', String(on));
}
function toggleHide() {
  S.boot.settings.hide_amounts = !S.boot.settings.hide_amounts;
  applyHide();
  api('/api/settings', { method: 'PATCH', body: { hide_amounts: S.boot.settings.hide_amounts } }).catch(() => {});
}

// ---------------------------------------------------------------------------- refresh

async function startRefresh(force = false) {
  try {
    await api('/api/refresh', { method: 'POST', body: { force } });
    pollRefresh();
  } catch (e) { toast(e.message, true); }
}
async function pollRefresh() {
  clearTimeout(S.refreshTimer);
  let st;
  try { st = await api('/api/refresh'); } catch { return; }
  const el = $('#refresh-status');
  if (st.running) {
    S.wasRunning = true;
    const what = st.phase === 'brokers' ? (st.current || 'Syncing platforms') :
      st.total ? `Prices ${st.done} of ${st.total}` : 'Starting';
    el.textContent = what + '\u2026';
    $('#refresh-btn').disabled = true;
    S.refreshTimer = setTimeout(pollRefresh, 900);
    return;
  }
  $('#refresh-btn').disabled = false;
  el.textContent = st.finished ? `Updated ${ago(st.finished)}` : 'Not refreshed yet';
  // Redraw once when a refresh we watched has finished — including the very first one,
  // when there was no earlier finish time to compare against.
  if (S.wasRunning || (st.finished && S.lastFinished && st.finished !== S.lastFinished)) {
    S.wasRunning = false;
    if (st.errors && st.errors.length) {
      toast(`Updated, but ${plural(st.errors.length, 'item')} couldn\u2019t be fetched. Settings \u203a Data sources has the details.`, true);
    }
    if ($('#modal').hidden) render();
  }
  S.lastFinished = st.finished;
  S.refreshTimer = setTimeout(pollRefresh, 60000);
}

// ---------------------------------------------------------------------------- updates

async function checkUpdateBanner() {
  let u;
  try { u = await api('/api/update'); } catch { return; }
  const b = $('#update-banner');
  if (!u.show_banner) { b.hidden = true; return; }
  const ready = u.status === 'ready';
  b.innerHTML = `<span><b>Whiskers ${esc(u.latest)} is available.</b> ${esc(u.notes || '')}</span>` +
    (ready ? `<button class="btn small primary" data-act="upd-reveal">Show the new version</button>`
           : `<button class="btn small" data-act="upd-download">Download it</button>`) +
    `<button class="btn small ghost" data-act="upd-dismiss">Not now</button>`;
  b.hidden = false;
  wire(b);
}
ACTS['upd-download'] = async btn => { await busy(btn, () => api('/api/update/download', { method: 'POST' })); setTimeout(checkUpdateBanner, 4000); };
ACTS['upd-reveal'] = () => api('/api/update/reveal', { method: 'POST' }).catch(e => toast(e.message, true));
ACTS['upd-dismiss'] = async () => { await api('/api/update/dismiss', { method: 'POST', body: {} }); $('#update-banner').hidden = true; };

// ============================================================================ Overview

async function vOverview(el) {
  const d = await api('/api/overview');
  const t = d.totals;
  if (!S.boot.platforms && !t.holdings) { renderWelcome(el); return; }
  const warn = d.warnings;
  const reds = warn.filter(w => w.level === 'red').length, ambers = warn.filter(w => w.level === 'amber').length;
  setDot('overview', reds ? 'red' : ambers ? 'amber' : null);
  el.innerHTML = `
  <div class="stack-lg">
    <div class="figures">
      <div class="hero"><div class="k">Total value</div><div class="v">${money(t.total)}</div>
        <div class="s">${known(t.day_change) ? `<span class="${signCls(t.day_change)}">${money(t.day_change, { sign: true })} (${pct(t.day_pct, { sign: true, dp: 2 })})</span> today` : 'No daily change yet'}${t.unpriced ? `, <span class="warnline">${plural(t.unpriced, 'holding')} unpriced</span>` : ''}</div></div>
      <div><div class="k">Gain on what you paid</div><div class="v ${signCls(t.gain)}">${money(t.gain, { sign: true })}</div>
        <div class="s">${known(t.gain_pct) ? `${pct(t.gain_pct, { sign: true })} on ${money(t.cost)} paid` : 'What you paid isn\u2019t known yet'}${t.cost_unknown ? `, cost unknown for ${t.cost_unknown}` : ''}</div></div>
      <div><div class="k">Cash not yet invested</div><div class="v">${money(t.cash)}</div>
        <div class="s">${known(t.cash) && t.total ? `${pct(t.cash / t.total)} of the portfolio` : 'Not reported yet'}${known(t.outside_cash) ? `, plus ${money(t.outside_cash)} in cash accounts` : ''}${known(t.owed) && t.owed > 0 ? `, less ${money(t.owed)} owed on cards` : ''}</div></div>
      <div><div class="k">Dividends, last 12 months</div><div class="v">${money(t.dividends_12m)}</div>
        <div class="s">${t.dividends_12m && t.total ? `${pct(t.dividends_12m / t.total, { dp: 2 })} of today\u2019s value` : 'None recorded yet'}</div></div>
    </div>

    <div class="grid g-main">
      <section class="panel">
        <div class="spread"><h2>Things to look at</h2>
          <div class="pill-row">${reds ? `<span class="chip red">${reds} red</span>` : ''}${ambers ? `<span class="chip amber">${ambers} amber</span>` : ''}</div></div>
        <div class="alerts" style="margin-top:8px">${warn.length ? warn.map(alertRow).join('') :
          '<p class="none-state">Nothing needs a look. Every sleeve is inside its band and no rule is tripped.</p>'}</div>
      </section>
      <div class="stack">${miniMonitor(d.market, d.exposure, d.playbook)}${bigPicture(d.big_picture)}</div>
    </div>

    <section class="panel">
      <div class="spread">
        <div><h2>${S.histMode === 'backdated' ? 'How today\u2019s holdings have done' : 'Your recorded value'}</h2>
          <p class="lede" style="margin:2px 0 0">${S.histMode === 'backdated'
            ? 'The holdings you own now, valued at past prices. It shows how this mix behaves, not what your account did.'
            : 'The value Whiskers has recorded each day it was open, and the money paid in.'}</p></div>
        <div class="row">
          <div class="seg">${segBtn('hist-mode', 'backdated', 'Today\u2019s mix', S.histMode)}${segBtn('hist-mode', 'actual', 'Recorded', S.histMode)}</div>
          <div class="seg">${[[365, '1Y'], [1095, '3Y'], [1825, '5Y']].map(([v, l]) => segBtn('hist-period', v, l, S.period.history)).join('')}</div>
        </div>
      </div>
      <div style="margin-top:12px">${historyChart(d)}</div>
    </section>

    <div class="grid g3">
      ${allocationCard(d.allocation, t)}
      ${platformsCard(t.platforms)}
      ${isaCard(d.isa)}
    </div>
    ${d.movers.length ? `<section class="panel"><h2>Biggest moves today</h2>
      <div class="table-wrap" style="margin-top:8px"><table><tbody>${d.movers.map(m => `
        <tr class="click" data-holding="${m.instrument_id}"><td>${esc(m.name)}</td>
        <td class="r ${signCls(m.day_change)}">${money(m.day_change, { sign: true })}</td>
        <td class="r num ${signCls(m.day_pct)}">${pct(m.day_pct, { sign: true })}</td></tr>`).join('')}</tbody></table></div></section>` : ''}
  </div>`;
}

const segBtn = (act, val, label, cur) => `<button type="button" class="${String(val) === String(cur) ? 'on' : ''}" data-act="${act}" data-v="${val}">${label}</button>`;
ACTS['hist-mode'] = b => { S.histMode = b.dataset.v; render(); };
ACTS['hist-period'] = b => { S.period.history = +b.dataset.v; render(); };

function alertRow(w) {
  return `<button class="alert ${w.level}" data-go="${w.go}" type="button"><span class="lvl ${w.level}"></span>
    <span class="t">${esc(w.title)}</span><span class="go">${esc(VIEWS[w.go]?.title || '')}</span>
    ${w.detail ? `<span class="d">${esc(w.detail)}</span>` : ''}</button>`;
}

function setDot(view, level) {
  const d = $(`[data-dot="${view}"]`);
  if (d) d.style.background = level ? colourOf(level) : 'transparent';
}

function sliceSince(points, days) {
  if (!points.length) return points;
  const last = Date.parse(points.at(-1)[0]);
  const from = new Date(last - days * 864e5).toISOString().slice(0, 10);
  return points.filter(p => p[0] >= from);
}

function historyChart(d) {
  if (S.histMode === 'backdated') {
    const h = d.history;
    const p = sliceSince(h.points, S.period.history);
    if (p.length < 2) return '<p class="muted">No price history yet. Press Refresh to fetch it.</p>';
    const first = p[0][1], last = p.at(-1)[1];
    let worst = null, peak = p[0];
    for (const q of p) { if (q[1] > peak[1]) peak = q; const dd = 1 - q[1] / peak[1]; if (!worst || dd > worst.dd) worst = { dd, from: peak[0], to: q[0] }; }
    const notes = [];
    notes.push(`Over this period: <span class="${signCls(last - first)}">${pct(last / first - 1, { sign: true })}</span>.`);
    if (worst && worst.dd > 0.005) notes.push(`Worst fall inside it: ${pct(-worst.dd)} (${fmtDate(worst.from)} to ${fmtDate(worst.to)}).`);
    if (h.coverage < 0.995) notes.push(`Covers ${pct(h.coverage, { dp: 0 })} of today\u2019s value; no price history for ${esc(h.missing.slice(0, 4).join(', '))}${h.missing.length > 4 ? ' and others' : ''}.`);
    return Charts.line({ series: [{ name: 'Value', points: p, color: 'var(--accent)', area: true }],
      money: true, fmt: v => moneyText(v, 0), yfmt: compactMoney, label: 'Backdated value' }, 260) +
      `<p class="chart-note">${notes.join(' ')}</p>`;
  }
  const snaps = sliceSince(d.snapshots, S.period.history);
  const paid = sliceSince(d.money_in, S.period.history);
  if (snaps.length < 2) {
    return `<p class="muted" style="max-width:70ch">Whiskers records the total once a day, whenever it\u2019s open, so this line starts ${snaps.length ? `on ${fmtDate(snaps[0][0])}` : 'today'} and grows from there. Until then, \u201cToday\u2019s mix\u201d shows the same holdings over the past five years.</p>`;
  }
  return Charts.line({ series: [
      { name: 'Value', points: snaps, color: 'var(--accent)', area: true },
      { name: 'Paid in', points: paid, color: 'var(--muted)', dash: '5 4', width: 1.6 }],
    money: true, fmt: v => moneyText(v, 0), yfmt: compactMoney }, 260);
}

// The Overview's monitor is the AI trade only; everything else is in the big picture
// underneath, and in full on the Market watch screen.
function miniMonitor(m, exp, pb) {
  const g = (m.groups || {}).ai || { label: 'No data', score: 0 };
  const ai = { regime: { Calm: 'calm', Watch: 'watch', Turning: 'turning' }[g.label] || 'none', gauge: g.score || 0, label: g.label };
  const lights = m.lights.filter(x => x.group === 'ai').map(x => `<div class="row small" style="gap:8px"><span class="lvl ${x.level}" style="background:${monColour(x.level)}"></span><span>${esc(x.title)}</span></div>`).join('');
  return `<section class="monitor" style="cursor:pointer" data-go="ai">
    <div class="spread"><h2>AI watch</h2><span class="muted small">The AI trade only</span></div>
    <div class="row" style="margin:12px 0 4px;gap:18px;align-items:center">
      <div style="width:150px;color:var(--mon-ink)">${Charts.gauge(needle(ai), { zones: GAUGE_ZONES, size: 220, label: ai.label })}</div>
      <div><div class="regime-word ${ai.regime}">${esc(ai.label)}</div>
      <p class="small" style="margin-top:6px;color:var(--mon-ink)">${known(exp.ai_pct) ? `${pct(exp.ai_pct, { dp: 0 })} of your money rides on AI` : 'AI exposure not worked out yet'}${exp.unknown ? `, ${plural(exp.unknown, 'holding')} not rated` : ''}.${pb ? ` Your AI signals: ${pb.ai_firing} of 3 firing.` : ''}</p></div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px 14px">${lights}</div>
  </section>`;
}

function bigPicture(b) {
  if (!b) return '';
  return `<section class="panel"><h2>The big picture</h2>
    <h3 style="margin-top:10px">The AI trade</h3><p class="small">${narr(b.ai)}</p>
    <h3 style="margin-top:12px">Markets and the economy</h3><p class="small">${narr(b.markets)}</p>
    <h3 style="margin-top:12px">What it means for your portfolio</h3><p class="small">${narr(b.portfolio)}</p>
    <p class="note" style="margin-top:10px">Written from today\u2019s readings by fixed rules. Not advice.</p>
  </section>`;
}

// Narratives come from the server as plain text with pound amounts in [[ ]]; those
// become private figures, so "Hide amounts" blurs them like every other.
const narr = t => esc(t || '').replace(/\[\[(.*?)\]\]/g, '<span class="pv">$1</span>');
const monColour = l => ({ green: 'var(--mon-green)', amber: 'var(--mon-amber)', red: 'var(--mon-red)' }[l] || 'var(--mon-muted)');
const GAUGE_ZONES = [{ to: .25, color: 'var(--mon-green)' }, { to: .5, color: 'var(--mon-amber)' },
                     { to: .75, color: 'var(--mon-red)' }, { to: 1, color: '#b0302a' }];
// The needle sits inside the zone for the regime the lights produced, nudged by how
// strong the readings are, so the dial can never contradict the word under it.
function needle(m) {
  const idx = { calm: 0, watch: 1, turning: 2, stress: 3 }[m.regime];
  return idx === undefined ? null : (idx + 0.2 + 0.6 * Math.min(1, m.gauge * 2)) / 4;
}

function allocationCard(a, t) {
  const rows = a.sleeves.concat(a.extra);
  const outer = rows.map(r => ({ value: r.value, color: r.colour }));
  const inner = a.sleeves.map(r => ({ value: r.target, color: r.colour }));
  const worst = a.sleeves.filter(r => r.status === 'red' || r.status === 'amber')
    .sort((x, y) => Math.abs(y.drift) - Math.abs(x.drift)).slice(0, 4);
  return `<section class="panel" data-go="allocation" style="cursor:pointer">
    <h2>Allocation</h2>
    <p class="lede">Outer ring: what you hold. Inner ring: your targets.</p>
    <div class="alloc-mini">
      <div>${Charts.donut(outer, { size: 160, thick: 20, inner, centre: t.total ? `${a.in_band}/${a.sleeves.length}` : '', sub: 'in band' })}</div>
      <div class="legend-rows small">${a.sleeves.length ? (worst.length ? worst.map(r => `
        <div class="row" style="margin-bottom:6px"><span class="lvl ${r.status}"></span><span class="grow">${esc(r.name)}</span>
        <span class="num">${pts(r.actual)} <span class="muted">/ ${pts(r.target, 0)}</span></span></div>`).join('') :
        '<p>Every sleeve is inside its band.</p>') : '<p>No sleeves yet. Load your plan in Settings.</p>'}
        ${a.extra.map(r => `<div class="row"><span class="lvl" style="background:${r.colour}"></span><span class="grow">${esc(r.name)}</span><span class="num">${pts(r.actual)}</span></div>`).join('')}
      </div>
    </div>
  </section>`;
}

function platformsCard(plats) {
  plats = plats.filter(p => p.kind === 'platform');
  return `<section class="panel"><h2>Platforms</h2>
    <p class="lede">Each against its limit: the FSCS\u2019s \u00a385,000 per firm, or the lower buffer your plan sets.</p>
    <div class="stack">${plats.length ? plats.map(p => {
      const share = p.limit ? p.total / p.limit : 0;
      const cls = share > 1 ? 'red' : share >= 0.9 ? 'amber' : '';
      const room = p.limit - p.total;
      return `<div><div class="spread small"><b>${esc(p.name)}</b><span>${money(p.total)}</span></div>
        <div class="limit-bar" style="margin:6px 0 4px"><div class="fill ${cls}" style="width:${Math.min(100, share / 1.15 * 100)}%"></div>
          <div class="mark" style="left:${100 / 1.15}%" title="Protection limit"></div></div>
        <div class="tiny muted">${room >= 0 ? `${money(room)} below the limit` : `<span class="warnline">${money(-room)} over the limit</span>`}${known(p.cash) ? `, ${money(p.cash)} cash` : ', cash not known'}${p.last_sync ? `, updated ${ago(p.last_sync)}` : ''}</div></div>`;
    }).join('') : '<p class="muted">No platforms yet.</p>'}</div></section>`;
}

function isaCard(i) {
  if (!i.has_data) {
    return `<section class="panel"><h2>ISA allowance ${esc(i.label)}</h2><p class="lede">Needs your deposit history: it comes with a Trading 212 sync or a Freetrade activity file.</p></section>`;
  }
  const f = i.limit ? i.used / i.limit : 0;
  return `<section class="panel" data-go="activity" style="cursor:pointer"><h2>ISA allowance ${esc(i.label)}</h2>
    <div class="row" style="gap:18px;margin-top:10px">
      <div>${Charts.ring(f, { size: 128, color: i.over ? 'var(--red)' : 'var(--accent)', text: pct(f, { dp: 0 }), sub: 'used' })}</div>
      <div class="small"><div><span class="fig" style="font-size:1.3rem">${money(i.remaining, { dp: 0 })}</span> left of ${money(i.limit, { dp: 0 })}</div>
      <div class="muted">${i.days_left !== null ? `${plural(i.days_left, 'day')} until 5 April` : ''}</div>
      ${i.platforms.map(p => `<div class="tiny">${esc(p.name)}: ${money(p.used, { dp: 0 })}${p.flexible && p.withdrawals ? ' (after withdrawals, flexible)' : ''}</div>`).join('')}</div>
    </div></section>`;
}

// ---------------------------------------------------------------------------- welcome

function renderWelcome(el) {
  // Titles are applied by render() once it knows this screen is still the one wanted;
  // setting them here let a slow Overview rename whichever screen was opened next.
  el.dataset.title = 'Welcome';
  el.dataset.sub = 'Three things to set up, about ten minutes in all.';
  el.innerHTML = `<div class="welcome">
    <div class="steps">
      <div class="step"><div class="stack" style="gap:8px"><h3>Your plan</h3>
        ${S.boot.sleeves ? `<p><span class="chip green">Done</span> ${plural(S.boot.sleeves, 'sleeve')} set up. Change them any time in Settings.</p>` : `
        <p class="muted">The sleeves you split your money into, and the share each should have. Answer ten questions for a starting plan, load a plan file someone made for you, or start from a simple template. Every figure can be changed later in Settings.</p>
        <div class="row wrap"><button class="btn primary" data-act="plan-wizard">Answer some questions</button><button class="btn" data-act="plan-import">Load a plan file</button><button class="btn" data-act="starter">Start from a template</button></div>`}</div></div>
      <div class="step"><div class="stack" style="gap:8px"><h3>Your platforms</h3>
        <p class="muted">Trading 212 connects with a read-only key and updates itself. Freetrade has no connection, so it reads the activity file the app exports.</p>
        <div class="row wrap"><button class="btn" data-act="add-platform" data-kind="trading212">Add Trading 212</button><button class="btn" data-act="add-platform" data-kind="freetrade">Add Freetrade</button><button class="btn ghost" data-act="add-platform" data-kind="other">Another platform</button></div></div></div>
      <div class="step"><div class="stack" style="gap:8px"><h3>Sort holdings into sleeves</h3>
        <p class="muted">Whiskers suggests a sleeve for each holding. You confirm them on the Allocation screen.</p></div></div>
    </div>
    <div class="panel"><h3>Just looking?</h3><p class="muted" style="margin:4px 0 10px">Load a made-up portfolio to see every screen working. It sits on two sample platforms and comes out again in one click.</p>
      <button class="btn" data-act="sample-load">Load the sample portfolio</button></div>
  </div>`;
}

const STARTER = { whiskers_plan: 1, sleeves: [
  { name: 'Global core', target: 40 }, { name: 'Technology & AI', target: 18, ai_share: 100 },
  { name: 'Healthcare', target: 7, ai_share: 0 }, { name: 'Consumer', target: 5, ai_share: 0 },
  { name: 'Financials', target: 5, ai_share: 0 }, { name: 'Industrials', target: 5, ai_share: 0 },
  { name: 'Commodities & gold', target: 6, ai_share: 0 }, { name: 'Energy', target: 3, ai_share: 0 },
  { name: 'Defence', target: 2, ai_share: 0 }, { name: 'Gilts', target: 5, ai_share: 0 },
  { name: 'Cash', target: 4, ai_share: 0, is_cash: true }] };

ACTS.starter = async btn => {
  await busy(btn, async () => {
    await api('/api/plan/import', { method: 'POST', body: STARTER });
    toast('Template loaded. Change the sleeves and targets in Settings whenever you like.');
    await refreshBoot();
    render();
  });
};
ACTS['plan-import'] = async btn => {
  const f = await pickFile('.json,application/json');
  if (!f) return;
  await busy(btn, async () => {
    const out = await api('/api/plan/import', { method: 'POST', body: await f.text(), raw: true });
    const r = out.report;
    const bits = [plural(r.sleeves, 'sleeve'), plural(r.rules, 'rule')];
    if (known(r.sorted)) bits.push(`${plural(r.sorted, 'holding')} in sleeves${r.unsorted ? `, ${r.unsorted} still to sort on the Allocation screen` : ''}`);
    if (r.removed && r.removed.length) bits.push(`replaced ${r.removed.join(', ')}`);
    if (r.corrections && r.corrections.changed) bits.push(`${plural(r.corrections.changed.length, 'Freetrade holding')} corrected`);
    toast(`Plan loaded: ${bits.join('; ')}.`);
    await refreshBoot();
    render();
  });
};
ACTS['sample-load'] = async btn => {
  await busy(btn, async () => {
    await api('/api/sample/load', { method: 'POST' });
    toast('Sample loaded. Remove it from Settings when you\u2019re done.');
    await refreshBoot();
    pollRefresh();
    go('overview');
  });
};
ACTS['add-platform'] = btn => addPlatform(btn.dataset.kind);

async function refreshBoot() { S.boot = await api('/api/bootstrap'); }

// ============================================================================ Holdings

function mergeHoldings(rows, total) {
  const add = (a, b) => (known(a) || known(b)) ? (a || 0) + (b || 0) : null;
  const by = new Map();
  for (const r of rows) {
    let m = by.get(r.instrument_id);
    if (!m) {
      m = { ...r, platforms: [], value: null, cost: null, gain: null, day_change: null, quantity: 0, anyUnknownCost: false };
      by.set(r.instrument_id, m);
    }
    m.platforms.push(r);
    m.quantity += r.quantity;
    m.value = add(m.value, r.value);
    m.cost = add(m.cost, r.cost);
    if (!known(r.cost)) m.anyUnknownCost = true;
    m.gain = add(m.gain, r.gain);
    m.day_change = add(m.day_change, r.day_change);
  }
  for (const m of by.values()) {
    m.weight = known(m.value) && total ? m.value / total : null;
    m.gain_pct = known(m.gain) && m.cost ? m.gain / m.cost : null;
  }
  return [...by.values()];
}

async function vHoldings(el) {
  const d = await api('/api/holdings');
  const total = d.totals.total;
  const f = S.holdingsFilter;
  let rows = mergeHoldings(d.rows, total);
  const platforms = [...new Set(d.rows.map(r => r.platform))];
  if (f.platform) rows = rows.filter(r => r.platforms.some(p => p.platform === f.platform));
  if (f.q) { const q = f.q.toLowerCase(); rows = rows.filter(r => `${r.name} ${r.symbol} ${r.sleeve || ''}`.toLowerCase().includes(q)); }
  const groups = new Map();
  for (const s of d.sleeves) groups.set(s.id, { sleeve: s, rows: [] });
  groups.set(null, { sleeve: { id: null, name: 'Not in a sleeve yet', colour: '#a0a9b6', target: null }, rows: [] });
  for (const r of rows) (groups.get(r.sleeve_id) || groups.get(null)).rows.push(r);
  const body = [...groups.values()].filter(g => g.rows.length).map(g => {
    g.rows.sort((a, b) => (b.value || 0) - (a.value || 0));
    const sub = g.rows.reduce((a, r) => a + (r.value || 0), 0);
    return `<tr class="group"><td colspan="3"><span class="lvl" style="background:${g.sleeve.colour}"></span>${esc(g.sleeve.name)} <span class="muted small">${plural(g.rows.length, 'holding')}</span></td>
      <td class="r">${money(sub)}</td><td class="r num">${total ? pct(sub / total) : ''}${known(g.sleeve.target) ? ` <span class="muted small">of ${pts(g.sleeve.target, 0)}</span>` : ''}</td><td colspan="3"></td></tr>` +
      g.rows.map(holdingRow).join('');
  }).join('');
  el.innerHTML = `<div class="stack">
    <div class="spread">
      <div class="row wrap">
        <input type="search" id="h-q" placeholder="Find a holding" value="${esc(f.q)}" style="width:220px">
        <select id="h-plat"><option value="">Every platform</option>${platforms.map(p => `<option ${p === f.platform ? 'selected' : ''}>${esc(p)}</option>`).join('')}</select>
      </div>
      <div class="row"><span class="muted small">${plural(rows.length, 'holding')}${d.totals.unpriced ? `, ${d.totals.unpriced} without a price` : ''}</span>
        <button class="btn" data-act="add-position">Add a holding by hand</button></div>
    </div>
    ${rows.length ? `<div class="panel" style="padding:6px 8px"><div class="table-wrap"><table>
      <thead><tr><th>Holding</th><th style="width:130px">Last year</th><th class="r">Price</th><th class="r">Value</th><th class="r">Weight</th><th class="r">Gain</th><th class="r">Today</th><th class="r">AI share</th></tr></thead>
      <tbody>${body}</tbody></table></div></div>` : '<div class="panel"><p class="muted">No holdings match.</p></div>'}
  </div>`;
  const q = $('#h-q', el);
  q.addEventListener('input', () => { f.q = q.value; clearTimeout(S._qt); S._qt = setTimeout(render, 250); });
  $('#h-plat', el).addEventListener('change', e => { f.platform = e.target.value; render(); });
}

function holdingRow(r) {
  const up = r.spark.length > 1 && r.spark.at(-1)[1] >= r.spark[0][1];
  const badges = r.platforms.map(p => `<span class="badge">${esc(shortPlatform(p.platform))}</span>`).join('');
  const src = r.platforms.map(p => p.value_source).find(Boolean);
  return `<tr class="click" data-holding="${r.instrument_id}">
    <td><div>${esc(r.name)}${badges}</div><div class="sym">${tickerOf(r)}${src === 'broker-same-isin' ? ', priced from the other platform' : src === 'at-cost' ? ', Treasury bill, counted at cost' : ''}</div></td>
    <td>${Charts.spark(r.spark, { w: 120, h: 28, color: up ? 'var(--up)' : 'var(--down)' })}</td>
    <td class="r num">${known(r.price_gbp) ? `<span class="pv">${moneyText(r.price_gbp, 2)}</span>` : '\u2014'}</td>
    <td class="r">${known(r.value) ? money(r.value) : '<span class="warnline">no price</span>'}</td>
    <td class="r num">${pct(r.weight)}</td>
    <td class="r"><div class="${signCls(r.gain)}">${money(r.gain, { sign: true })}</div><div class="tiny ${signCls(r.gain_pct)}">${known(r.gain_pct) ? pct(r.gain_pct, { sign: true }) : (r.anyUnknownCost ? 'cost unknown' : '')}</div></td>
    <td class="r num ${signCls(r.day_change)}">${known(r.day_change) && r.value ? pct(r.day_change / (r.value - r.day_change), { sign: true }) : '\u2014'}</td>
    <td class="r num">${known(r.ai_share) ? `${Math.round(r.ai_share)}%${r.ai_share_set ? '' : '<span class="muted tiny"> sleeve</span>'}` : '<span class="muted">not set</span>'}</td>
  </tr>`;
}
const shortPlatform = n => n.replace(/^Sample \u2014 /, '').replace(/\s*(Stocks\s*)?ISA$/i, '').replace('Trading 212', 'T212') || n;

// ---------------------------------------------------------------------------- one holding

async function openHolding(iid, period) {
  const d = await api(`/api/holding/${iid}`).catch(e => { toast(e.message, true); return null; });
  if (!d) return;
  S.period.holding = period || S.period.holding;
  const i = d.instrument, ccy = d.currency || i.currency || '';
  const days = S.period.holding;
  const cut = (p) => days >= 99999 ? p : sliceSince(p, days);
  const series = [{ name: 'Price', points: cut(d.series), color: 'var(--accent)', width: 2, notMoney: true },
    { name: '50-day average', points: cut(d.sma50), color: 'var(--amber)', dash: '4 3', width: 1.3, notMoney: true },
    { name: '200-day average', points: cut(d.sma200), color: 'var(--muted)', dash: '6 4', width: 1.3, notMoney: true }];
  const markers = d.trades.filter(t => ['BUY', 'SELL'].includes(t.side)).map(t => ({
    date: t.traded_on, shape: t.side === 'SELL' ? 'down' : 'up',
    color: t.side === 'SELL' ? 'var(--red)' : 'var(--green)',
    label: `${t.side === 'SELL' ? 'Sold' : 'Bought'} ${+t.quantity.toFixed(4)} on ${t.platform}` }));
  const priceFmt = v => `${ccy === 'GBP' ? '\u00a3' : ccy === 'USD' ? '$' : ccy === 'EUR' ? '\u20ac' : ''}${v >= 1000 ? v.toFixed(0) : v.toFixed(2)}${['GBP', 'USD', 'EUR', ''].includes(ccy) ? '' : ' ' + ccy}`;
  const total = d.positions.reduce((a, p) => ({ v: a.v + (p.value || 0), c: known(p.cost) ? a.c + p.cost : a.c, unknownCost: a.unknownCost || !known(p.cost) }), { v: 0, c: 0, unknownCost: false });
  const sleeveOpts = `<option value="">Not in a sleeve</option>` + d.sleeves.map(s => `<option value="${s.id}" ${s.id === i.sleeve_id ? 'selected' : ''}>${esc(s.name)}${!i.sleeve_id && s.id === d.suggested_sleeve ? ' (suggested)' : ''}</option>`).join('');
  const body = `<div class="stack-lg">
    <div class="grid g-main">
      <div>
        <div class="spread"><div class="row small">${Object.entries(d.changes).map(([k, v]) => `<span><span class="muted">${k}</span> <span class="num ${signCls(v)}">${pct(v, { sign: true })}</span></span>`).join('')}</div>
          <div class="seg">${[[365, '1Y'], [1095, '3Y'], [1825, '5Y']].map(([v, l]) => `<button type="button" class="${v === days ? 'on' : ''}" data-act="hold-period" data-iid="${iid}" data-v="${v}">${l}</button>`).join('')}</div></div>
        ${d.series.length > 1 ? Charts.line({ series, markers, fmt: priceFmt, yfmt: v => priceFmt(v), label: 'Price' }, 280) :
          `<p class="warnline" style="padding:30px 0">${esc(d.price_error || 'No price history for this holding yet.')} Check the price symbol below.</p>`}
        <div class="legend" style="margin-top:6px"><span><i style="background:var(--accent)"></i>Price in ${esc(ccy || 'its own currency')}</span><span><i style="background:var(--amber)"></i>50-day average</span><span><i style="background:var(--muted)"></i>200-day average</span><span><i style="background:var(--green)"></i>Buys</span></div>
        <p class="chart-note">${known(d.drawdown) ? (d.drawdown < 0.005 ? 'At or near its high of the past year.' : `${pct(d.drawdown)} below its high of the past year${d.high ? ` (${fmtDate(d.high[0])})` : ''}.`) : ''}${d.source ? ` Prices from ${esc(d.source)}, ${ago(d.fetched)}.` : ''}</p>
      </div>
      <div class="stack">
        <dl class="kv">
          <dt>Value</dt><dd>${money(total.v)}</dd>
          <dt>You paid</dt><dd>${total.unknownCost ? '<span class="muted">not known for every platform</span>' : money(total.c)}</dd>
          <dt>Gain</dt><dd class="${signCls(total.v - total.c)}">${total.unknownCost ? '\u2014' : money(total.v - total.c, { sign: true })}</dd>
          <dt>Company</dt><dd>${esc(i.company || '\u2014')}</dd>
          <dt>ISIN</dt><dd>${esc(i.isin || '\u2014')}</dd>
        </dl>
        <table class="small"><thead><tr><th>Platform</th><th class="r">Shares</th><th class="r">Value</th><th></th></tr></thead><tbody>
          ${d.positions.map(p => `<tr><td>${esc(p.platform)}<div class="tiny muted">${p.source === 'api' ? 'from Trading 212' : p.source === 'csv' ? 'from the activity file' : p.source === 'sample' ? 'sample' : 'typed in'}${p.value_as_of ? `, ${ago(p.value_as_of)}` : ''}</div></td>
            <td class="r num">${+p.quantity.toFixed(6)}</td><td class="r">${money(p.value)}</td>
            <td class="r">${p.source !== 'api' ? `<button class="btn small ghost" data-act="adjust" data-pid="${p.platform_id}" data-iid="${iid}" data-q="${p.quantity}">Correct</button> <button class="btn small ghost" data-act="gone" data-pid="${p.platform_id}" data-iid="${iid}">No longer held</button>` : ''}</td></tr>`).join('')}
        </tbody></table>
      </div>
    </div>

    <div class="grid g2">
      <div class="stack">
        <label class="field">Sleeve<select id="hi-sleeve">${sleeveOpts}</select></label>
        <label class="field">Share of this holding that rides on AI (%)
          <input type="number" id="hi-ai" min="0" max="100" step="1" value="${i.ai_share ?? ''}" placeholder="${d.sleeves.find(s => s.id === i.sleeve_id)?.ai_share ?? 'not set'}">
          <span class="help">100 for an AI company, 0 for gold. For a fund, roughly what share of it is in AI-linked companies. Blank uses the sleeve\u2019s figure.</span></label>
        <div class="row">
          <label class="field grow">Company it counts as<input type="text" id="hi-company" value="${esc(i.company || '')}" placeholder="e.g. Alphabet"><span class="help">Two share classes, or the same shares on two platforms, count as one company in rules.</span></label>
          <label class="field grow">Theme<input type="text" id="hi-theme" value="${esc(i.theme || '')}" placeholder="e.g. Freight"><span class="help">Holdings that rise and fall on one idea.</span></label>
        </div>
      </div>
      <div class="stack">
        <label class="field">Price symbol (Yahoo)
          <div class="row"><input type="text" id="hi-sym" value="${esc(i.market_symbol || '')}" class="grow"><button class="btn" data-act="check-sym">Check</button></div>
          <span class="help" id="hi-sym-out">London listings end in .L (VWRP.L); US ones have no suffix (NVDA).</span></label>
        <label class="field">Notes<textarea id="hi-notes" placeholder="Why you hold it, what would make you sell">${esc(i.notes || '')}</textarea></label>
      </div>
    </div>

    <details ${d.lookthrough.length ? 'open' : ''}><summary><b>What this fund holds</b> <span class="muted small">for rules that count exposure through funds</span></summary>
      <div class="stack" style="margin-top:10px">
        <p class="muted small" style="max-width:70ch">Only needed for a fund, and only for the companies your rules are about. Take the weights from the fund\u2019s own factsheet, which gives its top holdings each month.</p>
        ${d.lookthrough.length ? `<table class="small" style="max-width:520px"><tbody>${d.lookthrough.map(l => `<tr><td>${esc(l.company)}</td><td class="r num">${pts(l.weight, 2)}</td><td class="muted tiny">${fmtDate(l.as_of)}</td><td class="r"><button class="btn small ghost" data-act="lt-del" data-iid="${iid}" data-company="${esc(l.company)}">Remove</button></td></tr>`).join('')}</tbody></table>` : ''}
        <div class="row"><input type="text" id="lt-company" placeholder="Company, e.g. Alphabet" style="width:220px"><input type="number" id="lt-weight" placeholder="%" step="0.01" min="0" max="100" style="width:90px"><button class="btn" data-act="lt-add" data-iid="${iid}">Add</button></div>
      </div></details>

    ${d.dividends.length ? `<details><summary><b>Dividends</b> <span class="muted small">${plural(d.dividends.length, 'payment')}</span></summary><table class="small" style="max-width:520px;margin-top:8px"><tbody>${d.dividends.slice(0, 40).map(v => `<tr><td>${fmtDate(v.paid_on)}</td><td>${esc(v.platform)}</td><td class="r">${money(v.amount_gbp, { dp: 2 })}</td></tr>`).join('')}</tbody></table></details>` : ''}
    ${d.trades.length ? `<details><summary><b>Trades</b> <span class="muted small">${plural(d.trades.length, 'trade')}</span></summary><table class="small" style="margin-top:8px"><tbody>${d.trades.slice().reverse().slice(0, 60).map(t => `<tr><td>${fmtDate(t.traded_on)}</td><td>${esc(sideWord(t.side))}</td><td class="r num">${+(+t.quantity).toFixed(6)}</td><td class="r">${money(t.value_gbp, { dp: 2 })}</td><td class="muted">${esc(t.platform)}</td></tr>`).join('')}</tbody></table></details>` : ''}
  </div>`;
  openModal({ title: `${i.name || i.symbol} (${tickerText(i)})`, body, wide: true,
    foot: `<button class="btn" data-act="close">Close</button><button class="btn primary" data-act="hold-save" data-iid="${iid}">Save changes</button>` });
}
const sideWord = s => ({ BUY: 'Bought', SELL: 'Sold', ADJUST: 'Corrected by hand', COST: 'Cost corrected', SET: 'Set to match the platform', TRANSFER_IN: 'Transferred in', TRANSFER_OUT: 'Transferred out', CORPORATE: 'Corporate action' }[s] || s);

ACTS['hold-period'] = b => openHolding(+b.dataset.iid, +b.dataset.v);
ACTS['hold-save'] = async b => {
  const body = {
    sleeve_id: $('#hi-sleeve').value || null, ai_share: $('#hi-ai').value === '' ? null : +$('#hi-ai').value,
    company: $('#hi-company').value, theme: $('#hi-theme').value, market_symbol: $('#hi-sym').value,
    notes: $('#hi-notes').value };
  await busy(b, async () => {
    await api(`/api/instrument/${b.dataset.iid}`, { method: 'PATCH', body });
    closeModal();
    toast('Saved.');
    render();
  });
};
ACTS['check-sym'] = async b => {
  const out = $('#hi-sym-out');
  await busy(b, async () => {
    const r = await api('/api/check-symbol', { method: 'POST', body: { symbol: $('#hi-sym').value } });
    out.innerHTML = r.ok ? `<span class="up">Found${r.name ? `: ${esc(r.name)}` : ''}, last ${esc(r.currency || '')} ${r.price}, on ${fmtDate(r.date)}.</span> Save to use it.`
                         : `<span class="warnline">${esc(r.message || 'Nothing found for that symbol.')}</span>`;
  });
};
ACTS.adjust = b => {
  openModal({ title: 'Correct the share count', body: `
    <p class="lede">When the activity file can\u2019t describe something (a transfer, some corporate actions) the count here can differ from the platform\u2019s. Type what the platform shows. The difference is kept as a correction, so it survives the next import.</p>
    <label class="field" style="max-width:260px">Shares the platform shows<input type="number" id="adj-q" step="any" min="0" value="${b.dataset.q}"></label>`,
    foot: `<button class="btn" data-act="close">Cancel</button><button class="btn primary" data-act="adj-save" data-pid="${b.dataset.pid}" data-iid="${b.dataset.iid}">Save the correction</button>` });
};
ACTS['adj-save'] = async b => {
  await busy(b, async () => {
    await api('/api/positions/adjust', { method: 'POST', body: { platform_id: +b.dataset.pid, instrument_id: +b.dataset.iid, quantity: +$('#adj-q').value } });
    toast('Share count corrected.');
    openHolding(+b.dataset.iid);
    render();
  });
};
ACTS['lt-add'] = async b => {
  await busy(b, async () => {
    await api('/api/lookthrough', { method: 'POST', body: { fund_id: +b.dataset.iid, company: $('#lt-company').value, weight: $('#lt-weight').value } });
    openHolding(+b.dataset.iid);
  });
};
ACTS['lt-del'] = async b => {
  await api('/api/lookthrough', { method: 'POST', body: { fund_id: +b.dataset.iid, company: b.dataset.company, weight: null } });
  openHolding(+b.dataset.iid);
};

ACTS['add-position'] = async () => {
  const st = await api('/api/settings');
  const plats = st.platforms.filter(p => p.provider !== 'trading212');
  if (!plats.length) { toast('Add a platform first (Settings). Trading 212 holdings arrive by themselves.', true); return; }
  openModal({ title: 'Add a holding by hand', body: `
    <p class="lede">For a platform with no connection and no activity file. Trading 212 holdings arrive on their own; Freetrade ones come from its activity file.</p>
    <div class="grid g2">
      <label class="field">Platform<select id="ap-plat">${plats.map(p => `<option value="${p.id}">${esc(p.name)}</option>`).join('')}</select></label>
      <label class="field">Ticker<input type="text" id="ap-sym" placeholder="VWRP or NVDA"></label>
      <label class="field">Listed in<select id="ap-ex"><option value="LSE">London</option><option value="US">United States</option></select></label>
      <label class="field">Name (optional)<input type="text" id="ap-name"></label>
      <label class="field">Shares<input type="number" id="ap-q" step="any" min="0"></label>
      <label class="field">What they cost you, in pounds (optional)<input type="number" id="ap-cost" step="any" min="0"></label>
    </div>`,
    foot: `<button class="btn" data-act="close">Cancel</button><button class="btn primary" data-act="ap-save">Add the holding</button>` });
};
ACTS['ap-save'] = async b => {
  await busy(b, async () => {
    await api('/api/positions', { method: 'POST', body: { platform_id: +$('#ap-plat').value, symbol: $('#ap-sym').value,
      exchange: $('#ap-ex').value, name: $('#ap-name').value, quantity: $('#ap-q').value, cost: $('#ap-cost').value } });
    closeModal();
    toast('Holding added. Its price arrives in a moment.');
    setTimeout(render, 2500);
  });
};

// ============================================================================ Allocation

async function vAllocation(el) {
  const d = await api('/api/allocation');
  const v = d.view;
  if (!v.sleeves.length) {
    el.innerHTML = `<div class="panel"><h2>No sleeves yet</h2><p class="lede">Sleeves are the parts you split your money into, each with a target share. Load a plan file, or start from the template and edit it.</p>
      <div class="row"><button class="btn primary" data-act="plan-wizard">Answer some questions</button><button class="btn" data-act="plan-import">Load a plan file</button><button class="btn" data-act="starter">Start from a template</button></div></div>`;
    return;
  }
  const statusWord = { ok: 'inside its band', amber: 'drifting', red: 'outside its band', none: 'no value yet' };
  const statusCol = st => ({ ok: 'var(--green)', amber: 'var(--amber)', red: 'var(--red)' }[st] || 'var(--grey)');
  // Each row has its own scale, centred on its target, so a 2% sleeve's band is as
  // readable as a 40% sleeve's. What matters here is where a sleeve sits against its
  // own band; the hundred squares alongside show the sizes against each other.
  const bandRows = v.sleeves.map(r => {
    const gap = r.gap_value;
    const reach = Math.max(2.5 * r.band, Math.abs(r.actual - r.target) + 0.4 * r.band);
    const lo = r.target - reach, span = 2 * reach;
    const x = p => `${((p - lo) / span * 100).toFixed(2)}%`;
    const w = d => `${(d / span * 100).toFixed(2)}%`;
    const a = Math.min(r.actual, r.target), b = Math.max(r.actual, r.target);
    const col = statusCol(r.status);
    return `<div class="band-row">
      <div class="band-name"><span class="lvl ${r.status}"></span><span title="${esc(r.name)}">${esc(r.name)}<span class="st">${statusWord[r.status] || ''}</span></span></div>
      <div class="band-track" title="Target ${r.target}%. Inside its band from ${pts(Math.max(0, r.target - r.band))} to ${pts(r.target + r.band)}.">
        <div class="axisline"></div>
        <div class="zone warn" style="left:${x(r.target - r.band)};width:${w(2 * r.band)}"></div>
        <div class="zone" style="left:${x(r.target - r.band / 2)};width:${w(r.band)}"></div>
        <div class="drift" style="left:${x(a)};width:${w(b - a)};background:${col}"></div>
        <div class="tgt" style="left:${x(r.target)}"></div>
        <div class="dot" style="left:${x(r.actual)};background:${col}"></div>
      </div>
      <div class="band-fig"><span class="fig">${pts(r.actual)}</span> <span class="muted">of ${pts(r.target, r.target % 1 ? 1 : 0)}</span>
        <div class="tiny ${r.status === 'ok' ? 'muted' : ''}" style="${r.status === 'red' ? 'color:var(--red)' : r.status === 'amber' ? 'color:var(--amber)' : ''}">${known(gap) && Math.abs(gap) >= 1 ? `${money(Math.abs(gap), { dp: 0 })} ${gap > 0 ? 'under target' : 'over target'}` : 'on target'}</div></div>
    </div>`;
  }).join('');
  el.innerHTML = `<div class="stack-lg">
    <div class="figures" style="grid-template-columns:repeat(3,minmax(0,1fr))">
      <div><div class="k">Inside their bands</div><div class="v">${v.in_band} <span class="muted" style="font-size:1rem">of ${v.sleeves.length}</span></div><div class="s">Within half a band of target</div></div>
      <div><div class="k">Drifting</div><div class="v" style="color:${v.drifting ? 'var(--amber)' : 'inherit'}">${v.drifting}</div><div class="s">Past half the band: watch</div></div>
      <div><div class="k">Outside their bands</div><div class="v" style="color:${v.outside ? 'var(--red)' : 'inherit'}">${v.outside}</div><div class="s">Past the band: worth rebalancing</div></div>
    </div>
    ${v.targets_add_up ? '' : `<div class="panel warnline">Your targets add up to ${v.target_sum}%, not 100%. Fix them in Settings, or every figure below is measured against the wrong thing.</div>`}
    <div class="grid g-main">
      <section class="panel">
        <h2>Where each sleeve sits</h2>
        <p class="lede">The tick is the target and the dot is where the sleeve is now. Green is close enough to leave alone; amber is drifting; past the amber it is outside its band. A band is 5 points either side of target, or a quarter of the target when that is smaller (the \u201c5/25\u201d rule).</p>
        <div class="bands">${bandRows}</div>
        ${d.unassigned.length ? `<p class="warnline" style="margin-top:10px">${plural(d.unassigned.length, 'holding')} not in a sleeve yet, worth ${money(d.unassigned.reduce((a, u) => a + (u.value || 0), 0))}. They are left out of the percentages above until sorted, below.</p>` : ''}
      </section>
      <div class="stack">
        <section class="panel"><h2>Every pound, as a hundred squares</h2>
          <p class="lede">Each square is 1% of everything, cash included.</p>
          <div class="row" style="align-items:flex-start;gap:18px;flex-wrap:wrap">${Charts.waffle(d.waffle)}
            <div class="legend" style="display:grid;gap:3px">${v.sleeves.concat(v.extra).filter(r => r.actual > 0).map(r => `<span><i style="background:${r.colour}"></i>${esc(r.name)} <span class="muted">${pts(r.actual, 0)}</span></span>`).join('')}</div></div>
        </section>
        <section class="panel"><h2>Put new money to work</h2>
          <p class="lede">Paying into the sleeves that are furthest under target fixes drift without selling anything.</p>
          <div class="row"><input type="number" id="nm-amount" min="1" step="50" placeholder="Amount in \u00a3" style="width:160px"><button class="btn primary" data-act="new-money">Split it</button></div>
          <div id="nm-out" style="margin-top:12px"></div>
        </section>
      </div>
    </div>
    <section class="panel"><div class="spread"><h2>Your rules</h2><button class="btn" data-act="rule-add">Add a rule</button></div>
      <p class="lede">Limits you have set for yourself: a company, a theme, or AI as a whole. Each shows where it stands against its trigger.</p>
      ${d.rules.length ? `<div class="stack">${d.rules.map(ruleRow).join('')}</div>` : '<p class="muted">No rules yet. A common one: trim a single company back once it passes a set share of the portfolio.</p>'}
    </section>
    ${targetsPanel(d.holding_targets)}
    ${d.unassigned.length ? unassignedPanel(d) : ''}
  </div>`;
}

function ruleRow(r) {
  const what = r.kind === 'company_cap' ? `${esc(r.subject)}${r.basis === 'true' ? ', counting funds' : ', held directly'}`
    : r.kind === 'theme_cap' ? `${esc(r.subject)} theme` : 'Everything AI-linked, looked through funds';
  const top = Math.max(r.trigger * 1.35, (r.now || 0) * 1.1);
  const x = p => `${Math.max(0, Math.min(100, p / top * 100))}%`;
  const lvl = r.level === 'none' ? '' : r.level;
  const detail = r.detail && r.detail.holdings ? r.detail.holdings.map(h => `${esc(h.platform)} ${money(h.value, { dp: 0 })}`).join(', ') : '';
  return `<div class="band-row" style="grid-template-columns:minmax(160px,240px) 1fr 200px">
    <div><div class="row"><span class="lvl ${lvl}"></span><b>${what}</b></div>${r.note ? `<div class="tiny muted">${esc(r.note)}</div>` : ''}${detail ? `<div class="tiny muted">${detail}</div>` : ''}</div>
    <div class="band-track">
      <div class="axisline"></div>
      ${known(r.target) ? `<div class="tgt" style="left:${x(r.target)};background:var(--green)" title="Back to ${r.target}%"></div>` : ''}
      <div class="act" style="left:0;width:${x(r.now || 0)};background:${colourOf(lvl || 'none')}"></div>
      <div class="tgt" style="left:${x(r.trigger)};background:var(--red);width:3px" title="Trigger ${r.trigger}%"></div>
    </div>
    <div class="band-fig"><span class="fig">${pts(r.now)}</span> <span class="muted">trigger ${r.trigger}%</span>
      <div class="tiny">${r.level === 'red' && r.trim ? `Back to ${r.target}% means selling about ${money(r.trim, { dp: 0 })}` : known(r.target) ? `Trim back to ${r.target}%` : ''}
      <button class="btn small ghost" data-act="rule-del" data-id="${r.id}">Remove</button></div></div>
  </div>`;
}

function unassignedPanel(d) {
  const opts = sel => `<option value="">Choose a sleeve</option>` + d.sleeves.map(s => `<option value="${s.id}" ${s.id === sel ? 'selected' : ''}>${esc(s.name)}</option>`).join('');
  return `<section class="panel"><div class="spread"><h2>Holdings not in a sleeve yet</h2><button class="btn primary" data-act="assign-save">Save these</button></div>
    <p class="lede">The suggestions come from each holding\u2019s name. Check them: a fund called \u201cglobal\u201d might really be tech-heavy.</p>
    <div class="table-wrap"><table><tbody>${d.unassigned.map(u => `<tr><td>${esc(u.name)}<div class="tiny muted">${esc(u.platform)}</div></td><td class="r">${money(u.value)}</td>
      <td style="width:260px"><select data-assign="${u.instrument_id}">${opts(u.suggested)}</select></td></tr>`).join('')}</tbody></table></div></section>`;
}
ACTS['assign-save'] = async b => {
  const items = $$('[data-assign]').filter(s => s.value).map(s => ({ instrument_id: +s.dataset.assign, sleeve_id: +s.value }));
  if (!items.length) { toast('Choose a sleeve for at least one holding.', true); return; }
  await busy(b, async () => { await api('/api/assign', { method: 'POST', body: { items } }); toast(`${plural(items.length, 'holding')} sorted.`); render(); });
};
ACTS['new-money'] = async b => {
  const amount = +$('#nm-amount').value;
  if (!(amount > 0)) { toast('Type an amount first.', true); return; }
  await busy(b, async () => {
    const r = await api('/api/allocation/new-money', { method: 'POST', body: { amount } });
    const rows = r.split.filter(s => s.amount >= 0.5).sort((a, c) => c.amount - a.amount);
    $('#nm-out').innerHTML = `<table class="small"><thead><tr><th>Sleeve</th><th class="r">Put in</th><th class="r">Then</th></tr></thead><tbody>${rows.map(s => `
      <tr><td><span class="lvl" style="background:${s.colour};margin-right:6px"></span>${esc(s.name)}</td><td class="r">${money(s.amount, { dp: 0 })}</td>
      <td class="r num">${pts(s.from_pct)} <span class="muted">to</span> ${pts(s.to_pct)} <span class="muted">(${pts(s.target, 0)})</span></td></tr>`).join('')}</tbody></table>
      <p class="note" style="margin-top:6px">Arithmetic on your own targets, not advice. It says nothing about which holding inside a sleeve to buy.</p>`;
  });
};
ACTS['rule-del'] = async b => {
  if (!await confirmBox('Remove this rule?', 'It stops being checked straight away. You can add it again at any time.', 'Remove the rule', true)) return;
  await api(`/api/rules/${b.dataset.id}`, { method: 'DELETE' }).catch(e => toast(e.message, true));
  render();
};
ACTS['rule-add'] = () => {
  openModal({ title: 'Add a rule', body: `<div class="stack">
    <label class="field">What it limits<select id="ru-kind"><option value="company_cap">One company</option><option value="theme_cap">A theme (holdings that ride on one idea)</option><option value="ai_cap">Everything AI-linked</option></select></label>
    <label class="field" id="ru-subject-f">Company or theme, exactly as set on the holdings<input type="text" id="ru-subject" placeholder="Alphabet"></label>
    <div class="row"><label class="field grow">Trigger: act when it passes (%)<input type="number" id="ru-trig" step="0.1" min="0.1" max="100"></label>
      <label class="field grow">Bring it back to (%, optional)<input type="number" id="ru-tgt" step="0.1" min="0" max="100"></label></div>
    <label class="field" id="ru-basis-f">Count<select id="ru-basis"><option value="direct">Shares held directly</option><option value="true">Directly and through funds (needs fund holdings on each fund)</option></select></label>
    <label class="field">A note to your future self (optional)<input type="text" id="ru-note" placeholder="Why this limit exists"></label></div>`,
    foot: `<button class="btn" data-act="close">Cancel</button><button class="btn primary" data-act="rule-save">Add the rule</button>` });
  $('#ru-kind').addEventListener('change', e => {
    $('#ru-subject-f').hidden = e.target.value === 'ai_cap';
    $('#ru-basis-f').hidden = e.target.value !== 'company_cap';
  });
};
ACTS['rule-save'] = async b => {
  await busy(b, async () => {
    await api('/api/rules', { method: 'POST', body: { kind: $('#ru-kind').value, subject: $('#ru-subject').value,
      trigger: $('#ru-trig').value, target: $('#ru-tgt').value, basis: $('#ru-basis').value, note: $('#ru-note').value } });
    closeModal();
    toast('Rule added.');
    render();
  });
};

// ============================================================================ AI watch

async function vAI(el) {
  const d = await api('/api/ai');
  const m = d.market, e = d.exposure, t = d.totals;
  setDot('ai', m.regime === 'turning' || m.regime === 'stress' ? 'red' : m.regime === 'watch' ? 'amber' : null);
  const regimeCol = r => ({ calm: 'var(--mon-green)', watch: 'var(--mon-amber)', turning: 'var(--mon-red)', stress: '#b0302a' }[r] || 'var(--mon-line)');
  const strip = m.strip;
  const alarm = m.regime === 'turning' || m.regime === 'stress';
  const plans = d.plans || {};
  el.innerHTML = `<div class="stack-lg">
  <section class="monitor">
    <div class="monitor-head">
      <div style="color:var(--mon-ink)">${Charts.gauge(needle(m), { zones: GAUGE_ZONES, size: 260, label: m.label })}
        <div class="row tiny" style="justify-content:space-between;color:var(--mon-muted);padding:0 6px"><span>Calm</span><span>Watch</span><span>Turning</span><span>Stress</span></div></div>
      <div>
        <div class="regime-word ${m.regime}">${esc(m.label)}</div>
        <p style="margin-top:10px;max-width:62ch">${esc(m.text)}</p>
        <p class="muted small" style="margin-top:8px;max-width:62ch">Based on ${m.have} of ${m.of} lights. Every light describes what prices have already done. None can say what happens next, and each has gone red in falls that recovered within months.</p>
      </div>
    </div>
    ${strip.length ? `<div class="strip-wrap"><div class="spread tiny muted"><span>The same reading for each day of the last two years</span><span>${fmtDate(strip[0][0])} to ${fmtDate(strip.at(-1)[0])}</span></div>
      <div style="margin-top:6px;border-radius:4px;overflow:hidden">${Charts.strip(strip, regimeCol)}</div>
      <div class="legend" style="margin-top:6px">${['calm', 'watch', 'turning', 'stress'].map(r => `<span><i style="background:${regimeCol(r)}"></i>${r[0].toUpperCase() + r.slice(1)} ${pct(strip.filter(s => s[1] === r).length / strip.length, { dp: 0 })} of days</span>`).join('')}</div></div>` : ''}
    <h3 class="trace-group">Markets in general</h3>
    <div class="traces">${m.lights.filter(x => x.group === 'market').map(trace).join('')}</div>
    ${d.narratives ? `<p class="trace-note">${narr(d.narratives.market)}</p>` : ''}
    <h3 class="trace-group">The economy and money</h3>
    <div class="traces">${m.lights.filter(x => x.group === 'economy').map(trace).join('')}</div>
    ${d.narratives ? `<p class="trace-note">${narr(d.narratives.economy)}</p>` : ''}
    <h3 class="trace-group">The AI trade</h3>
    <div class="traces">${m.lights.filter(x => x.group === 'ai').map(trace).join('')}</div>
    ${d.narratives ? `<p class="trace-note">${narr(d.narratives.ai)}</p>` : ''}
  </section>

  ${playbookPanels(d.playbook, d.narratives && d.narratives.signals)}

  ${planPanel(plans, alarm || (d.playbook && d.playbook.tier.level === 'red'))}

  <div class="grid g2">
    <section class="panel"><h2>How much of your money rides on AI</h2>
      <p class="lede">Companies count in full; funds count for the share of them you have set. An S&P 500 fund is partly AI, because the biggest companies in it are.</p>
      ${exposureBlock(e, t, d.cap)}
    </section>
    <section class="panel"><h2>What a fall would cost</h2>
      <p class="lede">Move the sliders, or pick an illustration. Cash stays put. This is arithmetic on today\u2019s holdings, not a forecast.</p>
      <div class="pill-row" style="margin-bottom:12px">
        <button class="btn small" data-act="stress-preset" data-ai="20" data-other="5">A correction</button>
        <button class="btn small" data-act="stress-preset" data-ai="45" data-other="20">A bear market</button>
        <button class="btn small" data-act="stress-preset" data-ai="50" data-other="45">2008-sized, everything</button>
        <button class="btn small" data-act="stress-preset" data-ai="80" data-other="35">Dot-com sized</button>
      </div>
      <label class="field">AI-linked holdings fall by <b><span id="st-ai-v">40</span>%</b><input type="range" id="st-ai" min="0" max="90" value="40"></label>
      <label class="field" style="margin-top:8px">Everything else invested falls by <b><span id="st-o-v">15</span>%</b><input type="range" id="st-o" min="0" max="60" value="15"></label>
      <div id="st-out" style="margin-top:14px"></div>
      <p class="note" style="margin-top:10px">${esc(d.dotcom)}${d.worst ? ` The worst fall for today\u2019s mix in the last five years was ${pct(-d.worst.depth)}, from ${fmtDate(d.worst.peak)} to ${fmtDate(d.worst.trough)}${d.coverage < 0.99 ? ` (covering ${pct(d.coverage, { dp: 0 })} of it)` : ''}.` : ''}</p>
    </section>
  </div>

  ${d.context.length ? `<section class="panel"><h2>Background</h2><p class="lede">No lights here, just context worth glancing at.</p>
    <div class="grid g3">${d.context.map(c => `<div><h3>${esc(c.title)}</h3>
      <div class="small muted">${known(c.value) ? `Now ${c.key === 'US10Y' ? pts(c.value, 2) : c.key === 'GBPUSD' ? '$' + c.value.toFixed(3) : c.value.toFixed(3)}, ` : ''}${known(c.change_1y_pts) ? `${ptsChange(c.change_1y_pts)} in a year` : known(c.change_1y) ? `${pct(c.change_1y, { sign: true })} in a year` : ''}</div>
      ${Charts.line({ series: [{ name: c.title, points: c.spark, color: 'var(--cyan)', notMoney: true }], fmt: v => v.toFixed(c.key === 'GBPUSD' ? 3 : 2), yfmt: v => v.toFixed(c.key === 'US10Y' ? 1 : 2) }, 140)}
      ${c.explain ? `<p class="note">${esc(c.explain)}</p>` : ''}</div>`).join('')}</div></section>` : ''}
  <p class="note">Whiskers is a tool for keeping to your own plan. It isn\u2019t financial advice, and nothing on this screen is a recommendation to buy or sell.</p>
  </div>`;
  const draw = () => {
    const ai = +$('#st-ai').value / 100, oth = +$('#st-o').value / 100;
    $('#st-ai-v').textContent = Math.round(ai * 100);
    $('#st-o-v').textContent = Math.round(oth * 100);
    const total = t.total || 0, cash = t.cash || 0, aiv = e.ai_value || 0;
    const other = Math.max(0, total - cash - aiv);
    const lossA = aiv * ai, lossO = other * oth, after = total - lossA - lossO;
    const w = v => total ? `${v / total * 100}%` : '0';
    $('#st-out').innerHTML = !total ? '<p class="muted">Nothing to test yet.</p>' : `
      <div class="small muted">Today</div>
      <div style="display:flex;height:16px;border-radius:4px;overflow:hidden;margin:3px 0 8px">
        <div style="width:${w(aiv)};background:var(--red)" title="AI-linked"></div><div style="width:${w(other)};background:var(--accent)" title="Everything else"></div><div style="width:${w(cash)};background:var(--grey)" title="Cash"></div></div>
      <div class="small muted">After the fall</div>
      <div style="display:flex;height:16px;border-radius:4px;overflow:hidden;margin:3px 0 10px">
        <div style="width:${w(aiv - lossA)};background:var(--red)"></div><div style="width:${w(other - lossO)};background:var(--accent)"></div><div style="width:${w(cash)};background:var(--grey)"></div></div>
      <div class="spread"><span><span class="fig" style="font-size:1.5rem">${money(after, { dp: 0 })}</span> <span class="muted">from ${money(total, { dp: 0 })}</span></span>
        <span class="fig down" style="font-size:1.3rem">${money(-(lossA + lossO), { dp: 0 })} (${pct(-(lossA + lossO) / total)})</span></div>
      <div class="tiny muted" style="margin-top:4px">AI-linked part ${money(-lossA, { dp: 0 })}, everything else ${money(-lossO, { dp: 0 })}, cash unchanged.${e.unknown_value ? ` ${money(e.unknown_value, { dp: 0 })} not rated for AI is counted as everything else.` : ''}</div>`;
  };
  setTimeout(() => { ['#st-ai', '#st-o'].forEach(s => $(s)?.addEventListener('input', draw)); if ($('#st-ai')) draw(); }, 0);
  ACTS['stress-preset'] = b => { $('#st-ai').value = b.dataset.ai; $('#st-o').value = b.dataset.other; draw(); };
}

function trace(x) {
  const col = monColour(x.level);
  const word = { green: 'Normal', amber: 'Look', red: 'Alarm', none: 'No data' }[x.level] || 'No data';
  return `<div class="trace ${x.level}">
    <div class="top"><span class="name">${esc(x.title)}</span><span class="state">${word}</span></div>
    <div class="tiny muted">${esc(x.sub)}</div>
    <div class="words">${esc(x.words)}</div>
    ${x.since ? `<div class="tiny" style="color:var(--mon-muted)">${word} since ${fmtDate(x.since)}${x.direction && x.direction !== 'steady' ? `; ${x.direction} over the past month` : '; steady over the past month'}</div>` : ''}
    <div>${Charts.spark(x.spark, { w: 240, h: 44, color: col, area: false, avg: x.avg || null })}</div>
    <details><summary>What this means</summary><p style="margin-top:4px">${esc(x.explain)}</p>${x.as_of ? `<p style="margin-top:4px">Last reading ${fmtDate(x.as_of)}.</p>` : ''}</details>
  </div>`;
}

function exposureBlock(e, t, cap) {
  if (!t.total) return '<p class="muted">Nothing held yet.</p>';
  const w = v => `${Math.max(0, v / t.total * 100)}%`;
  const other = Math.max(0, t.total - (t.cash || 0) - e.ai_value);
  return `<div class="row" style="align-items:baseline;gap:12px"><span class="fig" style="font-size:2.4rem">${pct(e.ai_pct, { dp: 0 })}</span>
      <span>${money(e.ai_value, { dp: 0 })} of ${money(t.total, { dp: 0 })}${cap ? `, against your ${cap.trigger_pct}% limit` : ''}</span></div>
    <div style="display:flex;height:14px;border-radius:4px;overflow:hidden;margin:10px 0 6px">
      <div style="width:${w(e.ai_value)};background:var(--red)"></div><div style="width:${w(other)};background:var(--accent)"></div><div style="width:${w(t.cash || 0)};background:var(--grey)"></div></div>
    <div class="legend"><span><i style="background:var(--red)"></i>Rides on AI</span><span><i style="background:var(--accent)"></i>Everything else</span><span><i style="background:var(--grey)"></i>Cash</span></div>
    <table class="small" style="margin-top:12px"><thead><tr><th>Biggest contributors</th><th class="r">AI share</th><th class="r">Counts as</th></tr></thead><tbody>
      ${e.top.slice(0, 10).map(r => `<tr class="click" data-holding="${r.instrument_id}"><td>${esc(r.name)}${r.platforms.length > 1 ? ` <span class="badge">${r.platforms.length} platforms</span>` : ''}</td><td class="r num">${Math.round(r.share)}%</td><td class="r">${money(r.ai_value, { dp: 0 })}</td></tr>`).join('')}
    </tbody></table>
    ${e.unknown.length ? `<p class="warnline" style="margin-top:8px">Not rated yet: ${e.unknown.slice(0, 6).map(u => `<a href="#" data-holding="${u.instrument_id}">${esc(u.name)}</a>`).join(', ')}${e.unknown.length > 6 ? ` and ${e.unknown.length - 6} more` : ''}. Set an AI share on each, or on its sleeve in Settings.</p>` : ''}`;
}

function planPanel(plans, alarm) {
  const ai = plans.ai?.body || '', crash = plans.crash?.body || '';
  const editing = S.editPlans || (!ai && !crash);
  if (!editing) {
    return `<section class="plan-box ${alarm ? 'alarm' : ''}"><div class="spread"><h2>${alarm ? 'Your plan, written in calm weather' : 'Your plan'}</h2><button class="btn small" data-act="plan-edit">Edit</button></div>
      <div class="grid g2" style="margin-top:10px">
        <div><h3>If the AI trade turns</h3><p class="plan-text">${esc(ai) || '<span class="muted">Not written yet.</span>'}</p></div>
        <div><h3>In any big fall</h3><p class="plan-text">${esc(crash) || '<span class="muted">Not written yet.</span>'}</p></div>
      </div>
      <p class="tiny muted" style="margin-top:8px">${plans.ai?.updated_at ? `Last changed ${ago(plans.ai.updated_at)}.` : ''}</p></section>`;
  }
  return `<section class="plan-box"><h2>Write down your plan while things are calm</h2>
    <p class="small" style="margin:4px 0 12px;max-width:75ch">Decided in advance, a plan is much easier to follow than a decision made during a fall. It appears at the top of this screen, in red, whenever the lights turn.</p>
    <div class="grid g2">
      <label class="field">If the AI trade turns, I will\u2026<textarea id="plan-ai" placeholder="For example: keep contributing monthly, rebalance back to target once the Tech sleeve leaves its band, not sell anything else.">${esc(ai)}</textarea></label>
      <label class="field">In any big fall, I will\u2026<textarea id="plan-crash" placeholder="For example: not look more than weekly, use cash to top up whichever sleeves fall below their bands.">${esc(crash)}</textarea></label>
    </div>
    <div class="row" style="margin-top:10px"><button class="btn primary" data-act="plan-save">Save my plan</button>${ai || crash ? '<button class="btn ghost" data-act="plan-cancel">Cancel</button>' : ''}</div></section>`;
}
ACTS['plan-edit'] = () => { S.editPlans = true; render(); };
ACTS['plan-cancel'] = () => { S.editPlans = false; render(); };
ACTS['plan-save'] = async b => {
  await busy(b, async () => {
    await api('/api/plans/ai', { method: 'PUT', body: { body: $('#plan-ai').value } });
    await api('/api/plans/crash', { method: 'PUT', body: { body: $('#plan-crash').value } });
    S.editPlans = false;
    toast('Plan saved.');
    render();
  });
};

// ============================================================================ Markets

const GROUPS = [['ai', 'The AI trade'], ['markets', 'Stock markets'], ['sectors', 'Sectors'],
                ['commodities', 'Commodities'], ['rates', 'Rates and the pound'], ['stress', 'Stress gauges']];

async function vMarkets(el) {
  const d = await api('/api/markets');
  const keys = S.compare.filter(k => d.series.some(s => s.key === k));
  const cmp = keys.length ? await api(`/api/series?keys=${keys.map(k => 'REF:' + k).join(',')}&days=${S.period.compare}&rebase=1`) : { series: [] };
  const palette = ['var(--accent)', '#b35c00', '#7b3fc4', '#2f5bd3', '#c0392b', '#3d7d2c'];
  const unitFmt = s => !known(s.value) ? '\u2014' : s.unit === '%' ? pts(s.value, 2) : s.unit === '$' ? '$' + s.value.toFixed(s.value < 10 ? 3 : 2)
    : s.unit === '\u00a3' ? '\u00a3' + s.value.toFixed(2) : s.value >= 1000 ? Math.round(s.value).toLocaleString('en-GB') : s.value.toFixed(2);
  el.innerHTML = `<div class="stack-lg">
    <section class="panel"><div class="spread"><div><h2>Compare</h2><p class="lede" style="margin:0">Each line starts at 100, so you can see which did better. Tick up to six cards below.</p></div>
      <div class="seg">${[[365, '1Y'], [1095, '3Y'], [1825, '5Y']].map(([v, l]) => segBtn('cmp-period', v, l, S.period.compare)).join('')}</div></div>
      <div style="margin-top:10px">${Charts.line({ series: cmp.series.map((s, i) => ({ name: s.label, points: s.points, color: palette[i % palette.length], width: 1.8, notMoney: true })),
        fmt: v => v.toFixed(1), yfmt: v => v.toFixed(0), hlines: [{ v: 100, color: 'var(--muted)', dash: '2 4', opacity: .6 }], empty: 'Tick a card below to compare it.' }, 260)}</div>
    </section>
    ${GROUPS.map(([g, title]) => {
      const cards = d.series.filter(s => s.group === g);
      if (!cards.length) return '';
      return `<section><h2 style="margin-bottom:6px">${title}</h2>${d.narratives && d.narratives[g] ? `<p class="narrative">${narr(d.narratives[g])}</p>` : ''}<div class="markets-grid">${cards.map(s => {
        const on = S.compare.includes(s.key);
        const up = s.spark.length > 1 && s.spark.at(-1)[1] >= s.spark[0][1];
        return `<div class="mcard ${on ? 'picked' : ''}">
          <div class="spread"><b>${esc(s.label)}</b><label class="tiny row" style="gap:4px"><input type="checkbox" data-act="cmp-toggle" data-key="${s.key}" ${on ? 'checked' : ''}>Compare</label></div>
          <div class="spread"><span class="val">${unitFmt(s)}</span><span class="tiny muted">${s.as_of ? fmtDate(s.as_of) : ''}</span></div>
          <div class="changes">${[['1m', 'month'], ['1y', 'year'], ['5y', '5 years']].map(([k, l]) => `<span class="${s.priced ? signCls(s.changes[k]) : ''}" title="Change over a ${l}"><span class="muted" style="font-family:var(--sans)">${k}</span> ${s.changes_in_points ? ptsChange(s.changes[k]) : pct(s.changes[k], { sign: true })}</span>`).join('')}</div>
          ${Charts.spark(s.spark, { w: 280, h: 38, color: !s.priced ? 'var(--cyan)' : up ? 'var(--up)' : 'var(--down)' })}
          ${known(s.drawdown) && s.drawdown > 0.1 && s.priced ? `<div class="tiny warnline">${pct(s.drawdown)} below its high of the past year</div>` : ''}
          ${s.fetch_error ? `<div class="err">Couldn\u2019t fetch: ${esc(s.fetch_error)}</div>` : ''}
          <div class="small">${esc(s.blurb)}</div>
          <div class="why">${esc(s.why)}</div>
          ${s.linked.length ? `<div class="yours">Your ${s.linked.map(l => `${esc(l.name)} sleeve${known(l.actual) ? ` (${pts(l.actual)})` : ''}`).join(', ')} follows this.</div>` : ''}
        </div>`;
      }).join('')}</div></section>`;
    }).join('')}
    <p class="note">Prices come from Yahoo Finance\u2019s public charts and the Federal Reserve Bank of St. Louis (FRED). They can be delayed, and Yahoo\u2019s service is unofficial, so a figure here can occasionally be missing or late.</p>
  </div>`;
}
ACTS['cmp-period'] = b => { S.period.compare = +b.dataset.v; render(); };
ACTS['cmp-toggle'] = b => {
  const k = b.dataset.key;
  if (b.checked) { if (S.compare.length >= 6) { b.checked = false; toast('Six at a time is plenty. Untick one first.'); return; } S.compare.push(k); }
  else S.compare = S.compare.filter(x => x !== k);
  render();
};

// ============================================================================ Activity

async function vActivity(el) {
  const d = await api('/api/activity');
  const i = d.isa;
  const isaBars = d.isa_history.map(h => ({ label: h.label, value: h.used, long: `Tax year ${h.label}`, color: h.used > h.limit ? 'var(--red)' : 'var(--accent)' }));
  const divBars = d.dividends.map(m => ({ label: MONTHS[+m.month.slice(5) - 1], long: `${MONTHS[+m.month.slice(5) - 1]} ${m.month.slice(0, 4)}`, value: m.amount }));
  const div12 = d.dividends.slice(-12).reduce((a, m) => a + m.amount, 0);
  el.innerHTML = `<div class="stack-lg">
    <div class="grid g2">
      <section class="panel"><h2>ISA allowance</h2>
        <p class="lede">\u00a3${Math.round(i.limit).toLocaleString('en-GB')} a tax year across every ISA. A flexible ISA (Trading 212\u2019s is) lets money taken out go back in the same year without counting twice. Transfers from another ISA don\u2019t count.</p>
        ${i.has_data ? `<div class="row" style="gap:18px">${Charts.ring(i.limit ? i.used / i.limit : 0, { size: 130, color: i.over ? 'var(--red)' : 'var(--accent)', text: pct(i.limit ? i.used / i.limit : 0, { dp: 0 }), sub: i.label })}
          <div class="small grow"><div><span class="fig" style="font-size:1.3rem">${money(i.used, { dp: 0 })}</span> paid in, ${money(i.remaining, { dp: 0 })} left</div>
          ${i.platforms.map(p => `<div>${esc(p.name)}: ${money(p.deposits, { dp: 0 })} in${p.withdrawals ? `, ${money(p.withdrawals, { dp: 0 })} out` : ''}${p.flexible ? ' (flexible)' : ''}</div>`).join('')}
          ${i.transfers ? `<div class="muted">${money(i.transfers, { dp: 0 })} transferred in, not counted.</div>` : ''}</div></div>
          <div style="margin-top:12px">${Charts.bars({ items: isaBars, money: true, fmt: v => moneyText(v, 0), yfmt: compactMoney, hlines: [{ v: i.limit, color: 'var(--muted)', label: 'Allowance' }] }, 170)}</div>`
          : '<p class="muted">Needs deposit history, from a Trading 212 sync or a Freetrade activity file.</p>'}
      </section>
      <section class="panel"><h2>Dividends</h2><p class="lede">${money(div12, { dp: 0 })} in the last twelve months.</p>
        ${Charts.bars({ items: divBars, money: true, fmt: v => moneyText(v, 2), yfmt: compactMoney, color: 'var(--green)' }, 190)}
        ${d.dividends_by_holding.length ? `<table class="small" style="margin-top:10px"><tbody>${d.dividends_by_holding.map(r => `<tr><td>${esc(r.name || 'Unknown')}</td><td class="r">${money(r.amount, { dp: 2 })}</td></tr>`).join('')}</tbody></table>` : ''}
      </section>
    </div>
    <section class="panel"><h2>Money paid in</h2><p class="lede">Deposits less withdrawals, over time.</p>
      ${Charts.line({ series: [{ name: 'Paid in', points: d.money_in, color: 'var(--accent)', area: true }], money: true, fmt: v => moneyText(v, 0), yfmt: compactMoney, empty: 'No deposits recorded yet.' }, 200)}
    </section>
    <section class="panel"><div class="spread"><h2>Trades</h2><span class="muted small">${d.fees_12m ? `${money(d.fees_12m, { dp: 2 })} in stamp duty and FX fees over the last year` : ''}</span></div>
      ${d.trades.length ? `<div class="table-wrap" style="max-height:520px;overflow:auto;margin-top:8px"><table><thead><tr><th>Date</th><th>What</th><th>Holding</th><th class="r">Shares</th><th class="r">Amount</th><th>Platform</th></tr></thead><tbody>
        ${d.trades.map(t => `<tr ${t.instrument_id ? `class="click" data-holding="${t.instrument_id}"` : ''}><td class="nowrap">${fmtDate(t.traded_on)}</td><td>${esc(sideWord(t.side))}</td><td>${esc(t.name || t.symbol || '')}</td><td class="r num">${+(+t.quantity).toFixed(6)}</td><td class="r">${money(t.value_gbp, { dp: 2 })}</td><td class="muted small">${esc(t.platform)}</td></tr>`).join('')}
      </tbody></table></div>` : '<p class="muted">No trades recorded yet.</p>'}
    </section>
    ${d.moves.length ? `<section class="panel"><h2>Cash in and out</h2><div class="table-wrap"><table><tbody>${d.moves.map(c => `<tr><td class="nowrap">${fmtDate(c.happened_on)}</td><td>${esc({ DEPOSIT: 'Paid in', WITHDRAWAL: 'Taken out', INTEREST: 'Interest', FEE: 'Fee', TRANSFER: 'Transfer' }[c.kind] || c.kind)}</td><td class="r ${signCls(c.amount_gbp)}">${money(c.amount_gbp, { dp: 2, sign: true })}</td><td class="muted small">${esc(c.platform)}</td></tr>`).join('')}</tbody></table></div></section>` : ''}
  </div>`;
}

// ============================================================================ Settings

async function vSettings(el) {
  const d = await api('/api/settings');
  const up = await api('/api/update').catch(() => null);
  const s = d.settings;
  const tsum = d.sleeves.reduce((a, x) => a + x.target, 0);
  el.innerHTML = `<div class="stack-lg">
    <section class="panel"><div class="spread"><h2>Platforms</h2><div class="row"><button class="btn" data-act="add-platform" data-kind="trading212">Add Trading 212</button><button class="btn" data-act="add-platform" data-kind="freetrade">Add Freetrade</button><button class="btn ghost" data-act="add-platform" data-kind="other">Another</button></div></div>
      <p class="lede">Each platform is checked against the protection limit on its own, because FSCS protection is per firm.</p>
      <div class="stack">${d.platforms.some(p => p.kind === 'platform') ? d.platforms.filter(p => p.kind === 'platform').map(platformRow).join('<hr class="soft">') : '<p class="muted">None yet.</p>'}</div>
    </section>

    <section class="panel"><div class="spread"><h2>Your plan</h2><div class="row"><button class="btn" data-act="plan-wizard">Build a plan from questions</button><button class="btn" data-act="plan-import">Load a plan file</button><button class="btn" data-act="plan-export">Save a copy of your plan</button></div></div>
      ${d.plan_loaded ? `<p class="note">Plan file last loaded ${fmtDate(d.plan_loaded.at)}.</p>` : '<p class="warnline">No plan file loaded yet. Load one to set your sleeves, targets, rules and playbook in one go.</p>'}
      <p class="lede">Sleeves and their targets. Targets must add up to 100. A blank band uses the 5/25 rule; the AI share is the default for holdings in that sleeve.</p>
      <div class="table-wrap"><table class="small"><thead><tr><th>Sleeve</th><th class="r">Target %</th><th class="r">Band \u00b1</th><th class="r">AI share %</th><th>Cash sleeve</th><th>Colour</th><th></th></tr></thead><tbody>
        ${d.sleeves.map(x => `<tr data-sleeve="${x.id}">
          <td><input type="text" data-f="name" value="${esc(x.name)}" style="width:100%"></td>
          <td class="r"><input type="number" data-f="target" value="${x.target}" step="0.5" min="0" max="100" style="width:80px"></td>
          <td class="r"><input type="number" data-f="band" value="${x.band ?? ''}" step="0.25" min="0.1" placeholder="${Math.max(0.25, Math.min(5, 0.25 * x.target)).toFixed(2)}" style="width:80px"></td>
          <td class="r"><input type="number" data-f="ai_share" value="${x.ai_share ?? ''}" step="5" min="0" max="100" placeholder="per holding" style="width:120px"></td>
          <td><input type="checkbox" data-f="is_cash" ${x.is_cash ? 'checked' : ''} aria-label="Cash sleeve"></td>
          <td><input type="color" data-f="colour" value="${x.colour}" aria-label="Colour"></td>
          <td class="r"><button class="btn small ghost danger" data-act="sleeve-del" data-id="${x.id}">Remove</button></td></tr>`).join('')}
      </tbody></table></div>
      <div class="spread" style="margin-top:10px"><span class="${Math.abs(tsum - 100) < 0.01 ? 'muted' : 'warnline'} small">Targets add up to ${+tsum.toFixed(2)}%${Math.abs(tsum - 100) < 0.01 ? '.' : ', not 100%.'}</span>
        <div class="row"><button class="btn" data-act="sleeve-add">Add a sleeve</button><button class="btn primary" data-act="sleeves-save">Save the sleeves</button></div></div>
    </section>

    <section class="panel"><h2>Limits</h2>
      <div class="row wrap" style="gap:18px;margin-top:8px;align-items:flex-end">
        <label class="field">ISA allowance per tax year (\u00a3)<input type="number" id="set-isa" value="${s.isa_allowance}" style="width:140px"></label>
        <label class="field">Protection limit per platform (\u00a3)<input type="number" id="set-fscs" value="${s.fscs_limit}" style="width:140px"></label>
        <label class="field">Your name (optional)<input type="text" id="set-name" value="${esc(s.user_name || '')}" style="width:180px"></label>
        <button class="btn primary" data-act="limits-save">Save</button></div>
      <p class="note" style="margin-top:8px">Both limits change only by government decision: \u00a320,000 and \u00a385,000 were current in September 2026.</p>
    </section>

    ${cashPanel(d)}

    <section class="panel"><h2>Where prices come from</h2>
      <p class="lede">Yahoo Finance\u2019s public charts for share prices, and FRED, the St. Louis Federal Reserve\u2019s free data service, for rates, credit spreads, the VIX and exchange rates. Neither needs an account.</p>
      <dl class="kv"><dt>Working</dt><dd>${d.sources.ok} of ${d.sources.total} series</dd>
        <dt>Connection</dt><dd>${d.sources.browser_tls ? 'Browser-style (the most reliable with Yahoo)' : `Plain Python. It works, but Yahoo refuses it more readily than a browser-style connection. The browser-style one didn\u2019t load: ${esc(d.sources.browser_tls_problem || 'reason unknown')}`}</dd></dl>
      ${d.sources.failing.length ? `<details style="margin-top:8px"><summary class="warnline">${plural(d.sources.failing.length, 'series', 'series')} not working</summary><table class="small" style="margin-top:6px"><tbody>${d.sources.failing.map(f => `<tr><td>${esc(f.key.replace(/^(REF|SEC|FX):/, ''))}</td><td class="muted">${esc(f.last_error)}</td><td class="muted nowrap">${f.last_ok ? `last worked ${ago(f.last_ok)}` : 'never worked'}</td></tr>`).join('')}</tbody></table></details>` : ''}
      <div class="row wrap" style="margin-top:12px;align-items:flex-end">
        <label class="field">Stooq key (optional back-up source)<input type="text" id="set-stooq" value="${esc(s.stooq_key || '')}" style="width:240px" placeholder="Not needed"></label>
        <button class="btn" data-act="stooq-save">Save</button>
        <button class="btn" data-act="refresh-all">Fetch everything again</button></div>
    </section>

    <section class="panel"><h2>Sample portfolio</h2>
      <p class="lede">A made-up portfolio on two sample platforms, for trying things out. Remove it before connecting your own platforms, or its made-up holdings will count in your totals.</p>
      ${d.sample ? '<button class="btn danger" data-act="sample-remove">Remove the sample</button>' : '<button class="btn" data-act="sample-load">Load the sample</button>'}
    </section>

    <section class="panel"><h2>Updates and your data</h2>
      <dl class="kv"><dt>Version</dt><dd>${esc(d.version)}</dd>
        <dt>Updates</dt><dd>${up ? updateWords(up) : 'Unknown'}</dd>
        <dt>Your data</dt><dd class="small">${esc(d.data_dir)}</dd>
        <dt>Keys stored</dt><dd class="small">${d.vault === 'os-keychain' ? 'Encrypted, with the key in your computer\u2019s own credential store' : 'Encrypted in the data folder (no credential store was found on this computer)'}</dd></dl>
      <div class="row wrap" style="margin-top:10px">${up && up.status !== 'off' ? '<button class="btn" data-act="upd-check">Check for an update</button>' : ''}<button class="btn" data-act="open-data">Open the data folder</button><button class="btn" data-act="tour">Take the tour</button>
        <label class="row small"><input type="checkbox" data-act="toggle-refresh" ${s.refresh_on_open ? 'checked' : ''}>Refresh when Whiskers opens</label></div>
    </section>
    <p class="note">Whiskers is a personal tool for keeping to your own plan. It is not financial advice. It only ever reads from your platforms and cannot place a trade.</p>
  </div>`;
}

function updateWords(u) {
  if (u.status === 'off') return 'Not set up in this copy.';
  if (u.show_banner) return `Version ${esc(u.latest)} is available.`;
  if (u.last_error) return `The last check didn\u2019t get an answer: ${esc(u.last_error)}`;
  return u.checked_at ? `Up to date, checked ${ago(u.checked_at)}.` : 'Not checked yet.';
}

function platformRow(p) {
  const kind = p.provider === 'trading212' ? 'Trading 212, connected by read-only key' : p.provider === 'freetrade' ? 'Freetrade, from its activity file'
    : p.provider === 'sample' ? 'Sample platform' : 'Holdings typed in by hand';
  let actions = '';
  if (p.provider === 'trading212') {
    actions = `<button class="btn small" data-act="t212-key" data-id="${p.id}">${p.has_key ? 'Replace the key' : 'Connect'}</button>` +
      (p.has_key ? `<button class="btn small ghost" data-act="t212-forget" data-id="${p.id}">Forget the key</button>` : '');
  } else if (p.provider === 'freetrade') {
    actions = `<button class="btn small" data-act="ft-import" data-id="${p.id}">Import an activity file</button>`;
  }
  const cashNote = p.provider === 'trading212' ? 'reported by Trading 212' :
    known(p.cash_estimate) ? `the activity file suggests ${moneyText(p.cash_estimate, 2)}` : 'type what the platform shows';
  return `<div class="grid" style="grid-template-columns:minmax(0,1.3fr) minmax(0,1fr);gap:14px">
    <div><div class="row"><b>${esc(p.name)}</b>${p.flexible ? '<span class="chip">flexible ISA</span>' : ''}</div>
      <div class="small muted">${kind}. ${plural(p.holdings, 'holding')}, ${money(p.total, { dp: 0 })} in all${p.last_sync ? `, updated ${ago(p.last_sync)}` : ''}.</div>
      ${p.last_error ? `<div class="warnline small">${esc(p.last_error)}</div>` : ''}
      <div class="row wrap" style="margin-top:8px">${actions}<button class="btn small ghost" data-act="plat-rename" data-id="${p.id}" data-name="${esc(p.name)}">Rename</button>
        <label class="row small"><input type="checkbox" data-act="plat-flex" data-id="${p.id}" ${p.flexible ? 'checked' : ''}>Flexible ISA</label>
        <button class="btn small ghost danger" data-act="plat-del" data-id="${p.id}" data-name="${esc(p.name)}">Remove</button></div></div>
    <div class="row wrap" style="align-items:flex-end">
      <label class="field">Cash (\u00a3)<input type="number" step="0.01" value="${p.cash ?? ''}" data-cash="${p.id}" style="width:130px" ${p.provider === 'trading212' && p.has_key ? 'disabled' : ''}><span class="help">${cashNote}</span></label>
      ${p.provider !== 'trading212' || !p.has_key ? `<button class="btn small" data-act="cash-save" data-id="${p.id}">Save cash</button>` : ''}
    </div></div>`;
}

async function addPlatform(kind) {
  const names = { trading212: 'Trading 212 ISA', freetrade: 'Freetrade ISA', other: '' };
  let name = names[kind];
  if (kind === 'other') {
    openModal({ title: 'Add a platform', body: `<label class="field">Name<input type="text" id="np-name" placeholder="e.g. Vanguard ISA"></label>
      <label class="row small" style="margin-top:10px"><input type="checkbox" id="np-flex">It\u2019s a flexible ISA</label>`,
      foot: `<button class="btn" data-act="close">Cancel</button><button class="btn primary" data-act="np-save">Add it</button>` });
    ACTS['np-save'] = async b => {
      await busy(b, async () => {
        await api('/api/platforms', { method: 'POST', body: { name: $('#np-name').value, provider: 'other', flexible: $('#np-flex').checked } });
        closeModal(); await refreshBoot(); render();
      });
    };
    return;
  }
  try {
    const r = await api('/api/platforms', { method: 'POST', body: { name, provider: kind } });
    await refreshBoot();
    if (kind === 'trading212') t212Modal(r.id); else ftImport(r.id);
    render();
  } catch (e) { toast(e.message, true); }
}

function t212Modal(id) {
  openModal({ title: 'Connect Trading 212', body: `<div class="stack">
    <p>Whiskers needs a key that can <b>read</b> your account and nothing else.</p>
    <div class="steps">
      <div class="step"><div>On the Trading 212 website or app, switch to your <b>Stocks ISA</b> (each account has its own key), then go to Settings and find <b>API</b>.</div></div>
      <div class="step"><div>Generate a new key. Tick only the permissions that <b>read</b>: account data, portfolio, history and metadata. Leave anything that places orders or changes pies <b>unticked</b>. Whiskers never trades.</div></div>
      <div class="step"><div>Trading 212 shows an <b>API key</b> and a <b>secret</b>. The secret appears only once, so copy both now and paste them here.</div></div>
    </div>
    <label class="field">API key<input type="password" id="t212-key" autocomplete="off" spellcheck="false"></label>
    <label class="field">Secret<input type="password" id="t212-secret" autocomplete="off" spellcheck="false"><span class="help">Older keys came without a secret; leave this blank if yours has none.</span></label>
    <p class="note">The key is stored encrypted on this computer, with the encryption key in your operating system\u2019s own credential store. If a key is ever rejected, Whiskers says whether that is the key itself (401) or a missing read permission (403).</p>
  </div>`, foot: `<button class="btn" data-act="close">Cancel</button><button class="btn primary" data-act="t212-save" data-id="${id}">Test and save the key</button>` });
}
ACTS['t212-key'] = b => t212Modal(+b.dataset.id);
ACTS['t212-save'] = async b => {
  await busy(b, async () => {
    const r = await api(`/api/platforms/${b.dataset.id}/t212`, { method: 'POST', body: { api_key: $('#t212-key').value, api_secret: $('#t212-secret').value } });
    closeModal();
    toast(r.message + ' Fetching holdings now; history follows over the next few minutes.');
    pollRefresh();
    render();
  });
};
ACTS['t212-forget'] = async b => {
  if (!await confirmBox('Forget the Trading 212 key?', 'Holdings already fetched stay until you remove the platform. Delete the key on Trading 212\u2019s own API page too if you no longer need it.', 'Forget the key', true)) return;
  await api(`/api/platforms/${b.dataset.id}/t212`, { method: 'DELETE' }).catch(e => toast(e.message, true));
  render();
};

function ftImport(id) {
  openModal({ title: 'Import Freetrade activity', body: `<div class="stack">
    <p>Freetrade has no connection for apps, so Whiskers reads the activity file Freetrade lets you export.</p>
    <div class="steps">
      <div class="step"><div>In the Freetrade app, open <b>Activity</b> and use its export option to save your full history as a CSV file.</div></div>
      <div class="step"><div>Get the file onto this computer: email it to yourself, or save it to your cloud drive.</div></div>
      <div class="step"><div>Choose it below. Importing the same file again, or a newer one that overlaps, never counts anything twice.</div></div>
    </div>
    <button class="btn primary" data-act="ft-choose" data-id="${id}">Choose the file</button>
    <div id="ft-out"></div></div>`, foot: `<button class="btn" data-act="close">Done</button>` });
}
ACTS['ft-import'] = b => ftImport(+b.dataset.id);
ACTS['ft-choose'] = async b => {
  const f = await pickFile('.csv,text/csv');
  if (!f) return;
  await busy(b, async () => {
    const r = await api(`/api/platforms/${b.dataset.id}/import`, { method: 'POST', body: await f.arrayBuffer(), raw: true });
    const unknown = Object.entries(r.unknown_types || {});
    $('#ft-out').innerHTML = `<div class="panel" style="margin-top:6px"><b>Imported.</b>
      <p class="small">${plural(r.trades, 'new trade')}, ${plural(r.dividends, 'new dividend')}, ${plural(r.cash, 'new deposit or withdrawal', 'new deposits and withdrawals')}, from ${fmtDate(r.first)} to ${fmtDate(r.last)}. ${plural(r.positions, 'holding')} now on this platform.</p>
      ${known(r.cash_estimate) ? `<p class="small">By the file\u2019s arithmetic, cash should be about ${money(r.cash_estimate, { dp: 2 })}. Check it against the app and type the real figure into the platform\u2019s cash box.</p>` : ''}
      ${r.warnings.map(w => `<p class="warnline small">${esc(w)}</p>`).join('')}
      ${unknown.length ? `<p class="note">Left out as not relevant: ${unknown.map(([k, n]) => `${esc(k)} (${n})`).join(', ')}.</p>` : ''}</div>`;
    pollRefresh();
    render();
  });
};

ACTS['cash-save'] = async b => {
  const inp = $(`[data-cash="${b.dataset.id}"]`);
  await busy(b, async () => { await api(`/api/platforms/${b.dataset.id}`, { method: 'PATCH', body: { cash: inp.value === '' ? null : inp.value } }); toast('Cash saved.'); render(); });
};
ACTS['plat-flex'] = async b => { await api(`/api/platforms/${b.dataset.id}`, { method: 'PATCH', body: { flexible: b.checked } }).catch(e => toast(e.message, true)); };
ACTS['plat-rename'] = b => {
  openModal({ title: 'Rename the platform', body: `<label class="field">Name<input type="text" id="pr-name" value="${esc(b.dataset.name)}"></label>`,
    foot: `<button class="btn" data-act="close">Cancel</button><button class="btn primary" data-act="pr-save" data-id="${b.dataset.id}">Rename</button>` });
};
ACTS['pr-save'] = async b => { await busy(b, async () => { await api(`/api/platforms/${b.dataset.id}`, { method: 'PATCH', body: { name: $('#pr-name').value } }); closeModal(); render(); }); };
ACTS['plat-del'] = async b => {
  if (!await confirmBox(`Remove ${b.dataset.name}?`, 'Its holdings, trades, dividends and deposits are removed from Whiskers, and any saved key is forgotten. Nothing on the platform itself changes.', 'Remove the platform', true)) return;
  await api(`/api/platforms/${b.dataset.id}`, { method: 'DELETE' }).catch(e => toast(e.message, true));
  await refreshBoot();
  render();
};

ACTS['sleeves-save'] = async b => {
  await busy(b, async () => {
    for (const tr of $$('[data-sleeve]')) {
      const body = {};
      $$('[data-f]', tr).forEach(inp => {
        const f = inp.dataset.f;
        body[f] = inp.type === 'checkbox' ? inp.checked : inp.value === '' ? null : inp.value;
      });
      if (body.target === null) body.target = 0;
      await api(`/api/sleeves/${tr.dataset.sleeve}`, { method: 'PATCH', body });
    }
    toast('Sleeves saved.');
    render();
  });
};
ACTS['sleeve-add'] = async () => {
  try { await api('/api/sleeves', { method: 'POST', body: { name: `New sleeve ${Date.now() % 1000}`, target: 0 } }); render(); }
  catch (e) { toast(e.message, true); }
};
ACTS['sleeve-del'] = async b => {
  if (!await confirmBox('Remove this sleeve?', 'Holdings in it go back to \u201cnot in a sleeve yet\u201d. Nothing is sold or changed on any platform.', 'Remove the sleeve', true)) return;
  await api(`/api/sleeves/${b.dataset.id}`, { method: 'DELETE', body: {} }).catch(e => toast(e.message, true));
  render();
};
ACTS['plan-export'] = async () => {
  try {
    const res = await api('/api/plan/export');
    const blob = await res.blob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'Whiskers plan.json';
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  } catch (e) { toast(e.message, true); }
};
ACTS['limits-save'] = async b => {
  await busy(b, async () => {
    await api('/api/settings', { method: 'PATCH', body: { isa_allowance: $('#set-isa').value, fscs_limit: $('#set-fscs').value, user_name: $('#set-name').value } });
    toast('Saved.');
    await refreshBoot();
  });
};
ACTS['stooq-save'] = async b => { await busy(b, async () => { await api('/api/settings', { method: 'PATCH', body: { stooq_key: $('#set-stooq').value } }); toast('Saved.'); }); };
ACTS['refresh-all'] = () => { startRefresh(true); toast('Fetching every series again. This takes a minute or two.'); };
ACTS['sample-remove'] = async b => {
  if (!await confirmBox('Remove the sample portfolio?', 'The two sample platforms and everything on them go. Your own platforms are not touched. Sleeves stay, so you can keep or change them.', 'Remove the sample', true)) return;
  await busy(b, async () => { await api('/api/sample/remove', { method: 'POST' }); await refreshBoot(); toast('Sample removed.'); render(); });
};
ACTS['upd-check'] = async b => { await busy(b, async () => { const u = await api('/api/update/check', { method: 'POST' }); toast(updateWords(u).replace(/<[^>]+>/g, '')); checkUpdateBanner(); render(); }); };
ACTS['open-data'] = () => api('/api/open-data-folder', { method: 'POST' }).catch(e => toast(e.message, true));
ACTS['toggle-refresh'] = b => api('/api/settings', { method: 'PATCH', body: { refresh_on_open: b.checked } }).catch(e => toast(e.message, true));

// ============================================================================ start

async function boot() {
  try { S.boot = await api('/api/bootstrap'); }
  catch (e) { $('#boot').innerHTML = `<div class="panel" style="max-width:480px"><h2>Whiskers couldn\u2019t start</h2><p class="lede">${esc(e.message)}</p></div>`; return; }
  applyTheme();
  applyHide();
  buildNav();
  $('#fake-banner').hidden = !S.boot.app.fake_market;
  $('#refresh-btn').addEventListener('click', () => startRefresh(false));
  $('#tour-btn').addEventListener('click', () => startTour());
  // Web links open in your own browser, whichever window Whiskers is running in: inside
  // the app window a plain link would replace Whiskers itself with the web page.
  document.addEventListener('click', ev => {
    const a = ev.target.closest && ev.target.closest('a[href^="http"], a[href^="mailto:"]');
    if (!a) return;
    ev.preventDefault();
    api('/api/open-url', { method: 'POST', body: { url: a.href } }).catch(e => toast(e.message, true));
  });
  $('#theme-btn').addEventListener('click', cycleTheme);
  $('#hide-btn').addEventListener('click', toggleHide);
  $('#modal-x').addEventListener('click', closeModal);
  $('#modal').addEventListener('mousedown', e => { if (e.target.id === 'modal') closeModal(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && !$('#modal').hidden) closeModal(); });
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => { if (applyTheme()) render(); });
  setInterval(() => { if (applyTheme()) render(); }, 5 * 60 * 1000);
  $('#boot').remove();
  $('#app').hidden = false;
  const want = location.hash.slice(1);
  go(VIEWS[want] ? want : 'overview');
  if (!S.boot.settings.toured) setTimeout(() => startTour(), 900);
  pollRefresh();
  checkUpdateBanner();
  setInterval(checkUpdateBanner, 30 * 60 * 1000);
}

boot();


// ============================================================================ the playbook

function playbookPanels(pb, story) {
  if (!pb) return '';
  const lvl = pb.tier.level;
  const groups = [['market', 'Markets in general'], ['ai', 'The AI trade']];
  return `<div class="grid g-main">
    <section class="panel"><div class="spread"><h2>Your signals</h2><span class="chip ${lvl}">${pb.firing} of ${pb.of} firing: ${esc(pb.tier.label)}</span></div>
      <p class="lede">${esc(pb.tier.text)} None of these is a sell signal. They say what kind of fall this is, not whether to stay invested.</p>
      ${story ? `<p class="narrative">${narr(story)}</p>` : ''}
      ${groups.map(([g, t]) => `<h3 style="margin-top:12px">${t}</h3><div class="sig-list">${pb.signals.filter(x => x.group === g).map(signalRow).join('')}</div>`).join('')}
      <p class="note" style="margin-top:10px">${pb.manual_updated ? `The three you fill in were last updated ${fmtDate(pb.manual_updated)}.` : 'The three you fill in are still blank.'} Update them after each earnings season: late January, April, July and October.</p>
    </section>
    <section class="panel"><h2>Your ladder</h2>
      <p class="lede">What to do depends on how far your own holdings have fallen, not on the signals. Measured on today\u2019s holdings at past prices, so money paid in never hides a fall.</p>
      ${ladderBlock(pb.ladder)}
    </section>
  </div>`;
}

function signalRow(x) {
  const word = { '>': 'above', '>=': 'at', '<': 'below', '<=': 'at or below' }[x.op];
  const unit = x.unit === '%' ? '%' : '';
  const val = !known(x.value) ? 'not known yet' : x.unit === 'of 4' ? `${x.value} of 4`
    : `${x.key === 'breadth' && x.value > 0 ? '+' : ''}${(+x.value).toFixed(x.unit === '%' ? 2 : 1)}${unit}`;
  const rule = x.unit === 'of 4' ? `fires at ${x.threshold} or more` : `fires ${word} ${x.threshold}${unit}`;
  const state = x.firing === null ? 'none' : x.firing ? 'amber' : 'green';
  let input = '';
  if (x.kind === 'manual') {
    input = x.choices
      ? `<div class="pill-row" style="margin-top:6px">${x.choices.map(c => `<label class="chip"><input type="checkbox" data-act="sig-tick" data-key="${x.key}" value="${esc(c)}" ${x.ticked.includes(c) ? 'checked' : ''}> ${esc(c)}</label>`).join('')}</div>`
      : `<div class="row" style="margin-top:6px"><input type="number" step="0.1" id="sig-${x.key}" value="${known(x.value) ? x.value : ''}" style="width:110px" aria-label="${esc(x.title)}"><button class="btn small" data-act="sig-save" data-key="${x.key}">Save</button>${x.stale ? '<span class="tiny warnline">Due for updating</span>' : ''}</div>`;
  }
  return `<div class="sig"><div class="spread"><div class="row"><span class="lvl ${state}"></span><b>${esc(x.title)}</b></div>
      <span class="small nowrap">${esc(val)} <span class="muted">(${esc(rule)})</span></span></div>
    <div class="small muted">${esc(x.means)}${x.baseline ? ` Baseline: ${fmtDate(x.baseline)}.` : ''}</div>
    ${x.action ? `<div class="small" style="margin-top:2px">Your action: ${esc(x.action)}</div>` : ''}${input}</div>`;
}

function ladderBlock(l) {
  const rungs = [...l.rungs].reverse().map(r => `<div class="rung ${r.active ? 'on' : ''}">
      <span class="fig">${r.from}%${r.from === 40 ? '+' : ''}</span><span>${esc(r.text)}</span>
      ${r.active ? `<span class="chip ${r.from === 0 ? 'green' : 'amber'}">You are here</span>` : '<span></span>'}</div>`).join('');
  return `${known(l.drop) ? `<div class="fig" style="font-size:2rem;line-height:1.1">${l.drop < 0.5 ? 'At the high' : `${l.drop.toFixed(1)}% down`}</div>
      <div class="small muted">against the high of ${fmtDate(l.high_on)}</div>` : '<p class="muted">Needs price history for your holdings first.</p>'}
    <div class="ladder">${rungs}</div>
    ${known(l.cash) ? `<p class="small">Cash in your plan: ${money(l.cash)}. A third is ${money(l.third)}.</p>` : ''}
    <p class="small" style="margin-top:6px">Never: ${esc(l.never)}</p>`;
}

ACTS['sig-save'] = async b => {
  await api(`/api/signals/${b.dataset.key}`, { method: 'PUT', body: { value: $(`#sig-${b.dataset.key}`).value } });
  toast('Saved.');
  render();
};
ACTS['sig-tick'] = async b => {
  const key = b.dataset.key;
  const ticked = $$(`input[data-act="sig-tick"][data-key="${key}"]`).filter(i => i.checked).map(i => i.value);
  await api(`/api/signals/${key}`, { method: 'PUT', body: { ticked } });
  render();
};

// ============================================================================ cash accounts and cards

function cashPanel(d) {
  const banks = d.platforms.filter(p => p.kind === 'bank');
  const cards = d.platforms.filter(p => p.kind === 'card');
  const bankRow = x => {
    const auto = x.monzo_linked;
    const monzoish = /monzo/i.test(x.name);
    return `<tr><td><b>${esc(x.name)}</b><div class="tiny muted">${x.cash_as_of ? `${auto ? 'From Monzo, ' : 'Updated '}${ago(x.cash_as_of)}` : 'No balance yet'}${x.last_error ? ` <span class="warnline">${esc(x.last_error)}</span>` : ''}</div></td>
      <td class="r">${auto ? `<span class="fig">${money(x.cash)}</span>` : `<input type="number" step="0.01" id="bank-${x.id}" value="${known(x.cash) ? x.cash : ''}" style="width:130px" aria-label="Balance for ${esc(x.name)}">`}</td>
      <td><input type="checkbox" data-act="bank-plan" data-id="${x.id}" ${x.in_plan ? 'checked' : ''} aria-label="Count ${esc(x.name)} in my plan"></td>
      <td class="r nowrap">${auto ? `<button class="btn small ghost" data-act="monzo-forget" data-id="${x.id}">Disconnect</button>`
        : `${monzoish ? `<button class="btn small" data-act="monzo-connect" data-id="${x.id}">Connect automatically</button> ` : ''}<button class="btn small" data-act="bank-save" data-id="${x.id}">Save</button>`}
        <button class="btn small ghost danger" data-act="bank-del" data-id="${x.id}" data-name="${esc(x.name)}">Remove</button></td></tr>`;
  };
  const cardRow = x => `<tr><td><b>${esc(x.name)}</b><div class="tiny muted">${x.cash_as_of ? `Updated ${ago(x.cash_as_of)}` : 'Nothing entered yet'}</div></td>
      <td class="r"><input type="number" step="0.01" min="0" id="card-${x.id}" value="${known(x.cash) ? Math.abs(x.cash) : ''}" style="width:130px" aria-label="Owed on ${esc(x.name)}"></td>
      <td class="r nowrap"><button class="btn small" data-act="card-save" data-id="${x.id}">Save</button>
        <button class="btn small ghost danger" data-act="bank-del" data-id="${x.id}" data-name="${esc(x.name)}">Remove</button></td></tr>`;
  const net = d.platforms.filter(p => p.kind === 'bank' || p.kind === 'card').reduce((a, p) => a + (p.cash || 0), 0);
  return `<section class="panel"><div class="spread"><h2>Cash and cards</h2>
      <div class="row"><button class="btn" data-act="bank-add">Add a cash account</button><button class="btn" data-act="card-add">Add a credit card</button></div></div>
    <p class="lede">Bank and savings accounts such as HSBC or Spring, and credit cards such as Amex or Barclaycard. Type balances in when they change; Monzo can update itself. They sit beside your portfolio, not inside it: cards are taken off your cash, and a cash account counts in your Cash sleeve only if you tick \u201cPart of my plan\u201d.</p>
    ${banks.length ? `<div class="table-wrap"><table><thead><tr><th>Cash account</th><th class="r">Balance (\u00a3)</th><th>Part of my plan</th><th></th></tr></thead><tbody>${banks.map(bankRow).join('')}</tbody></table></div>` : ''}
    ${cards.length ? `<div class="table-wrap" style="margin-top:12px"><table><thead><tr><th>Credit card</th><th class="r">Owed (\u00a3)</th><th></th></tr></thead><tbody>${cards.map(cardRow).join('')}</tbody></table></div>` : ''}
    ${banks.length || cards.length ? `<p class="small" style="margin-top:10px">Cash less cards: <b class="fig">${money(net)}</b></p>` : '<p class="muted">None yet.</p>'}
    <p class="note" style="margin-top:8px">The FSCS protects bank deposits up to \u00a3120,000 per person per banking licence. Brands that share a licence share one limit (Spring is part of Paragon Bank, for one).</p>
  </section>`;
}

ACTS['bank-add'] = () => openModal({
  title: 'Add a cash account',
  body: `<div class="stack">
    <label class="field">Name<input type="text" id="bank-name" placeholder="For example, HSBC"></label>
    <label class="field">Balance (\u00a3)<input type="number" step="0.01" id="bank-bal"></label>
    <label class="row small"><input type="checkbox" id="bank-inplan"> Part of my plan: count this balance in my Cash sleeve</label></div>`,
  foot: '<button class="btn primary" data-act="bank-create">Add the account</button>',
});
ACTS['bank-create'] = async () => {
  const name = $('#bank-name').value.trim();
  if (!name) { toast('Give the account a name.', true); return; }
  await api('/api/platforms', { method: 'POST', body: { name, provider: 'bank', cash: $('#bank-bal').value, in_plan: $('#bank-inplan').checked } });
  closeModal();
  toast(`${name} added.`);
  render();
};
ACTS['card-add'] = () => openModal({
  title: 'Add a credit card',
  body: `<div class="stack">
    <label class="field">Name<input type="text" id="card-name" placeholder="For example, Amex"></label>
    <label class="field">Owed now (\u00a3)<input type="number" step="0.01" min="0" id="card-owed"><span class="help">The balance on your latest statement or in the card's app. Type it again when it changes.</span></label></div>`,
  foot: '<button class="btn primary" data-act="card-create">Add the card</button>',
});
ACTS['card-create'] = async () => {
  const name = $('#card-name').value.trim();
  if (!name) { toast('Give the card a name.', true); return; }
  await api('/api/platforms', { method: 'POST', body: { name, provider: 'card', owed: $('#card-owed').value } });
  closeModal();
  toast(`${name} added.`);
  render();
};
ACTS['bank-save'] = async b => {
  await api(`/api/platforms/${b.dataset.id}`, { method: 'PATCH', body: { cash: $(`#bank-${b.dataset.id}`).value } });
  toast('Balance saved.');
  render();
};
ACTS['card-save'] = async b => {
  await api(`/api/platforms/${b.dataset.id}`, { method: 'PATCH', body: { owed: $(`#card-${b.dataset.id}`).value } });
  toast('Saved.');
  render();
};
ACTS['bank-plan'] = async b => {
  await api(`/api/platforms/${b.dataset.id}`, { method: 'PATCH', body: { in_plan: b.checked } });
  render();
};
ACTS['bank-del'] = async b => {
  if (!await confirmBox(`Remove ${b.dataset.name}?`, 'Its balance comes off every total. Nothing else changes.', 'Remove', true)) return;
  await api(`/api/platforms/${b.dataset.id}`, { method: 'DELETE' });
  toast('Removed.');
  render();
};

// Monzo is the one account here with an API a person can use for their own money.
ACTS['monzo-connect'] = b => openModal({
  title: 'Connect Monzo automatically',
  body: `<div class="stack">
    <p class="small">Whiskers reads your balance (current account plus pots) and nothing else. It cannot move money.</p>
    <ol class="small" style="margin:0;padding-left:20px;display:grid;gap:6px">
      <li>On a computer, go to <a href="https://developers.monzo.com">developers.monzo.com</a> and sign in with the email on your Monzo account. Approve the sign-in in the Monzo app.</li>
      <li>Choose <b>Clients</b>, then <b>New OAuth Client</b>. Name it Whiskers.</li>
      <li>Redirect URL: <code>http://127.0.0.1:${location.port}/oauth/monzo</code> exactly.</li>
      <li>Confidentiality: <b>Confidential</b>, so Whiskers can keep the link going by itself.</li>
      <li>Open the new client and copy its Client ID and Client secret into the boxes below.</li>
    </ol>
    <label class="field">Client ID<input type="text" id="mz-id" placeholder="oauth2client_..."></label>
    <label class="field">Client secret<input type="password" id="mz-secret"></label>
    <p class="small">Next, Monzo emails you a sign-in link. Open it on this computer, then approve the request in the Monzo app, then press Refresh.</p></div>`,
  foot: `<button class="btn primary" data-act="monzo-go" data-id="${b.dataset.id}">Save and go to Monzo</button>`,
});
ACTS['monzo-go'] = async b => {
  const out = await api(`/api/platforms/${b.dataset.id}/monzo`, { method: 'POST', body: { client_id: $('#mz-id').value, client_secret: $('#mz-secret').value } });
  await api('/api/open-url', { method: 'POST', body: { url: out.url } });
  closeModal();
  toast('Monzo\u2019s sign-in page is open in your browser. Follow its email link, approve in the Monzo app, then press Refresh.');
};
ACTS['monzo-forget'] = async b => {
  if (!await confirmBox('Disconnect Monzo?', 'Whiskers forgets its Monzo key. The last balance stays until you type a new one.', 'Disconnect')) return;
  await api(`/api/platforms/${b.dataset.id}/monzo`, { method: 'DELETE' });
  render();
};

// ============================================================================ holdings against targets

function targetsPanel(rows) {
  if (!rows || !rows.length) return '';
  const out = rows.filter(r => r.status === 'out').length;
  const absent = rows.filter(r => r.status === 'not held').length;
  return `<section class="panel"><h2>Each holding against its own target</h2>
    <p class="lede">A holding may sit within a quarter of its target either side: a 4% target runs from 3% to 5%. ${out ? `${plural(out, 'holding')} outside ${out === 1 ? 'its' : 'their'} band` : 'Every holding is inside its band'}${absent ? `, ${absent} not held` : ''}.</p>
    <div class="table-wrap"><table><thead><tr><th>Holding</th><th class="r">Target</th><th class="r">Now</th><th style="width:36%">Band</th><th></th></tr></thead><tbody>
    ${rows.map(r => {
      const top = Math.max(r.high * 1.6, (r.actual || 0) * 1.08, 0.5);
      const x = v => `${Math.max(0, Math.min(100, v / top * 100)).toFixed(1)}%`;
      const col = r.status === 'ok' ? 'var(--green)' : r.status === 'out' ? 'var(--amber)' : 'var(--grey)';
      const held = r.status !== 'not held' && known(r.actual);
      const word = { ok: 'In band', out: held && r.actual > r.high ? 'Over' : 'Under', 'not held': 'Not held', none: 'No value' }[r.status];
      return `<tr><td><b>${esc(r.key)}</b>${r.name !== r.key ? `<div class="tiny muted">${esc(r.name)}</div>` : ''}</td>
        <td class="r">${pts(r.target, 2)}</td><td class="r">${held ? pts(r.actual, 2) : '\u2014'}</td>
        <td><div class="band-track" title="Band ${pts(r.low, 2)} to ${pts(r.high, 2)}"><div class="axisline"></div>
          <div class="zone" style="left:${x(r.low)};width:calc(${x(r.high)} - ${x(r.low)})"></div>
          <div class="tgt" style="left:${x(r.target)}"></div>${held ? `<div class="dot" style="left:${x(r.actual)};background:${col}"></div>` : ''}</div></td>
        <td><span class="chip ${r.status === 'ok' ? 'green' : r.status === 'out' ? 'amber' : ''}">${word}</span></td></tr>`;
    }).join('')}
    </tbody></table></div></section>`;
}


// ============================================================================ tickers people recognise

// A broker's own code can be stale: Trading 212 still lists Ouster as CLA, its old SPAC
// ticker. Where the price symbol says something different, that is the one shown, with
// the broker's code alongside so the two can still be matched up.
const normTicker = x => String(x || '').toUpperCase().replace(/\./g, '-').replace(/-$/, '');
function tickerText(r) {
  const ms = String(r.market_symbol || '').replace(/\.[A-Z]{1,2}$/, '');
  return !ms || normTicker(ms) === normTicker(r.symbol) ? String(r.symbol || '') : `${ms}, listed as ${r.symbol}`;
}
function tickerOf(r) {
  const ms = String(r.market_symbol || '').replace(/\.[A-Z]{1,2}$/, '');
  if (!ms || normTicker(ms) === normTicker(r.symbol)) return esc(r.symbol);
  return `${esc(ms)} <span class="muted">(listed as ${esc(r.symbol)})</span>`;
}

ACTS.gone = async b => {
  if (!await confirmBox('No longer held here?', 'Its share count on this platform goes to zero. The correction is kept when you import the next Freetrade file.', 'Set to zero')) return;
  await api('/api/positions/adjust', { method: 'POST', body: { platform_id: +b.dataset.pid, instrument_id: +b.dataset.iid, quantity: 0 } });
  closeModal();
  toast('Set to zero.');
  render();
};


// ============================================================================ the tour

// A minute's walk round the app for someone opening it for the first time. It starts by
// itself once, and again whenever the Tour button or Settings asks. A step whose part of
// the screen isn't there yet (a brand-new copy has no holdings) is shown in the middle.
const TOUR = [
  { title: 'Welcome to Whiskers', text: 'Your investments, the limits you set for them, and what markets are doing, in one place. It only ever reads from your platforms: it cannot buy, sell or move money. This tour takes about a minute.', sample: true },
  { title: 'Seven screens', target: '#nav', text: 'Overview for the headlines, Holdings for each investment, Allocation for your plan, Market watch for warning lights, Markets for the indices behind them, Activity for money in and out, and Settings to connect everything.' },
  { title: 'Your totals', view: 'overview', target: '.figures', text: 'What everything is worth, what you paid, cash waiting to be invested and dividends. A figure nobody can price is left out and flagged, never counted as zero.' },
  { title: 'Things to look at', view: 'overview', target: '.alerts', text: 'Anything past a limit you set, worst first: red to act on, amber to watch, blue for information. Each one says how long it has been like that, and clicking it takes you to the screen that explains it.' },
  { title: 'AI watch and the big picture', view: 'overview', target: '.monitor', text: 'The AI trade at a glance, then three short paragraphs: the AI trade, markets and the economy, and what it all means for your own portfolio.' },
  { title: 'Every holding', view: 'holdings', target: '.table-wrap', text: 'Grouped into your sleeves, with a year\u2019s price line for each. Click a holding for its chart, its details, and to correct anything the platform got wrong.' },
  { title: 'Your plan against reality', view: 'allocation', target: '.bands', text: 'Each sleeve against its target. The tick is the target, the dot is where you are: green is fine, amber is drifting, red is outside its band. \u201cPut new money to work\u201d shows where a contribution would do most good.' },
  { title: 'Market watch', view: 'ai', target: '.monitor', text: 'Warning lights for markets in general, the economy, and the AI trade, each judged on a week\u2019s readings rather than one day. They describe what has already happened; none of them can predict what happens next.' },
  { title: 'Markets', view: 'markets', target: 'p.narrative', text: 'The indices, rates and commodities behind your holdings, each section with a short summary of what it is saying.' },
  { title: 'Setting up', view: 'settings', target: '.panel', text: 'Connect Trading 212 with a read-only key, import Freetrade\u2019s activity file, add bank accounts and cards, and load or build your plan. Nothing leaves your computer.' },
  { title: 'Keeping it up to date', target: '#refresh-btn', text: 'Refresh fetches the latest prices and updates any connected accounts. Whiskers also does this each time it opens.' },
  { title: 'Hide amounts', target: '#hide-btn', text: 'Blurs every pound figure, for when someone can see your screen. Percentages stay visible.' },
  { title: 'That\u2019s it', text: 'The Tour button in the sidebar, and Settings, bring this back any time. Nothing here is financial advice: Whiskers measures your portfolio against your own plan.' },
];
let tourAt = -1;

async function startTour(at = 0) {
  tourAt = at;
  if (!$('#tour')) {
    document.body.insertAdjacentHTML('beforeend', '<div id="tour" role="dialog" aria-modal="true" aria-labelledby="tour-title"><div class="tour-hole"></div><div class="tour-card"></div></div>');
    document.addEventListener('keydown', ev => {
      if (tourAt < 0) return;
      if (ev.key === 'Escape') endTour();
      if (ev.key === 'ArrowRight') tourStep(1);
      if (ev.key === 'ArrowLeft') tourStep(-1);
    });
    window.addEventListener('resize', () => { if (tourAt >= 0) showTour(); });
    // A click on the darkened page, outside the card, does nothing rather than leaving
    // the tour half-open; the card's close button and Esc always end it.
  }
  $('#tour').hidden = false;
  await showTour();
}

async function tourStep(by) {
  const next = tourAt + by;
  if (next < 0) return;
  if (next >= TOUR.length) { endTour(); return; }
  tourAt = next;
  await showTour();
}

// Waits for a screen change to finish drawing: until then the old screen's parts are
// still on the page, and a step could otherwise point at something about to vanish.
function afterRender(ms = 4000) {
  return new Promise(resolve => {
    const done = () => { document.removeEventListener('whiskers:rendered', done); clearTimeout(t); resolve(); };
    const t = setTimeout(done, ms);
    document.addEventListener('whiskers:rendered', done);
  });
}

async function showTour() {
  const st = TOUR[tourAt];
  if (st.view && S.view !== st.view) {
    const drawn = afterRender();
    go(st.view);
    await drawn;
  }
  let el = null;
  for (let i = 0; st.target && i < 15 && !el; i++) {
    const found = document.querySelector(st.target);
    if (found && found.offsetParent !== null && found.getBoundingClientRect().height > 0) el = found;
    else await new Promise(r => setTimeout(r, 120));
  }
  const hole = $('#tour .tour-hole'), card = $('#tour .tour-card');
  const empty = !S.boot || !S.boot.platforms;
  card.innerHTML = `<div class="spread"><div class="tiny muted">${tourAt + 1} of ${TOUR.length}</div>
      <button class="btn ghost small" data-tour="end" aria-label="Close the tour" title="Close the tour (Esc)">\u2715</button></div>
    <h3 id="tour-title" style="margin:2px 0 6px">${esc(st.title)}</h3><p class="small">${esc(st.text)}</p>
    ${st.sample && empty ? '<p class="small" style="margin-top:8px">Nothing is set up yet, so the screens are empty. The sample portfolio fills them with made-up holdings, and comes out again in one click.</p>' : ''}
    <div class="row" style="margin-top:12px;justify-content:space-between">
      <button class="btn ghost small" data-tour="end">Skip the tour</button>
      <div class="row">${st.sample && empty ? '<button class="btn small" data-tour="sample">Use the sample</button>' : ''}${tourAt ? '<button class="btn small" data-tour="back">Back</button>' : ''}
      <button class="btn primary small" data-tour="next">${tourAt === TOUR.length - 1 ? 'Finish' : 'Next'}</button></div></div>`;
  card.querySelectorAll('[data-tour]').forEach(b => b.addEventListener('click', async () => {
    const act = b.dataset.tour;
    if (act === 'end') endTour();
    else if (act === 'back') tourStep(-1);
    else if (act === 'next') tourStep(1);
    else if (act === 'sample') {
      b.disabled = true;
      await api('/api/sample/load', { method: 'POST', body: {} });
      S.boot = await api('/api/bootstrap');
      render();
      tourStep(1);
    }
  }));
  placeTour(el, hole, card);
  card.querySelector('[data-tour="next"]').focus();
}

// The card always lands fully on screen. A tall target (the Holdings table runs to
// several screens) is scrolled so its top shows, and only its visible part is lit: the
// first version centred such a table, which put both the lit area and the card above
// the top of the window, leaving the app greyed out with no way on or out.
function placeTour(el, hole, card) {
  const pad = 8, margin = 12;
  const cw = Math.min(380, innerWidth - 2 * margin);
  card.style.width = `${cw}px`;
  card.style.transform = 'none';
  const ch = card.offsetHeight;
  if (!el) {
    hole.style.display = 'none';
    $('#tour').classList.add('dim');
    Object.assign(card.style, { left: `${(innerWidth - cw) / 2}px`, top: `${Math.max(margin, (innerHeight - ch) / 2)}px` });
    return;
  }
  $('#tour').classList.remove('dim');
  const r0 = el.getBoundingClientRect();
  if (r0.top < margin || r0.top > innerHeight * 0.45) {
    window.scrollBy({ top: r0.top - Math.min(120, innerHeight * 0.15), behavior: 'instant' });
  }
  const r = el.getBoundingClientRect();
  const top = Math.max(r.top, margin);
  const bottom = Math.max(top + 40, Math.min(r.bottom, innerHeight - ch - 3 * margin, innerHeight * 0.62));
  Object.assign(hole.style, { display: 'block', left: `${Math.max(0, r.left - pad)}px`, top: `${top - pad}px`,
                              width: `${Math.min(r.width + 2 * pad, innerWidth)}px`, height: `${bottom - top + 2 * pad}px` });
  let y = bottom + pad + margin;                             // below the lit area, if it fits
  if (y + ch > innerHeight - margin) y = top - pad - margin - ch;   // otherwise above it
  y = Math.min(Math.max(margin, y), innerHeight - ch - margin);     // and never off screen
  const x = Math.min(Math.max(margin, r.left), innerWidth - cw - margin);
  Object.assign(card.style, { left: `${x}px`, top: `${y}px` });
}

function endTour() {
  tourAt = -1;
  if ($('#tour')) $('#tour').hidden = true;
  if (S.boot && !S.boot.settings.toured) {
    S.boot.settings.toured = true;
    api('/api/settings', { method: 'PATCH', body: { toured: true } }).catch(() => {});
  }
}

ACTS.tour = () => startTour();


// ============================================================================ plan builder

// Ten questions, a draft plan, and why it came out that way. Nothing is saved until
// "Use this plan": the draft comes back from the server and is only imported then.
ACTS['plan-wizard'] = async () => {
  if (!S.wizQ) S.wizQ = (await api('/api/plan/questions')).questions;
  const a = S.wizA || {};
  openModal({
    title: 'Build a plan from questions', wide: true,
    body: `<p class="small">About two minutes. You\u2019ll see the plan, and why, before anything is saved.</p>` +
      S.wizQ.map((q, i) => `<fieldset class="wiz"><legend>${i + 1}. ${esc(q.text)}</legend>${q.options.map(([v, l]) =>
        `<label class="wiz-opt"><input type="${q.kind === 'many' ? 'checkbox' : 'radio'}" name="wiz-${q.id}" value="${esc(v)}" ${(q.kind === 'many' ? (a[q.id] || []).includes(v) : a[q.id] === v) ? 'checked' : ''}> ${esc(l)}</label>`).join('')}</fieldset>`).join(''),
    foot: '<button class="btn primary" data-act="plan-wizard-build">Show my plan</button>',
  });
};
ACTS['plan-wizard-build'] = async () => {
  const a = {};
  for (const q of S.wizQ) {
    const picked = $$(`input[name="wiz-${q.id}"]:checked`).map(i => i.value);
    a[q.id] = q.kind === 'many' ? picked : picked[0];
  }
  S.wizA = a;
  const gap = S.wizQ.findIndex(q => q.kind === 'one' && !a[q.id]);
  if (gap >= 0) { toast(`Please answer question ${gap + 1}.`, true); return; }
  const out = await api('/api/plan/build', { method: 'POST', body: { answers: a } });
  S.wizPlan = out.plan;
  const rows = out.plan.sleeves.map(x => `<tr><td>${esc(x.name)}</td><td class="r">${pts(x.target, x.target % 1 ? 1 : 0)}</td></tr>`).join('');
  openModal({
    title: 'Your starting plan', wide: true,
    body: `<div class="grid g2"><div><table><thead><tr><th>Sleeve</th><th class="r">Target</th></tr></thead><tbody>${rows}</tbody></table>
      ${out.plan.rules.map(r => `<p class="small" style="margin-top:10px">Rule: ${esc(r.note)}</p>`).join('')}
      ${out.plan.platforms.length ? `<p class="small" style="margin-top:6px">Platforms: ${out.plan.platforms.map(x => esc(x.name)).join(', ')}, each kept under \u00a3${Number(out.plan.platforms[0].limit).toLocaleString('en-GB')}.</p>` : ''}</div>
      <div><h3>Why</h3><ul class="small" style="padding-left:18px;display:grid;gap:6px">${out.why.map(w => `<li>${esc(w)}</li>`).join('')}</ul>
        ${out.plan.plans && out.plan.plans.crash ? `<h3 style="margin-top:12px">Your plan for a fall, to start from</h3><p class="small">${esc(out.plan.plans.crash)}</p>` : ''}
        <h3 style="margin-top:12px">Based on</h3><ul class="tiny" style="padding-left:18px;display:grid;gap:4px">${(out.sources || []).map(([t, u]) => `<li><a href="${esc(u)}">${esc(t)}</a></li>`).join('')}</ul></div></div>
      <p class="note" style="margin-top:12px">Using it replaces your current sleeves and targets. Holdings already sorted into sleeves with other names go back to \u201cnot in a sleeve yet\u201d.</p>`,
    foot: '<button class="btn" data-act="plan-wizard">Change my answers</button><button class="btn primary" data-act="plan-wizard-use">Use this plan</button>',
  });
};
ACTS['plan-wizard-use'] = async () => {
  const out = await api('/api/plan/import', { method: 'POST', body: S.wizPlan });
  closeModal();
  toast(`Plan set: ${plural(out.report.sleeves, 'sleeve')}. Sort your holdings into them on the Allocation screen.`);
  S.boot = await api('/api/bootstrap');
  render();
};
