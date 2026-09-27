"""Everything that deserves a look, in one list, worst first.

Rules the person has set — "trim Alphabet back to 8% when it passes 9.3%" — are checked
here, alongside the limits that come with the territory: each platform against the FSCS
protection limit, each sleeve against its band, and the gaps in the data that would make
any of those figures wrong.

A warning always says what was found, what it is being compared with, and where to go
about it. Where a rule implies a trade, the size is given as arithmetic on the person's
own rule — "selling about £1,900 brings it back to 8%" — never as advice to do it.
"""

from __future__ import annotations

from .. import db
from . import isa

ORDER = {"red": 0, "amber": 1, "info": 2, "green": 3}


def _month_ago_sleeves() -> dict:
    """Sleeve shares from the daily snapshot of about a month ago, when there is one."""
    import datetime as dt
    import json
    lo = (dt.date.today() - dt.timedelta(days=40)).isoformat()
    hi = (dt.date.today() - dt.timedelta(days=25)).isoformat()
    row = db.one("SELECT detail FROM snapshots WHERE d BETWEEN ? AND ? ORDER BY d LIMIT 1", (lo, hi))
    try:
        return (json.loads(row["detail"]) or {}).get("_sleeves", {}) if row else {}
    except (ValueError, TypeError):
        return {}


def _drift_trend(r: dict, then: float | None) -> str:
    """A drift is a trend or a jolt; last month's share says which."""
    if then is None:
        return ""
    before, now = abs(then - r["target"]), abs(r["actual"] - r["target"])
    if abs(now - before) < 0.2:
        return f" A month ago it was {then:.1f}%, so this has been the case for a while."
    return (f" A month ago it was {then:.1f}%, so it is moving "
            f"{'further from' if now > before else 'back towards'} its target.")


def _money(v: float) -> str:
    return f"£{v:,.0f}"


def company_exposure(pos: list[dict], total: float, company: str) -> dict:
    name = (company or "").strip().lower()
    direct = [x for x in pos if (x["company"] or "").strip().lower() == name and x["value"] is not None]
    direct_value = sum(x["value"] for x in direct)
    fund_values: dict[int, float] = {}
    for x in pos:
        if x["value"] is not None:
            fund_values[x["instrument_id"]] = fund_values.get(x["instrument_id"], 0.0) + x["value"]
    look = db.rows("SELECT l.fund_id, l.weight, l.as_of, i.name FROM lookthrough l "
                   "JOIN instruments i ON i.id=l.fund_id WHERE lower(l.company)=?", (name,))
    via = [{"fund_id": r["fund_id"], "name": r["name"], "weight": r["weight"], "as_of": r["as_of"],
            "value": fund_values.get(r["fund_id"], 0.0) * r["weight"] / 100} for r in look]
    lt_value = sum(v["value"] for v in via)
    return {"company": company, "direct_value": direct_value,
            "direct_pct": (direct_value / total * 100) if total else None,
            "true_value": direct_value + lt_value,
            "true_pct": ((direct_value + lt_value) / total * 100) if total else None,
            "holdings": [{"name": x["name"], "platform": x["platform"], "value": x["value"]}
                         for x in direct],
            "via_funds": via}


def rule_status(pos: list[dict], totals: dict, exp: dict | None = None) -> list[dict]:
    total = totals.get("total") or 0.0
    out = []
    for r in db.rows("SELECT * FROM rules WHERE enabled=1 ORDER BY id"):
        trig = float(r["trigger_pct"])
        tgt = float(r["target_pct"]) if r["target_pct"] is not None else None
        if r["kind"] == "company_cap":
            ce = company_exposure(pos, total, r["subject"])
            now = ce["true_pct"] if r["basis"] == "true" else ce["direct_pct"]
            item = {"rule": r, "now": now, "detail": ce}
        elif r["kind"] == "theme_cap":
            v = sum(x["value"] for x in pos if x["value"] is not None
                    and (x["theme"] or "").strip().lower() == (r["subject"] or "").strip().lower())
            item = {"rule": r, "now": (v / total * 100) if total else None, "detail": {"value": v}}
        elif r["kind"] == "ai_cap":
            item = {"rule": r, "now": (exp["ai_pct"] * 100) if exp and exp.get("ai_pct") is not None
                    else None, "detail": {}}
        else:
            continue
        now = item["now"]
        if now is None:
            item["level"] = "none"
        else:
            back_to = tgt if tgt is not None else trig
            amber_from = back_to + (trig - back_to) / 2 if tgt is not None else trig * 0.9
            item["level"] = "red" if now > trig else "amber" if now > amber_from else "green"
            item["amber_from"] = amber_from
            item["trim"] = max(0.0, (now - back_to) / 100 * total) if now > back_to else 0.0
        out.append(item)
    return out


