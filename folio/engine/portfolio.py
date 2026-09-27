"""What everything is worth, in pounds, and how sure we are about it.

Each holding is valued from the freshest trustworthy figure available:

1. the broker's own valuation (Trading 212 reports every position in pounds), or
2. a market price times the share count, converted at that day's exchange rate, or
3. for a Freetrade holding with no market price, Trading 212's price for the same ISIN
   — the FSCS duplicates are the same shares held in two places.

When a broker value and a market price are from the same day, the broker wins: it is
the broker's own record of the account. Otherwise the newer wins. Every row carries
where its number came from and when, and a holding nobody can price is left as None
and counted, never quietly added in as zero.
"""

from __future__ import annotations

import datetime as dt
import json

from .. import config, db
from ..brokers import tbills
from ..market import store
from . import mathx


def _ai_share(r: dict) -> float | None:
    if r.get("ai_share") is not None:
        return float(r["ai_share"])
    if r.get("sleeve_ai") is not None:
        return float(r["sleeve_ai"])
    return None


def positions() -> list[dict]:
    rows = db.rows(
        "SELECT p.platform_id, p.instrument_id, p.quantity, p.cost, p.broker_value, p.broker_price,"
        " p.broker_ccy, p.valued_at, p.source, i.symbol, i.name, i.isin, i.exchange, i.currency,"
        " i.market_symbol, i.sleeve_id, i.ai_share, i.company, i.theme, i.notes,"
        " pl.name AS platform, pl.provider, s.name AS sleeve, s.ai_share AS sleeve_ai,"
        " s.colour AS sleeve_colour"
        " FROM positions p JOIN instruments i ON i.id=p.instrument_id"
        " JOIN platforms pl ON pl.id=p.platform_id"
        " LEFT JOIN sleeves s ON s.id=i.sleeve_id"
        " WHERE p.quantity > 0 ORDER BY i.name")
    # Per-share pound prices implied by a broker's valuation, keyed by ISIN, for pricing
    # the same shares where they are held without one.
    implied: dict[str, tuple[float, str]] = {}
    for r in rows:
        if r["broker_value"] and r["quantity"] and r["isin"]:
            implied[r["isin"]] = (r["broker_value"] / r["quantity"], r["valued_at"] or "")
    out = []
    for r in rows:
        out.append(_value(r, implied))
    return out


def _value(r: dict, implied: dict) -> dict:
    key = store.sec_key(r["market_symbol"]) if r["market_symbol"] else None
    mkt = store.latest(key) if key else None
    mkt_gbp = store.to_gbp(mkt["value"], mkt["currency"]) if mkt else None
    qty = r["quantity"]
    value = price_gbp = None
    source = as_of = None
    broker_day = (r["valued_at"] or "")[:10]
    mkt_day = (mkt["as_of"] if mkt else "")[:10]
    if r["broker_value"] is not None and (mkt_gbp is None or broker_day >= mkt_day):
        value, source, as_of = r["broker_value"], "broker", r["valued_at"]
        price_gbp = value / qty if qty else None
    elif mkt_gbp is not None:
        price_gbp = mkt_gbp
        value, source, as_of = qty * mkt_gbp, "market", mkt["as_of"]
    elif r["isin"] in implied:
        price_gbp, as_of = implied[r["isin"]]
        value, source = qty * price_gbp, "broker-same-isin"
    elif r["cost"] is not None and tbills.is_tbill(r["name"], r["symbol"], r["isin"]):
        # A Treasury bill has no market price anyone publishes. Held to maturity it
        # repays its face value; at cost it is at most a few pence in the pound out.
        value, source = r["cost"], "at-cost"
        price_gbp = value / qty if qty else None

    # Today's move, in pounds, from the last two daily closes (and the live price when
    # it is newer than the last close). Needs a market series; None without one.
    day_change = day_pct = None
    if key:
        pts = store.gbp_points(key, (dt.date.today() - dt.timedelta(days=12)).isoformat())
        if mkt and mkt.get("live") and mkt_gbp is not None and pts and mkt["as_of"][:10] > pts[-1][0]:
            prev, now_p = pts[-1][1], mkt_gbp
        elif len(pts) >= 2:
            prev, now_p = pts[-2][1], pts[-1][1]
        else:
            prev = now_p = None
        if prev:
            day_pct = now_p / prev - 1
            day_change = qty * (now_p - prev)

    cost = r["cost"]
    gain = (value - cost) if (value is not None and cost is not None) else None
    return {
        "platform_id": r["platform_id"], "platform": r["platform"], "provider": r["provider"],
        "instrument_id": r["instrument_id"], "symbol": r["symbol"], "name": r["name"] or r["symbol"],
        "isin": r["isin"], "market_symbol": r["market_symbol"], "currency": r["currency"],
        "quantity": qty, "cost": cost, "value": value, "price_gbp": price_gbp,
        "value_source": source, "value_as_of": as_of, "gain": gain,
        "gain_pct": (gain / cost) if (gain is not None and cost) else None,
        "day_change": day_change, "day_pct": day_pct,
        "sleeve_id": r["sleeve_id"], "sleeve": r["sleeve"], "sleeve_colour": r["sleeve_colour"],
        "ai_share": _ai_share(r), "ai_share_set": r["ai_share"] is not None,
        "company": r["company"], "theme": r["theme"], "notes": r["notes"],
        "source": r["source"], "has_history": bool(key and mkt),
    }


