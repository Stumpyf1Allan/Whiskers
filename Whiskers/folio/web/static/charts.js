/* Whiskers charts. Hand-drawn SVG: no library, no network, nothing to go stale.

   Line and bar charts are placed as empty boxes and drawn once they are on the page,
   at their real pixel width, so text stays crisp and a narrow card gets a chart that
   fits rather than a shrunken wide one. They redraw when their box changes size.

   Tooltips are HTML, not SVG <title>: the browser draws a <title> itself and nothing
   can blur it, so with "Hide amounts" on it would read the figure out. Amounts in a
   tooltip carry the `pv` class like every other private figure. */
'use strict';

const Charts = (() => {
  const reg = new Map();
  let seq = 0;
  const ro = new ResizeObserver(entries => {
    for (const e of entries) {
      const w = Math.round(e.contentRect.width);
      if (w && e.target._w !== w) draw(e.target);
    }
  });

  // SVG presentation attributes do not resolve CSS variables in every engine (Safari's
  // WebKit is what a Mac window uses), so a colour given as var(--x) is looked up and
  // written in literally. Charts are redrawn when the theme changes.
  const cv = c => {
    if (typeof c !== 'string' || !c.startsWith('var(')) return c;
    const v = getComputedStyle(document.documentElement).getPropertyValue(c.slice(4, -1).trim()).trim();
    return v || c;
  };

  const esc = s => String(s ?? '').replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  function place(kind, cfg, height) {
    const id = 'c' + (++seq);
    reg.set(id, { kind, cfg });
    return `<div class="chart" data-cid="${id}" style="height:${height}px"></div>`;
  }

  function mount(root = document) {
    for (const id of [...reg.keys()]) {
      if (!document.querySelector(`[data-cid="${id}"]`) && !root.querySelector(`[data-cid="${id}"]`)) reg.delete(id);
    }
    root.querySelectorAll('.chart[data-cid]:not([data-mounted])').forEach(el => {
      el.dataset.mounted = '1';
      draw(el);
      ro.observe(el);
    });
  }

  function draw(el) {
    const item = reg.get(el.dataset.cid);
    if (!item || !el.isConnected) return;
    const w = Math.max(140, Math.round(el.clientWidth));
    el._w = w;
    (item.kind === 'line' ? drawLine : drawBars)(el, item.cfg, w, el.clientHeight || 200);
  }

  // ---------------------------------------------------------------- scales
  function niceTicks(lo, hi, n) {
    const span = hi - lo || 1;
    const raw = span / Math.max(1, n);
    const mag = 10 ** Math.floor(Math.log10(raw));
    const step = [1, 2, 2.5, 5, 10].map(k => k * mag).find(s => s >= raw) || raw;
    const out = [];
    for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) out.push(+v.toFixed(10));
    return out.length ? out : [lo, hi];
  }
  const DAY = 864e5;
  const STEPS = [7, 14, 30, 61, 91, 182, 365, 730, 1461].map(d => d * DAY);
  const stepFor = (span, n) => STEPS.find(s => span / s <= n) || STEPS.at(-1);
  function timeTicks(t0, t1, n) {
    const step = stepFor(t1 - t0, n);
    const out = [];
    const d = new Date(t0);
    if (step >= 365 * DAY) { d.setUTCMonth(0, 1); }
    else if (step >= 30 * DAY) { d.setUTCDate(1); }
    d.setUTCHours(12, 0, 0, 0);
    let t = d.getTime();
    while (t < t0) t = advance(t, step);
    while (t <= t1) { out.push(t); t = advance(t, step); }
    return out;
  }
  function advance(t, step) {
    const d = new Date(t);
    if (step >= 365 * DAY) d.setUTCFullYear(d.getUTCFullYear() + Math.round(step / (365 * DAY)));
    else if (step >= 30 * DAY) d.setUTCMonth(d.getUTCMonth() + Math.round(step / (30.4 * DAY)));
    else d.setTime(t + step);
    return d.getTime();
  }
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  // Labelled by the spacing of the ticks, not the span of the chart: half-yearly ticks
  // labelled with the year alone read "2022 2022 2023 2023".
  function tickLabel(t, step) {
    const d = new Date(t);
    if (step >= 365 * DAY) return String(d.getUTCFullYear());
    if (step >= 30 * DAY) return `${MONTHS[d.getUTCMonth()]} ${String(d.getUTCFullYear()).slice(2)}`;
    return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`;
  }
  function longDate(t) {
    const d = new Date(t);
    return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
  }
  function nearest(arr, t) {
    let lo = 0, hi = arr.length - 1;
    while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (arr[mid] < t) lo = mid; else hi = mid; }
    return Math.abs(arr[lo] - t) <= Math.abs(arr[hi] - t) ? lo : hi;
  }
  function compact(v) {
    const a = Math.abs(v);
    if (a >= 1e6) return (v / 1e6).toFixed(a >= 1e7 ? 0 : 1) + 'm';
    if (a >= 1e4) return (v / 1e3).toFixed(0) + 'k';
    if (a >= 1e3) return (v / 1e3).toFixed(1) + 'k';
    if (a >= 100) return v.toFixed(0);
    if (a >= 10) return v.toFixed(1);
    return v.toFixed(2);
  }
  const parseT = s => Date.parse(String(s).slice(0, 10) + 'T12:00:00Z');

  // ---------------------------------------------------------------- line
  function drawLine(el, cfg, W, H) {
    const series = (cfg.series || []).filter(s => s.points && s.points.length > 1);
    if (!series.length) {
      el.innerHTML = `<div class="muted small" style="padding:24px 4px">${esc(cfg.empty || 'No data yet.')}</div>`;
      return;
    }
    for (const s of series) {
      s._t = s.points.map(p => parseT(p[0]));
      s._v = s.points.map(p => +p[1]);
    }
    const pad = { l: cfg.yAxis === false ? 6 : 58, r: 14, t: 10, b: 24 };
    let t0 = Math.min(...series.map(s => s._t[0]));
    let t1 = Math.max(...series.map(s => s._t.at(-1)));
    if (t1 === t0) t1 = t0 + DAY;
    let lo = Infinity, hi = -Infinity;
    for (const s of series) for (const v of s._v) { if (v < lo) lo = v; if (v > hi) hi = v; }
    for (const h of cfg.hlines || []) { lo = Math.min(lo, h.v); hi = Math.max(hi, h.v); }
    if (cfg.zero) { lo = Math.min(lo, 0); hi = Math.max(hi, 0); }
    const span = hi - lo || Math.abs(hi) * 0.1 || 1;
    lo -= span * 0.06; hi += span * 0.06;
    if (cfg.zero && lo < 0 && Math.min(...series.flatMap(s => s._v)) >= 0) lo = 0;
    const ticks = niceTicks(lo, hi, Math.max(4, Math.round(H / 55)));
    const x = t => pad.l + (t - t0) / (t1 - t0) * (W - pad.l - pad.r);
    const y = v => pad.t + (1 - (v - lo) / (hi - lo)) * (H - pad.t - pad.b);
    const yfmt = cfg.yfmt || compact;
    let svg = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(cfg.label || 'Chart')}">`;
    for (const b of cfg.xbands || []) {
      const a = x(Math.max(t0, parseT(b.from))), z = x(Math.min(t1, parseT(b.to)));
      if (z > a) svg += `<rect x="${a}" y="${pad.t}" width="${z - a}" height="${H - pad.t - pad.b}" fill="${cv(b.color)}" opacity="${b.opacity ?? .12}"/>`;
    }
    svg += '<g class="axis">';
    for (const v of ticks) {
      if (v < lo || v > hi) continue;
      svg += `<line x1="${pad.l}" x2="${W - pad.r}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}"/>`;
      if (cfg.yAxis !== false) {
        svg += `<text x="${pad.l - 8}" y="${(y(v) + 4).toFixed(1)}" text-anchor="end"${cfg.money ? ' class="ymoney"' : ''}>${esc(yfmt(v))}</text>`;
      }
    }
    const nx = Math.max(2, Math.floor((W - pad.l - pad.r) / 88));
    const step = stepFor(t1 - t0, nx);
    for (const t of timeTicks(t0, t1, nx)) {
      svg += `<text x="${x(t).toFixed(1)}" y="${H - 6}" text-anchor="middle">${tickLabel(t, step)}</text>`;
    }
    svg += '</g>';
    for (const h of cfg.hlines || []) {
      svg += `<line x1="${pad.l}" x2="${W - pad.r}" y1="${y(h.v)}" y2="${y(h.v)}" stroke="${cv(h.color) || 'currentColor'}" stroke-dasharray="${h.dash || '4 4'}" opacity="${h.opacity ?? .8}"/>`;
      if (h.label) svg += `<text x="${W - pad.r - 4}" y="${y(h.v) - 5}" text-anchor="end" font-size="11" fill="${cv(h.color) || 'currentColor'}">${esc(h.label)}</text>`;
    }
    for (const s of series) {
      const d = s._t.map((t, i) => `${i ? 'L' : 'M'}${x(t).toFixed(1)},${y(s._v[i]).toFixed(1)}`).join('');
      if (s.area) {
        const base = y(Math.max(lo, Math.min(hi, s.areaBase ?? lo)));
        svg += `<path d="${d}L${x(s._t.at(-1)).toFixed(1)},${base}L${x(s._t[0]).toFixed(1)},${base}Z" fill="${cv(s.color)}" opacity="${s.areaOpacity ?? .1}"/>`;
      }
      svg += `<path d="${d}" fill="none" stroke="${cv(s.color)}" stroke-width="${s.width || 2}"${s.dash ? ` stroke-dasharray="${s.dash}"` : ''} stroke-linejoin="round" stroke-linecap="round"${s.opacity ? ` opacity="${s.opacity}"` : ''}/>`;
    }
    const main = series[0];
    for (const m of cfg.markers || []) {
      const t = parseT(m.date);
      if (t < t0 || t > t1) continue;
      const v = m.v ?? main._v[nearest(main._t, t)];
      const cx = x(t), cy = y(v);
      const c = cv(m.color) || 'currentColor';
      svg += m.shape === 'down'
        ? `<path d="M${cx - 5},${cy - 9}h10l-5,7z" fill="${c}"/>`
        : m.shape === 'up' ? `<path d="M${cx - 5},${cy + 9}h10l-5,-7z" fill="${c}"/>`
        : `<circle cx="${cx}" cy="${cy}" r="3.5" fill="${c}"/>`;
    }
    svg += `<g class="cursor" style="display:none"><line y1="${pad.t}" y2="${H - pad.b}" stroke="currentColor" opacity=".3"/>` +
           series.map(s => `<circle r="3.5" fill="${cv(s.color)}" stroke="${cv('var(--panel)')}" stroke-width="1.5"/>`).join('') + '</g>';
    svg += `<rect class="hit" x="${pad.l}" y="0" width="${W - pad.l - pad.r}" height="${H}" fill="transparent"/></svg><div class="tip" hidden></div>`;
    el.innerHTML = svg;

    const hit = el.querySelector('.hit'), cur = el.querySelector('.cursor'), tip = el.querySelector('.tip');
    const line = cur.querySelector('line'), dots = cur.querySelectorAll('circle');
    const markerDays = new Map((cfg.markers || []).map(m => [String(m.date).slice(0, 10), m.label || '']));
    const fmt = cfg.fmt || (v => compact(v));
    const show = px => {
      const t = t0 + (px - pad.l) / (W - pad.l - pad.r) * (t1 - t0);
      const i = nearest(main._t, t), tt = main._t[i];
      cur.style.display = '';
      line.setAttribute('x1', x(tt)); line.setAttribute('x2', x(tt));
      let rows = '';
      series.forEach((s, j) => {
        const k = nearest(s._t, tt);
        dots[j].setAttribute('cx', x(s._t[k])); dots[j].setAttribute('cy', y(s._v[k]));
        if (s.noTip) return;
        const val = (s.fmt || fmt)(s._v[k], s);
        rows += `<div><i style="display:inline-block;width:8px;height:8px;border-radius:2px;background:${cv(s.color)};margin-right:6px"></i>${esc(s.name || '')} <b${cfg.money && !s.notMoney ? ' class="pv"' : ''}>${esc(val)}</b></div>`;
      });
      const mk = markerDays.get(main.points[i][0].slice(0, 10));
      tip.innerHTML = `<div class="muted">${longDate(tt)}</div>${rows}${mk ? `<div>${esc(mk)}</div>` : ''}`;
      tip.hidden = false;
      const left = x(tt) + 14 + tip.offsetWidth > W ? x(tt) - tip.offsetWidth - 14 : x(tt) + 14;
      tip.style.left = `${Math.max(0, left)}px`;
      tip.style.top = `${pad.t}px`;
    };
    hit.addEventListener('mousemove', ev => show(ev.clientX - el.getBoundingClientRect().left));
    hit.addEventListener('mouseleave', () => { cur.style.display = 'none'; tip.hidden = true; });
  }

  // ---------------------------------------------------------------- bars
  function drawBars(el, cfg, W, H) {
    const items = cfg.items || [];
    if (!items.length) { el.innerHTML = `<div class="muted small" style="padding:24px 4px">${esc(cfg.empty || 'Nothing yet.')}</div>`; return; }
    const pad = { l: 52, r: 10, t: 10, b: 26 };
    let hi = Math.max(0, ...items.map(i => i.value), ...(cfg.hlines || []).map(h => h.v));
    hi = hi || 1;
    const ticks = niceTicks(0, hi * 1.08, Math.max(3, Math.round(H / 58)));
    const top = Math.max(ticks.at(-1), hi);
    const iw = (W - pad.l - pad.r) / items.length;
    const bw = Math.max(2, Math.min(46, iw * 0.68));
    const y = v => pad.t + (1 - v / top) * (H - pad.t - pad.b);
    const every = Math.max(1, Math.ceil(items.length / Math.max(1, Math.floor((W - pad.l) / 56))));
    const yfmt = cfg.yfmt || compact;
    let svg = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}"><g class="axis">`;
    for (const v of ticks) {
      svg += `<line x1="${pad.l}" x2="${W - pad.r}" y1="${y(v)}" y2="${y(v)}"/><text x="${pad.l - 8}" y="${y(v) + 4}" text-anchor="end"${cfg.money ? ' class="ymoney"' : ''}>${esc(yfmt(v))}</text>`;
    }
    items.forEach((it, i) => {
      if (i % every === 0 || i === items.length - 1) {
        svg += `<text x="${pad.l + iw * i + iw / 2}" y="${H - 7}" text-anchor="middle">${esc(it.label)}</text>`;
      }
    });
    svg += '</g>';
    items.forEach((it, i) => {
      const h = Math.max(0, y(0) - y(it.value));
      svg += `<rect x="${pad.l + iw * i + (iw - bw) / 2}" y="${y(0) - h}" width="${bw}" height="${h}" rx="2" fill="${cv(it.color || cfg.color || 'var(--accent)')}"/>`;
    });
    for (const h of cfg.hlines || []) {
      svg += `<line x1="${pad.l}" x2="${W - pad.r}" y1="${y(h.v)}" y2="${y(h.v)}" stroke="${cv(h.color) || 'currentColor'}" stroke-dasharray="4 4"/>`;
      if (h.label) svg += `<text x="${W - pad.r}" y="${y(h.v) - 5}" text-anchor="end" font-size="11" fill="${cv(h.color) || 'currentColor'}">${esc(h.label)}</text>`;
    }
    svg += `<rect class="hit" x="${pad.l}" y="0" width="${W - pad.l - pad.r}" height="${H}" fill="transparent"/></svg><div class="tip" hidden></div>`;
    el.innerHTML = svg;
    const hit = el.querySelector('.hit'), tip = el.querySelector('.tip');
    const fmt = cfg.fmt || compact;
    hit.addEventListener('mousemove', ev => {
      const px = ev.clientX - el.getBoundingClientRect().left;
      const i = Math.max(0, Math.min(items.length - 1, Math.floor((px - pad.l) / iw)));
      const it = items[i];
      tip.innerHTML = `<div class="muted">${esc(it.long || it.label)}</div><b${cfg.money ? ' class="pv"' : ''}>${esc(fmt(it.value))}</b>${it.note ? `<div>${esc(it.note)}</div>` : ''}`;
      tip.hidden = false;
      const cx = pad.l + iw * i + iw / 2;
      tip.style.left = `${Math.max(0, cx + 12 + tip.offsetWidth > W ? cx - tip.offsetWidth - 12 : cx + 12)}px`;
      tip.style.top = `${pad.t}px`;
    });
    hit.addEventListener('mouseleave', () => { tip.hidden = true; });
  }

  // ---------------------------------------------------------------- static pieces
  function spark(points, { w = 120, h = 30, color = 'var(--accent)', area = true, avg = null } = {}) {
    color = cv(color);
    if (!points || points.length < 2) return '<span class="muted tiny">no chart</span>';
    const vals = points.map(p => +p[1]).concat(avg ? avg.map(p => +p[1]) : []);
    const lo = Math.min(...vals), hi = Math.max(...vals), span = hi - lo || 1;
    const t0 = parseT(points[0][0]), t1 = parseT(points.at(-1)[0]) || t0 + 1;
    const X = t => ((t - t0) / (t1 - t0 || 1)) * w;
    const Y = v => 2 + (1 - (v - lo) / span) * (h - 4);
    const path = pts => pts.map((p, i) => `${i ? 'L' : 'M'}${X(parseT(p[0])).toFixed(1)},${Y(+p[1]).toFixed(1)}`).join('');
    const d = path(points);
    return `<svg class="spark" width="100%" height="${h}" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true">` +
      (area ? `<path d="${d}L${w},${h}L0,${h}Z" fill="${color}" opacity=".12"/>` : '') +
      (avg && avg.length > 1 ? `<path d="${path(avg)}" fill="none" stroke="${color}" stroke-width="1.2" stroke-dasharray="3 3" opacity=".7" vector-effect="non-scaling-stroke"/>` : '') +
      `<path d="${d}" fill="none" stroke="${color}" stroke-width="1.6" vector-effect="non-scaling-stroke"/></svg>`;
  }

  function arc(cx, cy, r, a0, a1) {
    const p = a => [cx + r * Math.sin(a), cy - r * Math.cos(a)];
    const [x0, y0] = p(a0), [x1, y1] = p(a1);
    return `M${x0.toFixed(2)},${y0.toFixed(2)}A${r},${r} 0 ${a1 - a0 > Math.PI ? 1 : 0} 1 ${x1.toFixed(2)},${y1.toFixed(2)}`;
  }

  // A slice covering the whole ring starts and ends at the same point, and an SVG arc
  // between identical points draws nothing — Mittens & Pence's donut went blank for the
  // commonest real case, one account. Two half arcs make a full circle.
  function ringPath(cx, cy, r, a0, a1) {
    if (a1 - a0 >= Math.PI * 2 - 1e-6) return arc(cx, cy, r, 0, Math.PI) + arc(cx, cy, r, Math.PI, Math.PI * 2 - 1e-4);
    return arc(cx, cy, r, a0, a1);
  }

  function donut(slices, { size = 200, thick = 24, inner = null, centre = '', sub = '' } = {}) {
    const c = size / 2, r = c - thick / 2 - 2;
    const total = slices.reduce((a, s) => a + Math.max(0, s.value), 0) || 1;
    let a = 0, out = `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" role="img" aria-label="Allocation">`;
    out += `<circle cx="${c}" cy="${c}" r="${r}" fill="none" stroke="${cv('var(--line-2)')}" stroke-width="${thick}"/>`;
    for (const s of slices) {
      const f = Math.max(0, s.value) / total;
      if (f <= 0) continue;
      const a1 = a + f * Math.PI * 2;
      out += `<path d="${ringPath(c, c, r, a, a1 - (f < 1 ? 0.012 : 0))}" fill="none" stroke="${cv(s.color)}" stroke-width="${thick}"/>`;
      a = a1;
    }
    if (inner && inner.length) {
      const ri = r - thick / 2 - 7, tsum = inner.reduce((q, s) => q + Math.max(0, s.value), 0) || 1;
      let b = 0;
      for (const s of inner) {
        const f = Math.max(0, s.value) / tsum;
        if (f <= 0) continue;
        const b1 = b + f * Math.PI * 2;
        out += `<path d="${ringPath(c, c, ri, b, b1 - (f < 1 ? 0.02 : 0))}" fill="none" stroke="${cv(s.color)}" stroke-width="5" opacity=".75"/>`;
        b = b1;
      }
    }
    if (centre) out += `<text x="${c}" y="${c + 2}" text-anchor="middle" style="font-family:var(--num)" font-size="${size / 9}" fill="${cv('var(--ink)')}">${esc(centre)}</text>`;
    if (sub) out += `<text x="${c}" y="${c + size / 9}" text-anchor="middle" font-size="${size / 17}" fill="${cv('var(--muted)')}">${esc(sub)}</text>`;
    return out + '</svg>';
  }

  // Semicircle with coloured zones and a needle. `frac` is 0..1 along the arc.
  function gauge(frac, { zones, size = 240, label = '' } = {}) {
    const w = size, h = size * 0.62, cx = w / 2, cy = h - 12, r = w / 2 - 16;
    const ang = f => -Math.PI / 2 + f * Math.PI;
    let out = `<svg class="gauge" width="100%" viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(label)}">`;
    let from = 0;
    for (const z of zones) {
      out += `<path d="${arc(cx, cy, r, ang(from) + 0.02, ang(z.to) - 0.02)}" fill="none" stroke="${cv(z.color)}" stroke-width="14" stroke-linecap="butt" opacity="${z.dim ? .35 : 1}"/>`;
      from = z.to;
    }
    if (frac !== null && frac !== undefined) {
      const a = ang(Math.max(0, Math.min(1, frac)));
      const nx = cx + (r - 22) * Math.sin(a), ny = cy - (r - 22) * Math.cos(a);
      out += `<line x1="${cx}" y1="${cy}" x2="${nx.toFixed(1)}" y2="${ny.toFixed(1)}" stroke="currentColor" stroke-width="3" stroke-linecap="round"/><circle cx="${cx}" cy="${cy}" r="6" fill="currentColor"/>`;
    }
    return out + '</svg>';
  }

  function ring(frac, { size = 132, color = 'var(--accent)', text = '', sub = '', thick = 12 } = {}) {
    const c = size / 2, r = c - thick / 2 - 1, f = Math.max(0, Math.min(1, frac || 0));
    let out = `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" role="img" aria-label="${esc(text)} ${esc(sub)}">` +
      `<circle cx="${c}" cy="${c}" r="${r}" fill="none" stroke="${cv('var(--line-2)')}" stroke-width="${thick}"/>`;
    if (f > 0) out += `<path d="${ringPath(c, c, r, 0, f * Math.PI * 2)}" fill="none" stroke="${cv(color)}" stroke-width="${thick}" stroke-linecap="${f >= 1 ? 'butt' : 'round'}"/>`;
    out += `<text x="${c}" y="${c + 4}" text-anchor="middle" style="font-family:var(--num)" font-size="${size / 6.2}" fill="${cv('var(--ink)')}">${esc(text)}</text>`;
    if (sub) out += `<text x="${c}" y="${c + size / 6}" text-anchor="middle" font-size="${size / 12}" fill="${cv('var(--muted)')}">${esc(sub)}</text>`;
    return out + '</svg>';
  }

  // One thin cell per day, coloured by what the lights said that day.
  function strip(days, colour, { h = 26 } = {}) {
    if (!days || !days.length) return '';
    const n = days.length;
    let out = `<svg width="100%" height="${h}" viewBox="0 0 ${n} ${h}" preserveAspectRatio="none" role="img" aria-label="Readings over time">`;
    let start = 0;
    for (let i = 1; i <= n; i++) {
      if (i === n || days[i][1] !== days[start][1]) {
        out += `<rect x="${start}" y="0" width="${i - start}" height="${h}" fill="${cv(colour(days[start][1]))}"/>`;
        start = i;
      }
    }
    return out + '</svg>';
  }

  function waffle(cells) {
    return `<div class="waffle" role="img" aria-label="One square per percent">` +
      cells.map(c => `<i style="background:${c.colour}" title="${esc(c.name)}"></i>`).join('') + '</div>';
  }

  return {
    line: (cfg, height = 240) => place('line', cfg, height),
    bars: (cfg, height = 200) => place('bars', cfg, height),
    mount, spark, donut, gauge, ring, strip, waffle, compact,
  };
})();
