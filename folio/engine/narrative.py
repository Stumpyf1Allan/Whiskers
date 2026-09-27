"""The words under the charts: what each section is saying, in plain English.

Everything here is generated from the same numbers the screens show, by fixed rules,
so it can be checked against them. It describes what has already happened and never
guesses what happens next. Money amounts are wrapped in [[ ]] so the interface can blur
them when "Hide amounts" is on.
"""

from __future__ import annotations

import datetime as dt

STATE = {"green": "normal", "amber": "raised", "red": "high", "none": "not available"}
CALM = {
    "market": "World shares are above their long-term trend and within 10% of their high, "
              "with fear and credit stress low.",
    "economy": "No sign of a downturn building: the yield curve isn't inverted, US "
               "unemployment isn't rising and financial strain is at or below average.",
    "ai": "The AI trade's trend is intact, chip stocks and Nvidia are near their highs, and "
          "AI stocks are still keeping pace with the market.",
}


def _day(d: str | None) -> str:
    if not d:
        return "recently"
    x = dt.date.fromisoformat(d[:10])
    return f"{x.day} {x.strftime('%b')}"


def _money(v: float | None) -> str:
    return "[[£{:,.0f}]]".format(v) if v is not None else "an unknown amount"


def _updown(x: float | None) -> str:
    if x is None:
        return "unchanged"
    v = x * 100
    size = f"{abs(v):.0f}%" if abs(v) >= 10 else f"{abs(v):.1f}%"
    return f"up {size}" if v >= 0 else f"down {size}"


def _join(items: list[str]) -> str:
    items = [i for i in items if i]
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1] if items else ""


# ---------------------------------------------------------------------------- lights

def _heading(x: dict) -> str:
    return {"worsening": ", still getting worse", "improving": ", but improving"}.get(
        x.get("direction"), "")


def lights_story(lights: list[dict], group: str) -> str:
    known = [x for x in lights if x["level"] != "none"]
    if not known:
        return "No data yet for these lights."
    bad = [x for x in known if x["level"] in ("amber", "red")]
    if not bad:
        text = f"All {len(known)} lights are green. {CALM[group]}"
        worse = [x["title"] for x in known if x.get("direction") == "worsening"]
        if worse:
            text += f" Heading the wrong way over the past month: {_join(worse)}."
        return text
    parts = [f"{x['title']}: {x['level']} since {_day(x.get('since'))}{_heading(x)}" for x in bad]
    good = len(known) - len(bad)
    text = "; ".join(parts) + "."
    if good:
        text += f" The other {good} {'is' if good == 1 else 'are'} green."
    return text


def watch(market: dict, playbook: dict | None) -> dict:
    lights = market.get("lights", [])
    out = {g: lights_story([x for x in lights if x["group"] == g], g) for g in ("market", "economy", "ai")}
    if playbook:
        out["signals"] = signals_story(playbook)
    return out


def signals_story(pb: dict) -> str:
    tier = pb["tier"]
    text = f"{pb['firing']} of {pb['of']} firing, so your playbook reads {tier['label'].lower()}."
    firing = [r for r in pb["signals"] if r["firing"]]
    if firing:
        text += " Firing: " + "; ".join(
            f"{r['title']}" + (f" since {_day(r.get('since'))}" if r.get("since") else "") for r in firing) + "."
    unknown = [r["title"] for r in pb["signals"] if r["firing"] is None]
    if unknown:
        text += f" Not known yet: {_join(unknown)}."
    return text


# ---------------------------------------------------------------------------- Markets screen

def markets(series: list[dict], lights: list[dict]) -> dict:
    groups: dict[str, list] = {}
    for s in series:
        groups.setdefault(s["group"], []).append(s)
    out = {}
    for g, items in groups.items():
        if g == "rates":
            out[g] = _rates(items)
        elif g == "stress":
            out[g] = _stress([x for x in lights if x["group"] in ("market", "economy")
                              and x["key"] not in ("world_trend", "world_fall")])
        else:
            out[g] = _prices(items)
    return out


def _prices(items: list[dict]) -> str:
    have = [x for x in items if x.get("value") is not None and (x.get("changes") or {}).get("1y") is not None]
    if not have:
        return "No prices yet for this section."
    ranked = sorted(have, key=lambda x: x["changes"]["1y"], reverse=True)
    parts = []
    if len(ranked) >= 2:
        b, w = ranked[0], ranked[-1]
        parts.append(f"Over the past year {b['label']} has done best ({_updown(b['changes']['1y'])}) "
                     f"and {w['label']} worst ({_updown(w['changes']['1y'])}).")
    else:
        parts.append(f"{ranked[0]['label']} is {_updown(ranked[0]['changes']['1y'])} over the past year.")
    falls = sorted([x for x in have if (x.get("drawdown") or 0) >= 0.10], key=lambda x: -x["drawdown"])
    if falls:
        parts.append(" ".join(
            f"{x['label']} is {x['drawdown'] * 100:.0f}% below its high of the past year, "
            f"{'bear-market territory' if x['drawdown'] >= 0.2 else 'a correction'}." for x in falls[:3]))
    elif all(x.get("drawdown") is not None for x in have):
        parts.append("Everything here is within 10% of its high of the past year.")
    moves = [x for x in have if abs((x["changes"] or {}).get("1m") or 0) >= 0.05]
    if moves:
        parts.append("In the past month " + _join(
            [f"{x['label']} {'rose' if x['changes']['1m'] > 0 else 'fell'} "
             f"{abs(x['changes']['1m']) * 100:.0f}%" for x in moves[:4]]) + ".")
    else:
        parts.append("The past month was quiet here: nothing moved as much as 5%.")
    linked = {}
    for x in items:
        for s in x.get("linked") or []:
            if s.get("actual") is not None:
                linked[s["name"]] = s["actual"]
    if linked:
        parts.append("For you, this is what moves your " + _join(
            [f"{n} sleeve ({a:.1f}%)" for n, a in linked.items()]) + ".")
    return " ".join(parts)