#: FSCS deposit protection per person per banking licence, from 1 December 2025.
DEPOSIT_LIMIT = 120000.0


def platforms_summary(pos: list[dict] | None = None) -> list[dict]:
    pos = positions() if pos is None else pos
    limit_default = float(config.settings.get("fscs_limit") or 85000)
    out = []
    for p in db.rows("SELECT * FROM platforms ORDER BY sort, id"):
        mine = [x for x in pos if x["platform_id"] == p["id"]]
        invested = sum(x["value"] for x in mine if x["value"] is not None)
        unknown = sum(1 for x in mine if x["value"] is None)
        total = invested + (p["cash"] or 0.0)
        out.append({
            "id": p["id"], "name": p["name"], "provider": p["provider"], "wrapper": p["wrapper"],
            "flexible": bool(p["flexible"]), "holdings": len(mine), "invested": invested,
            "cash": p["cash"], "cash_as_of": p["cash_as_of"], "cash_source": p["cash_source"],
            "total": total, "unpriced": unknown,
            "limit": (None if p["provider"] == "card" else
                      p["limit_gbp"] or (DEPOSIT_LIMIT if p["provider"] == "bank" else limit_default)),
            "kind": {"bank": "bank", "card": "card"}.get(p["provider"], "platform"),
            "in_plan": bool(p["in_plan"]),
            "reported_total": p["reported_total"], "reported_at": p["reported_at"],
            "last_sync": p["last_sync"], "last_error": p["last_error"],
        })
    return out


def totals(pos: list[dict] | None = None) -> dict:
    pos = positions() if pos is None else pos
    plats = platforms_summary(pos)
    priced = [x for x in pos if x["value"] is not None]
    invested = sum(x["value"] for x in priced)
    # Cash in a bank account counts only if its "part of my plan" box is ticked;
    # otherwise it is reported beside the portfolio, never inside its percentages.
    cash_known = [p["cash"] for p in plats if p["cash"] is not None and p["in_plan"]]
    outside = [p for p in plats if not p["in_plan"]]
    # A card's balance is what is owed, kept as a negative number, so the sums below net
    # it off; it is reported on its own line as well so a debt is never hidden in a total.
    outside_known = [p["cash"] for p in outside if p["cash"] is not None and p["kind"] != "card"]
    owed_known = [-p["cash"] for p in plats if p["kind"] == "card" and p["cash"] is not None]
    cash = sum(cash_known) if cash_known else None
    with_cost = [x for x in priced if x["cost"] is not None]
    cost = sum(x["cost"] for x in with_cost)
    gain = sum(x["gain"] for x in with_cost)
    moved = [x for x in pos if x["day_change"] is not None and x["value"] is not None]
    changes = [x["day_change"] for x in moved]
    # Measured against what those same holdings were worth yesterday — not against the
    # whole portfolio, which would understate the move whenever some have no prices.
    yesterday = sum(x["value"] - x["day_change"] for x in moved)
    since = (dt.date.today() - dt.timedelta(days=365)).isoformat()
    divs = db.scalar("SELECT SUM(amount_gbp) FROM dividends WHERE paid_on>=?", (since,))
    total = invested + (cash or 0.0) if (priced or cash is not None) else None
    return {
        "total": total, "invested": invested if priced else None, "cash": cash,
        "holdings": len(pos), "unpriced": len(pos) - len(priced),
        "cost": cost if with_cost else None, "gain": gain if with_cost else None,
        "gain_pct": (gain / cost) if (with_cost and cost) else None,
        "cost_unknown": len(priced) - len(with_cost),
        "day_change": sum(changes) if changes else None,
        "day_pct": (sum(changes) / yesterday) if (changes and yesterday) else None,
        "dividends_12m": divs,
        "outside_cash": sum(outside_known) if outside_known else None,
        "owed": sum(owed_known) if owed_known else None,
        "outside_net": (sum(outside_known) - sum(owed_known)) if (outside_known or owed_known) else None,
        "outside_accounts": [{"name": p["name"], "cash": p["cash"], "kind": p["kind"]} for p in outside],
        "everything": ((total or 0.0) + sum(outside_known) - sum(owed_known))
                      if (total is not None or outside_known or owed_known) else None,
        "platforms": plats,
    }


