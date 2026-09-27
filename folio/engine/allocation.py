"""Sleeves: what you meant to hold against what you actually hold.

**How far is too far?** The tolerance for each sleeve follows the "5/25" rule used by
many planners: a sleeve has drifted when it is out by 5 percentage points, or by a
quarter of its own target, whichever is smaller. A 23% sleeve may wander between 18%
and 28%; a 2% sleeve only between 1.5% and 2.5%, because a quarter of a small target is
small. Any sleeve can have its own band instead.

Past half its band a sleeve is amber (drifting); past the whole band it is red.

**New money.** Selling inside an ISA costs no tax, but it does cost spreads and FX fees,
and it can mean trades across both platforms. Pointing new contributions at the
underweight sleeves corrects drift for free, so the calculator does that first.
"""

from __future__ import annotations

import re

from .. import db
from ..brokers import symbols

PALETTE = ["#2f5bd3", "#0f8b6d", "#b35c00", "#7b3fc4", "#0e7490", "#c0392b", "#8a6d00",
           "#3d7d2c", "#a3316f", "#4b5d73", "#1f8fbf", "#9a4d2e", "#5a4fcf", "#6b8e23"]
UNASSIGNED = "#a0a9b6"


#: A band can run from a tenth of a point to the whole portfolio (100: never drifts,
#: for a sleeve that holds what is on its way out).
BAND_MIN, BAND_MAX = 0.1, 100.0


def band_for(target: float, override: float | None = None) -> float:
    if override is not None:
        return max(0.1, float(override))
    return max(0.25, min(5.0, 0.25 * float(target or 0)))


def sleeves() -> list[dict]:
    out = db.rows("SELECT * FROM sleeves ORDER BY sort, id")
    for i, s in enumerate(out):
        s["colour"] = s["colour"] or PALETTE[i % len(PALETTE)]
    return out


def view(pos: list[dict], totals: dict) -> dict:
    """Every sleeve with its target, its actual share of the whole portfolio (cash
    included), its band and a status. Holdings not yet in a sleeve are a line of their
    own, so they can never quietly disappear from the percentages."""
    sl = sleeves()
    total = totals.get("total") or 0.0
    by_id = {s["id"]: s for s in sl}
    values = {s["id"]: 0.0 for s in sl}
    counts = {s["id"]: 0 for s in sl}
    unassigned = 0.0
    unassigned_n = 0
    for x in pos:
        if x["value"] is None:
            continue
        if x["sleeve_id"] in values:
            values[x["sleeve_id"]] += x["value"]
            counts[x["sleeve_id"]] += 1
        else:
            unassigned += x["value"]
            unassigned_n += 1
    cash = totals.get("cash") or 0.0
    cash_sleeve = next((s for s in sl if s["is_cash"]), None)
    if cash_sleeve:
        values[cash_sleeve["id"]] += cash
    rows = []
    for s in sl:
        v = values[s["id"]]
        actual = (v / total * 100) if total else 0.0
        band = band_for(s["target"], s["band"])
        drift = actual - s["target"]
        status = "ok" if abs(drift) <= band / 2 else ("amber" if abs(drift) <= band else "red")
        if not total:
            status = "none"
        rows.append({"id": s["id"], "name": s["name"], "target": s["target"], "actual": actual,
                     "value": v, "band": band, "band_custom": s["band"] is not None,
                     "drift": drift, "status": status, "holdings": counts[s["id"]],
                     "colour": s["colour"], "is_cash": bool(s["is_cash"]),
                     "ai_share": s["ai_share"],
                     "gap_value": (s["target"] / 100 * total - v) if total else None})
    extra = []
    if unassigned_n:
        extra.append({"id": None, "name": "Not in a sleeve yet", "target": 0.0,
                      "actual": (unassigned / total * 100) if total else 0.0,
                      "value": unassigned, "holdings": unassigned_n, "colour": UNASSIGNED,
                      "status": "unassigned"})
    if cash and not cash_sleeve:
        extra.append({"id": None, "name": "Cash (no cash sleeve)", "target": 0.0,
                      "actual": (cash / total * 100) if total else 0.0, "value": cash,
                      "holdings": 0, "colour": "#c8ced8", "status": "cash"})
    target_sum = sum(s["target"] for s in sl)
    return {"sleeves": rows, "extra": extra, "total": total,
            "target_sum": target_sum, "targets_add_up": abs(target_sum - 100) < 0.01,
            "in_band": sum(1 for r in rows if r["status"] == "ok"),
            "drifting": sum(1 for r in rows if r["status"] == "amber"),
            "outside": sum(1 for r in rows if r["status"] == "red")}


def holding_targets(pos: list[dict], total: float) -> list[dict]:
    """Each holding against its own target, with a band of a quarter of that target either
    side (a 4% holding may sit between 3% and 5%). Targets come from the plan, keyed by
    ticker, and are matched by ISIN, ticker or price symbol, so "BRK.B", "BRK-B" and a
    Trading 212 name all land on the same line. A target with nothing held says so."""
    targets = db.get_meta("holding_targets", {}) or {}
    if not targets:
        return []
    band = float(db.get_meta("holding_band", 0.25) or 0.25)
    got: dict[str, dict] = {k: {"value": 0.0, "names": set(), "held": False} for k in targets}
    for x in pos:
        keys = [symbols.plan_key(x["isin"]) if x["isin"] else None, symbols.plan_key(x["symbol"]),
                symbols.alias_key(re.sub(r"\.[A-Z]{1,2}$", "", x["market_symbol"] or ""))]
        hit = next((k for k in keys if k and k in targets), None)
        if hit:
            got[hit]["held"] = True
            got[hit]["names"].add(x["name"])
            got[hit]["value"] += x["value"] or 0.0
    rows = []
    for key, t in sorted(targets.items(), key=lambda kv: -kv[1]):
        g = got[key]
        actual = (g["value"] / total * 100) if total else None
        lo, hi = t * (1 - band), t * (1 + band)
        status = ("not held" if not g["held"] else "none" if actual is None
                  else "ok" if lo <= actual <= hi else "out")
        rows.append({"key": key, "name": ", ".join(sorted(g["names"])) or key, "target": t,
                     "actual": actual, "low": lo, "high": hi, "value": g["value"], "status": status})
    return rows


