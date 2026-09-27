"""How much of the portfolio rides on AI, and what a fall would cost in pounds.

Exposure is **look-through**: a single company counts in full if it is AI-linked, and a
fund counts for the share of it that is — an S&P 500 fund is partly AI because Nvidia,
Microsoft, Alphabet and friends are some of its biggest holdings. Allan's own review
found true AI and tech exposure of 36% when direct positions alone suggested far less;
that gap is the reason this module exists.

The share for each holding comes from the person, not from here: fund make-ups change
monthly and this app has no trustworthy free source for them. A holding whose share
nobody has set is counted separately and named, never assumed to be zero.
"""

from __future__ import annotations

#: Context for the stress screen. Well-documented history, kept deliberately short.
DOTCOM = ("From March 2000 to October 2002 the Nasdaq-100 fell more than 80% and the "
          "S&P 500 nearly half. The Nasdaq Composite didn't get back to its 2000 peak "
          "until 2015.")


def exposure(pos: list[dict], totals: dict) -> dict:
    total = totals.get("total") or 0.0
    priced = [x for x in pos if x["value"] is not None]
    unknown = [x for x in priced if x["ai_share"] is None]
    rows = []
    ai_value = 0.0
    for x in priced:
        if x["ai_share"] is None:
            continue
        v = x["value"] * x["ai_share"] / 100
        ai_value += v
        if v > 0:
            rows.append({"name": x["name"], "platform": x["platform"], "value": x["value"],
                         "share": x["ai_share"], "ai_value": v, "instrument_id": x["instrument_id"]})
    # The same shares held on two platforms are one exposure.
    merged: dict[int, dict] = {}
    for r in rows:
        m = merged.setdefault(r["instrument_id"], dict(r, value=0.0, ai_value=0.0, platforms=[]))
        m["value"] += r["value"]
        m["ai_value"] += r["ai_value"]
        m["platforms"].append(r["platform"])
    top = sorted(merged.values(), key=lambda r: r["ai_value"], reverse=True)
    return {
        "total": total, "ai_value": ai_value,
        "ai_pct": (ai_value / total) if total else None,
        "unknown": [{"name": x["name"], "value": x["value"], "instrument_id": x["instrument_id"]}
                    for x in unknown],
        "unknown_value": sum(x["value"] for x in unknown),
        "top": top[:14],
    }


def scenario(exp: dict, totals: dict, ai_fall: float, other_fall: float) -> dict:
    """What the portfolio would be worth if AI-linked holdings fell by `ai_fall` and
    everything else invested fell by `other_fall` (fractions). Cash stays put."""
    total = totals.get("total") or 0.0
    cash = totals.get("cash") or 0.0
    invested = total - cash
    ai = exp["ai_value"]
    other = max(0.0, invested - ai)
    loss_ai = ai * ai_fall
    loss_other = other * other_fall
    after = total - loss_ai - loss_other
    return {"before": total, "after": after, "loss": loss_ai + loss_other,
            "loss_pct": ((loss_ai + loss_other) / total) if total else None,
            "loss_ai": loss_ai, "loss_other": loss_other, "ai": ai, "other": other,
            "cash": cash, "unknown_value": exp["unknown_value"]}