# ---------------------------------------------------------------------------- history

def take_snapshot():
    """Today's value, kept, so a real history accumulates from the first day onwards."""
    t = totals()
    if t["total"] is None:
        return None
    detail = {p["name"]: round(p["total"], 2) for p in t["platforms"]}
    from . import allocation
    view = allocation.view(positions(), t)
    detail["_sleeves"] = {r["name"]: round(r["actual"], 2) for r in view["sleeves"]}
    with db.tx() as c:
        c.execute("INSERT INTO snapshots(d,value,cash,cost,detail) VALUES(?,?,?,?,?) "
                  "ON CONFLICT(d) DO UPDATE SET value=excluded.value, cash=excluded.cash,"
                  " cost=excluded.cost, detail=excluded.detail",
                  (db.today(), round(t["total"], 2), t["cash"], t["cost"], json.dumps(detail)))
    return t["total"]


def snapshots() -> list[tuple[str, float]]:
    return [(r["d"], r["value"]) for r in db.rows("SELECT d, value FROM snapshots ORDER BY d")]


def money_in() -> list[tuple[str, float]]:
    """Running total of what has been paid in, less what has been taken out."""
    rows = db.rows("SELECT happened_on AS d, SUM(amount_gbp) AS a FROM cash_moves "
                   "WHERE kind IN ('DEPOSIT','WITHDRAWAL','TRANSFER') GROUP BY happened_on ORDER BY d")
    out, run = [], 0.0
    for r in rows:
        run += r["a"] or 0.0
        out.append((r["d"], round(run, 2)))
    return out


def backdated(days: int = 5 * 365, pos: list[dict] | None = None) -> dict:
    """Today's holdings, valued at every past date we have prices for.

    Not your account's history — what the portfolio you hold *now* would have been
    worth. That is the useful question for risk: "how did this mix behave in 2022?"
    Cash is held flat. Holdings without price history are left out, and the share of
    today's value that *is* covered comes back with the series, so the chart can say so.
    """
    pos = positions() if pos is None else pos
    start = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    series, covered, missing = [], 0.0, []
    flat = sum(x["value"] for x in pos if x["value_source"] == "at-cost")
    covered += flat
    for x in pos:
        if x["value_source"] == "at-cost":
            continue                           # held flat, like cash
        if not x["market_symbol"] or x["value"] is None:
            if x["value"] is not None:
                missing.append(x["name"])
            continue
        pts = store.gbp_points(store.sec_key(x["market_symbol"]), start)
        if len(pts) < 20:
            missing.append(x["name"])
            continue
        # Scale so the series ends at today's actual value — keeps broker-valued
        # holdings consistent with the headline figure.
        scale = x["value"] / pts[-1][1] if pts[-1][1] else 0
        series.append({d: v * scale for d, v in pts})
        covered += x["value"]
    invested = sum(x["value"] for x in pos if x["value"] is not None)
    if not series:
        return {"points": [], "coverage": 0.0, "missing": missing}
    all_days = sorted(set().union(*[s.keys() for s in series]))
    last_seen = [None] * len(series)
    out = []
    for d in all_days:
        total = 0.0
        ok = True
        for i, s in enumerate(series):
            if d in s:
                last_seen[i] = s[d]
            if last_seen[i] is None:
                ok = False                        # this holding has no price yet
                break
            total += last_seen[i]
        if ok:
            out.append((d, round(total + flat, 2)))
    return {"points": out, "coverage": (covered / invested) if invested else 0.0,
            "missing": missing, "worst": mathx.max_drawdown(out)}


def dividends_by_month(months: int = 24) -> list[dict]:
    start = (dt.date.today().replace(day=1) - dt.timedelta(days=31 * (months - 1))).replace(day=1)
    rows = db.rows("SELECT substr(paid_on,1,7) AS m, SUM(amount_gbp) AS a FROM dividends "
                   "WHERE paid_on>=? GROUP BY m ORDER BY m", (start.isoformat(),))
    have = {r["m"]: r["a"] for r in rows}
    out, d = [], start
    while d <= dt.date.today():
        m = d.strftime("%Y-%m")
        out.append({"month": m, "amount": round(have.get(m, 0.0), 2)})
        d = (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    return out
