"""Your signals, your tiers and your ladder: the playbook, run by the app.

This is the decision layer from Allan's Investments 2 workbook (the TRIGGERS and
Playbook sheets), not the app's own invention. Eight signals, each simply firing or not:

* five fetched automatically — the US 10-year yield, the UK 10-year gilt yield, the US
  junk-bond spread, the VIX, and market breadth measured from a baseline date;
* three that no free data feed publishes, filled in by hand after each earnings season —
  how many of the big four cloud companies are guiding capex flat or down, Nvidia's
  data-centre growth, and the Magnificent Seven's share of the S&P 500.

The count decides the tier: 0-1 normal, 2-3 elevated, 4 or more structural. None of them
is a sell signal. They say what kind of drawdown this is; the ladder, driven only by how
far the portfolio itself has fallen, says when to deploy cash.

Thresholds and the words for each action come from the plan file, so the playbook is
edited in one place. The defaults below are the workbook's own numbers.
"""

from __future__ import annotations

import datetime as dt

from .. import db
from ..market import store
from . import mathx

SIGNALS = [
    {"key": "us10y", "title": "US 10-year yield", "group": "market", "kind": "auto",
     "ref": "US10Y", "op": ">", "threshold": 5.0, "unit": "%",
     "means": "Growth valuations compress as the discount rate rises."},
    {"key": "uk10y", "title": "UK 10-year gilt yield", "group": "market", "kind": "auto",
     "ref": "UK10Y", "op": ">", "threshold": 5.5, "unit": "%",
     "means": "Above this, gilts stop cushioning falls in shares and start moving with them. "
              "The series is a monthly average, so it lags by a few weeks."},
    {"key": "hy", "title": "US junk-bond spread", "group": "market", "kind": "auto",
     "ref": "HYOAS", "op": ">", "threshold": 4.5, "unit": "%",
     "means": "Credit stress tends to reach the real economy before share prices show it."},
    {"key": "breadth", "title": "Breadth since your baseline", "group": "market", "kind": "auto",
     "ref": ("RSP", "SPY"), "op": "<", "threshold": -10.0, "unit": "%",
     "means": "The equal-weight US market against the size-weighted one, since your baseline "
              "date. Falling means the rally has narrowed to the giants."},
    {"key": "vix", "title": "VIX", "group": "market", "kind": "auto",
     "ref": "VIX", "op": ">", "threshold": 25.0, "unit": "",
     "means": "Short-term fear. A poor predictor on its own, useful alongside credit."},
    {"key": "hyperscalers", "title": "Hyperscalers guiding capex flat or down", "group": "ai",
     "kind": "manual", "op": ">=", "threshold": 2, "unit": "of 4",
     "choices": ["Amazon", "Alphabet", "Meta", "Microsoft"],
     "means": "The AI trade rests on this spending continuing. It shows in guidance before "
              "it shows in prices."},
    {"key": "nvda_dc", "title": "Nvidia data-centre growth, year on year", "group": "ai",
     "kind": "manual", "op": "<", "threshold": 30.0, "unit": "%",
     "means": "A slowing growth rate confirms the capex signal rather than leading it."},
    {"key": "mag7", "title": "Magnificent Seven share of the S&P 500", "group": "ai",
     "kind": "manual", "op": ">", "threshold": 38.0, "unit": "%",
     "means": "Index concentration: your look-through exposure rises without you buying anything."},
]

TIERS = [
    {"from": 0, "label": "Normal", "level": "green",
     "text": "Do nothing. Don't look again for a month."},
    {"from": 2, "label": "Elevated", "level": "amber",
     "text": "Re-read the ladder. Check nothing has drifted out of band. Still don't sell."},
    {"from": 4, "label": "Structural", "level": "red",
     "text": "Still don't sell the core index. Deploy cash by the ladder only if the portfolio "
             "has actually fallen."},
]

LADDER = [
    {"from": 0, "text": "Nothing"},
    {"from": 10, "text": "Rebalance to bands only"},
    {"from": 20, "text": "Deploy the first third of cash"},
    {"from": 30, "text": "Deploy the second third"},
    {"from": 40, "text": "Deploy the final third"},
]
NEVER = "Sell the core index, stop contributions, or go to cash wholesale."
#: The three hand-filled signals are due again after each earnings season.
STALE_DAYS = 100


def overrides() -> dict:
    return db.get_meta("playbook", {}) or {}


def manual_values() -> dict:
    return db.get_meta("manual_signals", {}) or {}


def set_manual(key: str, value=None, ticked: list | None = None) -> dict:
    defn = next((s for s in SIGNALS if s["key"] == key and s["kind"] == "manual"), None)
    if not defn:
        raise KeyError(key)
    vals = manual_values()
    if defn.get("choices"):
        ticked = [c for c in (ticked or []) if c in defn["choices"]]
        vals[key] = {"ticked": ticked, "value": len(ticked), "updated": db.today()}
    else:
        vals[key] = {"value": None if value in (None, "") else float(value), "updated": db.today()}
    db.set_meta("manual_signals", vals)
    return vals[key]


def _fires(op: str, value: float, threshold: float) -> bool:
    return {">": value > threshold, ">=": value >= threshold,
            "<": value < threshold, "<=": value <= threshold}[op]