def _rule_warning(s: dict) -> dict | None:
    r, now = s["rule"], s["now"]
    if s["level"] not in ("red", "amber"):
        return None
    who = r["subject"] or "AI-linked holdings"
    basis = " counting what your funds hold too" if r["basis"] == "true" else ""
    if s["level"] == "red":
        title = f"{who} is {now:.1f}% of the portfolio — over your {r['trigger_pct']:g}% trigger"
    else:
        title = f"{who} is {now:.1f}%{basis} — past halfway to your {r['trigger_pct']:g}% trigger"
    detail = r["note"] or ""
    if r["target_pct"] is not None and s.get("trim"):
        detail = (detail + " " if detail else "") + (
            f"Your rule brings it back to {r['target_pct']:g}%: that is selling about "
            f"{_money(s['trim'])} of it.")
    return {"id": f"rule:{r['id']}", "level": s["level"], "kind": r["kind"], "title": title,
            "detail": detail.strip(), "go": "allocation"}


def _regime_since(market: dict) -> str:
    strip = market.get("strip") or []
    if not strip:
        return ""
    i = len(strip) - 1
    while i > 0 and strip[i - 1][1] == strip[-1][1]:
        i -= 1
    return f" The lights have read like this since {strip[i][0]}."


def evaluate(pos: list[dict], totals: dict, alloc: dict, exp: dict | None = None,
             market: dict | None = None, playbook: dict | None = None,
             holding_targets: list[dict] | None = None) -> list[dict]:
    out: list[dict] = []

    for s in rule_status(pos, totals, exp):
        w = _rule_warning(s)
        if w:
            out.append(w)

    for p in totals.get("platforms", []):
        if not p["total"]:
            continue
        if p.get("kind") == "card":
            continue                                   # a debt, not something to protect
        share = p["total"] / p["limit"] if p["limit"] else 0
        if p.get("kind") == "bank":
            if share >= 0.9:
                out.append({"id": f"fscs:{p['id']}", "level": "red" if share > 1 else "amber",
                            "kind": "fscs",
                            "title": f"{p['name']} holds {_money(p['total'])}, against "
                                     f"{_money(p['limit'])} of deposit protection",
                            "detail": "FSCS protects bank deposits up to £120,000 per person per "
                                      "banking licence. Brands that share a licence share one limit.",
                            "go": "settings"})
            continue
        if share > 1:
            out.append({"id": f"fscs:{p['id']}", "level": "red", "kind": "fscs",
                        "title": f"{p['name']} is {_money(p['total'] - p['limit'])} over the "
                                 f"{_money(p['limit'])} protection limit",
                        "detail": "FSCS protects up to £85,000 per person per firm if a platform "
                                  "fails and assets turn out to be missing. Your investments are "
                                  "held separately from the platform's own money, so this is a "
                                  "back-stop — but it is the limit your plan is built around.",
                        "go": "overview"})
        elif share >= 0.9:
            out.append({"id": f"fscs:{p['id']}", "level": "amber", "kind": "fscs",
                        "title": f"{p['name']} is within {_money(p['limit'] - p['total'])} of the "
                                 f"{_money(p['limit'])} protection limit",
                        "detail": "Growth alone can take it over. New money may be better "
                                  "paid into another platform.", "go": "overview"})

    month_ago = _month_ago_sleeves()
    for r in alloc["sleeves"]:
        trend = _drift_trend(r, month_ago.get(r["name"]))
        if r["status"] == "red":
            direction = "over" if r["drift"] > 0 else "under"
            out.append({"id": f"sleeve:{r['id']}", "level": "red", "kind": "drift",
                        "title": f"{r['name']} is {r['actual']:.1f}% against a {r['target']:g}% target",
                        "detail": f"{abs(r['drift']):.1f} points {direction}, outside its "
                                  f"±{r['band']:.2g}-point band.{trend}", "go": "allocation"})
        elif r["status"] == "amber":
            out.append({"id": f"sleeve:{r['id']}", "level": "amber", "kind": "drift",
                        "title": f"{r['name']} is drifting: {r['actual']:.1f}% against {r['target']:g}%",
                        "detail": f"Past half of its ±{r['band']:.2g}-point band.{trend}",
                        "go": "allocation"})
    if alloc["sleeves"] and not alloc["targets_add_up"]:
        out.append({"id": "targets", "level": "amber", "kind": "data",
                    "title": f"Your sleeve targets add up to {alloc['target_sum']:g}%, not 100%",
                    "detail": "Every drift figure is measured against these, so they need to "
                              "add up.", "go": "settings"})

    if playbook:
        t = playbook["tier"]
        if t["level"] in ("amber", "red"):
            out.append({"id": "signals", "level": t["level"], "kind": "market",
                        "title": f"Your signals: {playbook['firing']} of {playbook['of']} firing, {t['label'].lower()}",
                        "detail": t["text"], "go": "ai"})
        if playbook["manual_due"]:
            out.append({"id": "signals-due", "level": "info", "kind": "market",
                        "title": "The quarterly signals need filling in",
                        "detail": "Capex guidance, Nvidia data-centre growth and the Magnificent Seven's "
                                  "share, after each earnings season.", "go": "ai"})
        lad = playbook["ladder"]
        if lad.get("drop") is not None and lad["drop"] >= 10:
            rung = next(r for r in lad["rungs"] if r.get("active"))
            out.append({"id": "ladder", "level": "red" if lad["drop"] >= 20 else "amber", "kind": "market",
                        "title": f"Your holdings are {lad['drop']:.0f}% below their high: {rung['text'].lower()}",
                        "detail": "From your ladder. Never: " + lad["never"][0].lower() + lad["never"][1:],
                        "go": "ai"})
    out_of_band = [h for h in (holding_targets or []) if h["status"] == "out"]
    if out_of_band:
        out.append({"id": "holding-bands", "level": "info", "kind": "drift",
                    "title": f"{len(out_of_band)} holding{'s' if len(out_of_band) != 1 else ''} outside "
                             f"their own target band",
                    "detail": ", ".join(h["key"] for h in out_of_band[:8]) +
                              (" and more" if len(out_of_band) > 8 else "") + ".",
                    "go": "allocation"})
    if market and market.get("regime") in ("turning", "stress"):
        reds = sum(1 for x in market["lights"] if x["level"] == "red")
        level = "red"
        out.append({"id": "market", "level": level, "kind": "market",
                    "title": f"Market lights: {market['label']}, {reds} of {market['have']} red",
                    "detail": market["text"] + _regime_since(market), "go": "ai"})
    econ = [x for x in (market or {}).get("lights", []) if x.get("group") == "economy"
            and x["level"] in ("amber", "red")]
    if econ and any(x["level"] == "red" for x in econ):
        out.append({"id": "economy", "level": "amber", "kind": "market",
                    "title": "The economy: " + ", ".join(
                        f"{x['title'].lower()} {x['level']} since {x['since']}" for x in econ),
                    "detail": "Slow gauges of a downturn building. They describe the economy, not "
                              "prices, and have given false alarms as well as true ones.", "go": "ai"})

    # Gaps in the data: each of these makes some figure above less true.
    unassigned = [x for x in pos if x["sleeve_id"] is None]
    if unassigned:
        out.append({"id": "unassigned", "level": "info", "kind": "data",
                    "title": f"{len(unassigned)} holding{'s' if len(unassigned) != 1 else ''} "
                             f"not in a sleeve yet",
                    "detail": "They are left out of every sleeve's percentage until they are.",
                    "go": "allocation"})
    unpriced = [x for x in pos if x["value"] is None]
    if unpriced:
        out.append({"id": "unpriced", "level": "amber", "kind": "data",
                    "title": f"No price for {len(unpriced)} holding{'s' if len(unpriced) != 1 else ''}",
                    "detail": ", ".join(x["name"] for x in unpriced[:5]) +
                              " — left out of the totals rather than counted as £0. Check the "
                              "price symbol on the Holdings screen.", "go": "holdings"})
    if exp and exp["unknown"]:
        out.append({"id": "ai_unset", "level": "info", "kind": "data",
                    "title": f"AI share not set for {len(exp['unknown'])} holding"
                             f"{'s' if len(exp['unknown']) != 1 else ''}",
                    "detail": f"{_money(exp['unknown_value'])} is left out of the AI figure until "
                              f"it is.", "go": "ai"})
    for p in totals.get("platforms", []):
        if p["last_error"]:
            out.append({"id": f"sync:{p['id']}", "level": "amber", "kind": "data",
                        "title": f"{p['name']} didn't update", "detail": p["last_error"],
                        "go": "settings"})
    from ..market import store
    wanted = set(store.wanted_keys())
    stale = [r for r in db.rows("SELECT key, last_error, last_ok FROM series_meta WHERE key LIKE "
                                "'SEC:%' AND last_error IS NOT NULL") if r["key"] in wanted]
    if stale:
        out.append({"id": "prices", "level": "amber", "kind": "data",
                    "title": f"Prices for {len(stale)} holding{'s' if len(stale) != 1 else ''} "
                             f"couldn't be refreshed",
                    "detail": stale[0]["last_error"], "go": "settings"})

    a = isa.allowance()
    if a["has_data"]:
        if a["over"]:
            out.append({"id": "isa", "level": "red", "kind": "isa",
                        "title": f"Paid in {_money(a['used'])} this tax year — over the "
                                 f"{_money(a['limit'])} ISA allowance",
                        "detail": "Worth checking with the platforms: over-subscribing an ISA has "
                                  "to be corrected with HMRC.", "go": "activity"})
        elif a["days_left"] is not None:
            out.append({"id": "isa", "level": "info", "kind": "isa",
                        "title": f"{_money(a['remaining'])} of this year's ISA allowance left",
                        "detail": f"{a['days_left']} days until the tax year ends on 5 April.",
                        "go": "activity"})

    out.sort(key=lambda w: ORDER.get(w["level"], 9))
    return out