def _rates(items: list[dict]) -> str:
    parts = []
    for x in items:
        v, ch = x.get("value"), (x.get("changes") or {}).get("1y")
        if v is None:
            continue
        if x.get("changes_in_points"):
            move = "" if ch is None else f", {'up' if ch > 0 else 'down'} {abs(ch):.2f} points on the year"
            parts.append(f"{x['label']}: {v:.2f}%{move}.")
        elif x["key"] == "GBPUSD":
            effect = (" That lowers the value in pounds of your dollar holdings." if (ch or 0) > 0.02 else
                      " That raises the value in pounds of your dollar holdings." if (ch or 0) < -0.02 else "")
            parts.append(f"The pound buys ${v:.2f}, {_updown(ch)} on the year.{effect}")
        else:
            parts.append(f"{x['label']} is {_updown(ch)} on the year.")
    return " ".join(parts) or "No readings yet for this section."


def _stress(lights: list[dict]) -> str:
    known = [x for x in lights if x["level"] != "none"]
    if not known:
        return "No readings yet for the stress gauges."
    raised = [x for x in known if x["level"] != "green"]
    text = f"{len(known) - len(raised)} of {len(known)} stress gauges read normal."
    if raised:
        text += " " + "; ".join(f"{x['title']}: {STATE[x['level']]} since {_day(x.get('since'))}{_heading(x)}"
                                for x in raised) + "."
    worse = [x["title"] for x in known if x["level"] == "green" and x.get("direction") == "worsening"]
    if worse:
        text += f" Normal but rising over the past month: {_join(worse)}."
    return text + (" Each has given false alarms before; read together, they show strain "
                   "building or easing rather than what happens next.")


# ---------------------------------------------------------------------------- Overview

def big_picture(market: dict, pb: dict | None, exp: dict, alloc: dict, totals: dict) -> dict:
    lights = market.get("lights", [])
    groups = market.get("groups", {})
    ai = f"The AI trade reads {groups.get('ai', {}).get('label', 'no data').lower()}. " + \
        lights_story([x for x in lights if x["group"] == "ai"], "ai")
    if pb:
        rows = {r["key"]: r for r in pb["signals"]}
        bits = []
        h = rows.get("hyperscalers")
        if h and h.get("value") is not None:
            bits.append(f"{h['value']:.0f} of 4 hyperscalers guiding capex flat or down")
        n = rows.get("nvda_dc")
        if n and n.get("value") is not None:
            bits.append(f"Nvidia's data-centre growth at {n['value']:.0f}%")
        m = rows.get("mag7")
        if m and m.get("value") is not None:
            bits.append(f"the Magnificent Seven at {m['value']:.1f}% of the S&P 500")
        if bits:
            fired = sum(1 for r in pb["signals"] if r["group"] == "ai" and r["firing"])
            ai += f" Your AI signals: {_join(bits)} ({fired} of 3 firing)."
    mk = f"Markets in general read {groups.get('market', {}).get('label', 'no data').lower()}. " + \
        lights_story([x for x in lights if x["group"] == "market"], "market") + " The economy: " + \
        lights_story([x for x in lights if x["group"] == "economy"], "economy")
    if pb:
        mk += f" Your eight signals: {pb['firing']} of {pb['of']} firing ({pb['tier']['label'].lower()})."
    parts = []
    if exp.get("ai_pct") is not None:
        top = [t["name"] for t in exp.get("top", [])[:3]]
        parts.append(f"About {exp['ai_pct'] * 100:.0f}% of your money ({_money(exp['ai_value'])}) rides "
                     f"on AI" + (f", most of it through {_join(top)}." if top else "."))
    lad = (pb or {}).get("ladder") or {}
    if lad.get("drop") is not None:
        rung = next((r for r in lad["rungs"] if r.get("active")), None)
        parts.append(f"Your holdings are {lad['drop']:.1f}% below their high of {_day(lad.get('high_on'))}"
                     + (f", so your ladder says: {rung['text'][0].lower() + rung['text'][1:]}." if rung else "."))
    outside = [r for r in alloc.get("sleeves", []) if r["status"] == "red"]
    if outside:
        far = max(outside, key=lambda r: abs(r["drift"]))
        parts.append(f"{len(outside)} sleeve{'s are' if len(outside) != 1 else ' is'} outside "
                     f"{'their' if len(outside) != 1 else 'its'} band, furthest {far['name']} at "
                     f"{far['actual']:.1f}% against {far['target']:g}%.")
    for p in totals.get("platforms", []):
        if p.get("kind") == "platform" and p.get("limit") and p["total"] > p["limit"]:
            parts.append(f"{p['name']} is {_money(p['total'] - p['limit'])} over its protection limit.")
    parts.append("None of this predicts what markets do next: it describes what has already "
                 "happened, measured against your own plan.")
    return {"ai": ai, "markets": mk, "portfolio": " ".join(parts)}