def _auto(defn: dict, ov: dict) -> dict:
    """The reading as a series, so a signal is judged on how it has behaved rather than
    on one day: daily series use a 5-day average, like the market lights."""
    ref = defn["ref"]
    extra = {}
    if isinstance(ref, tuple):
        pts = mathx.ratio(store.points(store.ref_key(ref[0])), store.points(store.ref_key(ref[1])))
        if not pts:
            return {"value": None, "as_of": None, "series": []}
        base_day = ov.get("breadth_baseline") or \
            (dt.date.fromisoformat(pts[-1][0]) - dt.timedelta(days=365)).isoformat()
        base = mathx.value_on(pts, base_day)
        if not base:
            return {"value": None, "as_of": pts[-1][0], "series": [],
                    "note": f"No data as far back as {base_day}."}
        pts = [(d, (v / base - 1) * 100) for d, v in pts if d >= base_day]
        extra["baseline"] = base_day
    else:
        pts = store.points(store.ref_key(ref))
    if not pts:
        return {"value": None, "as_of": None, "series": []}
    daily = len(pts) > 40 and (dt.date.fromisoformat(pts[-1][0]) -
                               dt.date.fromisoformat(pts[-40][0])).days < 90
    if daily:
        sm = mathx.sma([v for _, v in pts], 5)
        pts = [(d, s_ if s_ is not None else v) for (d, v), s_ in zip(pts, sm)]
    return {"value": pts[-1][1], "as_of": pts[-1][0], "series": pts, "averaged": daily, **extra}


def _streak(series: list, op: str, threshold: float) -> dict:
    """Since when the signal has been in its current state, and which way it moved over
    the past month."""
    if not series:
        return {}
    state = _fires(op, series[-1][1], threshold)
    i = len(series) - 1
    while i > 0 and _fires(op, series[i - 1][1], threshold) == state:
        i -= 1
    month_ago = (dt.date.fromisoformat(series[-1][0]) - dt.timedelta(days=30)).isoformat()
    then = mathx.value_on(series, month_ago)
    change = None if then is None else series[-1][1] - then
    return {"since": series[i][0], "change_1m": change}


def evaluate(backdated: dict | None = None, cash_value: float | None = None) -> dict:
    ov = overrides()
    sig_ov = ov.get("signals") or {}
    manual = manual_values()
    today = dt.date.today()
    rows = []
    for d in SIGNALS:
        o = sig_ov.get(d["key"]) or {}
        threshold = float(o.get("threshold", d["threshold"]))
        row = {k: d[k] for k in ("key", "title", "group", "kind", "op", "unit", "means")}
        row.update(threshold=threshold, action=o.get("action") or "", choices=d.get("choices"))
        if d["kind"] == "auto":
            got = _auto(d, ov)
            series = got.pop("series", [])
            row.update(got)
            row.update(_streak(series, d["op"], threshold))
            row["stale"] = False
        else:
            m = manual.get(d["key"]) or {}
            row.update(value=m.get("value"), ticked=m.get("ticked") or [], updated=m.get("updated"))
            row["stale"] = (not m.get("updated")) or \
                (today - dt.date.fromisoformat(m["updated"])).days > STALE_DAYS
        row["firing"] = None if row.get("value") is None else _fires(d["op"], row["value"], threshold)
        rows.append(row)
    firing = sum(1 for r in rows if r["firing"])
    known = sum(1 for r in rows if r["firing"] is not None)
    tiers = [dict(t, text=(ov.get("tiers") or {}).get(t["label"].lower(), t["text"])) for t in TIERS]
    tier = [t for t in tiers if firing >= t["from"]][-1]
    manual_rows = [r for r in rows if r["kind"] == "manual"]
    return {"signals": rows, "firing": firing, "known": known, "of": len(rows), "tier": tier,
            "tiers": tiers, "ladder": ladder(backdated, cash_value, ov),
            "manual_due": any(r["stale"] for r in manual_rows),
            "manual_updated": max((r["updated"] for r in manual_rows if r.get("updated")), default=None)}


def ladder(backdated: dict | None, cash_value: float | None, ov: dict | None = None) -> dict:
    """How far today's holdings sit below their high, and which rung that is. Measured on
    the backdated history of today's mix, so money paid in never disguises a fall."""
    ov = ov or {}
    texts = ov.get("ladder") or {}
    rungs = [dict(r, text=texts.get(str(r["from"]), r["text"])) for r in LADDER]
    pts = (backdated or {}).get("points") or []
    out = {"rungs": rungs, "never": ov.get("never") or NEVER, "drop": None,
           "cash": cash_value, "third": (cash_value / 3) if cash_value else None}
    if len(pts) < 20:
        return out
    high_d, high_v = max(pts, key=lambda p: p[1])
    now = pts[-1][1]
    # Rounded before it meets a rung: 80 against 100 is 19.999999999999996% in floating
    # point, which would otherwise sit a whole rung too low.
    drop = max(0.0, round((1 - now / high_v) * 100, 6)) if high_v else 0.0
    active = [r for r in rungs if drop >= r["from"]][-1]
    for r in rungs:
        r["active"] = r is active
    out.update(drop=drop, high=high_v, high_on=high_d, now=now)
    return out