def new_money(amount: float, v: dict) -> list[dict]:
    """Split a contribution so the portfolio ends up as close to target as possible
    without selling anything: fill the biggest gaps first, and once every gap is filled
    share what is left by target."""
    amount = float(amount)
    if amount <= 0 or not v["sleeves"]:
        return []
    after = v["total"] + amount
    gaps = {r["id"]: max(0.0, r["target"] / 100 * after - r["value"]) for r in v["sleeves"]}
    need = sum(gaps.values())
    if need <= 0:
        split = {r["id"]: amount * r["target"] / 100 for r in v["sleeves"]}
    elif need >= amount:
        split = {k: amount * g / need for k, g in gaps.items()}
    else:
        spare = amount - need
        tsum = sum(r["target"] for r in v["sleeves"]) or 1
        split = {r["id"]: gaps[r["id"]] + spare * r["target"] / tsum for r in v["sleeves"]}
    out = []
    for r in v["sleeves"]:
        amt = split.get(r["id"], 0.0)
        new_pct = (r["value"] + amt) / after * 100 if after else 0
        out.append({"id": r["id"], "name": r["name"], "colour": r["colour"],
                    "amount": round(amt, 2), "from_pct": r["actual"], "to_pct": new_pct,
                    "target": r["target"]})
    return out


def waffle(v: dict) -> list[dict]:
    """A hundred squares, one per percent — shared out by the largest-remainder method
    so they always add up to exactly 100 however the percentages round."""
    parts = [(r["name"], r["colour"], r["actual"]) for r in v["sleeves"] + v["extra"]
             if r["actual"] > 0]
    if not parts:
        return []
    total = sum(p[2] for p in parts)
    raw = [(n, c, p / total * 100) for n, c, p in parts]
    whole = [int(x[2]) for x in raw]
    left = 100 - sum(whole)
    order = sorted(range(len(raw)), key=lambda i: raw[i][2] - whole[i], reverse=True)
    for i in order[:left]:
        whole[i] += 1
    cells = []
    for (n, c, p), k in zip(raw, whole):
        cells += [{"name": n, "colour": c}] * k
    return cells


# Words in an instrument's name that point at a kind of sleeve. A suggestion only —
# the app shows it, and nothing is assigned until somebody confirms.
_HINTS = [
    (("treasury bill", "t-bill", "uktb"), ("cash",)),
    (("gilt", "treasury", "government bond"), ("gilt", "bond")),
    (("money market", "cash fund", "liquidity"), ("cash",)),
    (("semiconductor", "robot", "automation", "technology", " tech", "nasdaq", "software",
      "artificial", " ai ", "cloud", "cyber", "alphabet", "microsoft", "nvidia", "meta platforms",
      "broadcom", "micron", "amazon", "cloudflare", "ouster"), ("tech", " ai", "ai ")),
    (("health", "pharma", "biotech", "medical", "novo nordisk", "astrazeneca", "bristol-myers",
      "pfizer", "smith & nephew"), ("health",)),
    (("gold", "silver", "copper", "commodit", "metal", "mining", "platinum", "uranium"),
     ("commod",)),
    (("property", "reit", "real estate", "infrastructure", "real asset", "timber"),
     ("real", "propert", "infrastruct")),
    (("defence", "defense", "aerospace", "bae systems", "rheinmetall"), ("defen",)),
    (("oil", "energy", "shell", "exxon", "natural gas", "petrol"), ("energy",)),
    (("bank", "financ", "insur", "berkshire", "lloyds", "barclays", "hsbc", "visa",
      "mastercard", "aviva"), ("financ",)),
    (("consumer", "diageo", "unilever", "tobacco", "retail", "drinks", "food", "brewer"),
     ("consumer",)),
    (("industr", "freight", "logistic", "xpo", "gxo", "rxo", "engineering", "materials",
      "chemical", "construction"), ("industr", "material")),
    (("emerging", " em "), ("emerging",)),
    (("dividend", "aristocrat", "equity income"), ("dividend",)),
    (("ftse 100", "ftse 250", "uk equity", "uk companies"), ("uk ",)),
    (("world", "global", "all-world", "s&p 500", "s&p500", "msci", "ftse all", "emerging",
      "small cap", "total market", "equal weight", "ftse 100", "ftse 250"),
     ("global", "core", "index")),
]


def suggest(name: str, sleeve_rows: list[dict]) -> int | None:
    text = f" {(name or '').lower()} "
    for words, targets in _HINTS:
        if any(w in text for w in words):
            for s in sleeve_rows:
                sname = f" {s['name'].lower()} "
                if any(t in sname for t in targets):
                    return s["id"]
    return None
