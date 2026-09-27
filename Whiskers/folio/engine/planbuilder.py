"""A starting plan from a few questions, for people who don't have one yet.

Built from well-regarded research rather than hunches, and it says which piece of
research each figure comes from (SOURCES). The steps:

1. How much to hold in shares is the LOWER of two figures, as the FCA expects advisers
   to treat them: what the person is *willing* to take (three questions on how they would
   react, their experience, and what they prefer), and what they are *able* to take
   (their capacity for loss: when they need the money, whether guaranteed income covers
   their essentials). A high capacity never pushes someone past what they are willing to
   take. [FCA FG11/05]
2. Capacity follows the lifecycle "glide path" used by target-date funds: about 90%
   shares when retirement is 25 or more years away, falling to about 50% at retirement.
   [Vanguard] Very long horizons may justify all shares, which recent research supports
   and others dispute. [Anarkulova, Cederburg & O'Doherty; Asness]
3. People already drawing an income use Morningstar's bucket approach: one to two years
   of withdrawals in cash, five to eight years in high-quality bonds, the rest in shares,
   so a fall never forces a sale. [Benz/Morningstar; Evensky] Above about 4% a year, the
   plan warns: 3.9% is the highest starting rate research finds safe over 30 years.
   [Morningstar 2025]
4. Around and in retirement, part of the bond holding is index-linked gilts, which protect
   against inflation directly; gold is kept as an optional theme, because over practical
   horizons it is an unreliable inflation hedge. [Vanguard; Erb & Harvey]
5. Shares are mostly one global index fund, the usual core, holding thousands of companies
   in many countries: diversifying across countries mattered more than holding bonds in
   the lifecycle research. Chosen themes get small satellite slices.

It is a starting point, not advice: it names kinds of investment (sleeves), never
particular funds, and every figure can be changed in Settings.
"""

from __future__ import annotations

QUESTIONS = [
    {"id": "age", "text": "How old are you?", "kind": "one", "options": [
        ["under40", "Under 40"], ["40to54", "40 to 54"], ["55to64", "55 to 64"], ["65plus", "65 or over"]]},
    {"id": "horizon", "text": "When will you start spending this money?", "kind": "one", "options": [
        ["now", "I'm already spending from it"], ["under5", "Within 5 years"], ["5to10", "In 5 to 10 years"],
        ["10to20", "In 10 to 20 years"], ["over20", "More than 20 years away"]]},
    {"id": "withdraw", "text": "Once you draw on it, roughly how much a year will you take out, as a share of the pot?",
     "kind": "one", "options": [["na", "I won't be drawing on it"], ["2", "About 2%"], ["3", "About 3%"],
                                ["4", "About 4%"], ["5", "5% or more"]]},
    {"id": "guaranteed", "text": "In retirement, how much of your essential spending will guaranteed income "
                                 "cover (State Pension, a final-salary or career-average pension such as the "
                                 "NHS scheme, an annuity)?", "kind": "one", "options": [
        ["most", "Most or all of it"], ["half", "About half"], ["little", "Little or none"], ["unsure", "Not sure"]]},
    {"id": "fall", "text": "If your investments fell by a third within a year, what would you most likely do?",
     "kind": "one", "options": [
        ["sell", "Sell to stop the losses"], ["worry", "Worry, but hold on"],
        ["hold", "Hold on without much worry"], ["buy", "Buy more while prices are low"]]},
    {"id": "experience", "text": "How long have you been invested through ups and downs?", "kind": "one", "options": [
        ["new", "I'm new to it"], ["few", "A few years"], ["long", "Ten years or more, including a big fall"]]},
    {"id": "prefer", "text": "Which would you rather have?", "kind": "one", "options": [
        ["steady", "Small, steady growth"], ["balanced", "Better growth, with some ups and downs"],
        ["growth", "The best long-run growth, accepting big swings"]]},
    {"id": "emergency", "text": "Do you have savings outside this, covering at least three months of spending?",
     "kind": "one", "options": [["yes", "Yes"], ["no", "Not yet"]]},
    {"id": "platforms", "text": "Which platforms do you use?", "kind": "many", "options": [
        ["freetrade", "Freetrade"], ["trading212", "Trading 212"]]},
    {"id": "buffer", "text": "How close to the \u00a385,000 FSCS protection limit should each platform get?",
     "kind": "one", "options": [
        ["85000", "Right up to \u00a385,000"], ["78000", "Keep about \u00a37,000 spare, as prices move"]]},
    {"id": "style", "text": "How hands-on do you want to be?", "kind": "one", "options": [
        ["simple", "Keep it simple: mostly one or two index funds"],
        ["mixed", "Index funds plus a few themes I believe in"],
        ["hands", "Hands-on: more themes and some single companies"]]},
    {"id": "themes", "text": "Which themes would you like a stake in? (Pick any, or none.)", "kind": "many",
     "options": [["tech", "Technology & AI"], ["health", "Healthcare"], ["energy", "Energy"],
                 ["defence", "Defence"], ["commod", "Commodities & gold"],
                 ["real", "Property & infrastructure"], ["em", "Emerging markets"],
                 ["uk", "UK companies"], ["income", "Dividend income"]]},
    {"id": "ai_cap", "text": "At most, how much of your money should ride on AI, counting what your funds hold?",
     "kind": "one", "options": [["20", "20%"], ["30", "30%"], ["40", "40%"], ["none", "No limit"]]},
]

SOURCES = [
    ["Vanguard: target-date glide path (90% shares at 25, 50% at 65, 30% by 72)",
     "https://institutional.vanguard.com/content/dam/inst/iig-transformation/insights/pdf/2025/231657-02_TDF_PTDF_OTH-TRIGT-Research.pdf"],
    ["Anarkulova, Cederburg & O'Doherty: Beyond the Status Quo (the case for global all-equity)",
     "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4590406"],
    ["Morningstar: Should long-term investors be 100% in equities? (including Asness's critique)",
     "https://www.morningstar.com/stocks/should-long-term-investors-be-100-equities"],
    ["Pfau & Kitces: Reducing retirement risk with a rising equity glide path (the \u2018bond tent\u2019)",
     "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2324930"],
    ["Morningstar (Christine Benz): the bucket approach to retirement portfolios",
     "https://www.morningstar.com/retirement/take-this-simple-step-runup-retirement"],
    ["Morningstar: What's a safe retirement withdrawal rate for 2026? (3.9% over 30 years)",
     "https://www.morningstar.com/retirement/whats-safe-retirement-withdrawal-rate-2026"],
    ["FCA FG11/05: establishing the risk a customer is willing and able to take",
     "https://www.fca.org.uk/publication/finalised-guidance/fsa-fg11-05.pdf"],
    ["Ibbotson, Milevsky, Chen & Zhu: Lifetime Financial Advice (human capital and pensions)",
     "https://rpc.cfainstitute.org/research/foundation/2007/lifetime-financial-advice-human-capital-asset-allocation-and-insurance"],
    ["Erb & Harvey: The Golden Dilemma (gold as an inflation hedge)", "https://www.nber.org/papers/w18706"],
]

#: Sleeve name and its default AI share (None: set per holding, as funds differ).
THEMES = {
    "tech": ("Technology & AI", 100), "health": ("Healthcare", 0), "energy": ("Energy", 0),
    "defence": ("Defence", 0), "commod": ("Commodities & gold", 0),
    "real": ("Property & infrastructure", 0), "em": ("Emerging markets", None),
    "uk": ("UK companies", None), "income": ("Dividend income", None),
}
#: Share of the equity part given to themes, and the most any one theme gets.
SATELLITES = {"simple": (0.10, 3.0), "mixed": (0.25, 8.0), "hands": (0.40, 12.0)}
GLIDE = {"over20": 90, "10to20": 80, "5to10": 60, "under5": 35}


def _half(x: float) -> float:
    return round(x * 2) / 2


def willingness(a: dict) -> float:
    """0 to 1, from three questions, weighted towards how someone says they would react:
    that is what decides whether a plan survives its first bad year."""
    fall = {"sell": 0.0, "worry": 0.33, "hold": 0.67, "buy": 1.0}.get(a.get("fall"), 0.67)
    exp = {"new": 0.0, "few": 0.5, "long": 1.0}.get(a.get("experience"), 0.5)
    pref = {"steady": 0.0, "balanced": 0.5, "growth": 1.0}.get(a.get("prefer"), 0.5)
    return 0.5 * fall + 0.2 * exp + 0.3 * pref


def build(a: dict) -> dict:
    why = []
    horizon = a.get("horizon") if a.get("horizon") in (*GLIDE, "now") else "over20"
    drawing = horizon == "now"
    rate = {"2": 2.0, "3": 3.0, "4": 4.0, "5": 5.0}.get(a.get("withdraw"))
    style = a.get("style") if a.get("style") in SATELLITES else "mixed"
    themes = [t for t in (a.get("themes") or []) if t in THEMES]
    older = a.get("age") in ("55to64", "65plus")

    # 1. What they are able to take: the glide path, or buckets once drawing.
    if drawing:
        r = rate or 4.0
        cash = max(4.0, 2 * r)                       # one to two years of withdrawals
        bonds = min(60.0, 7.5 * r)                   # five to eight years more
        able = 100.0 - cash - bonds
        why.append(f"You are drawing about {r:g}% a year, so the plan follows the bucket approach: about "
                   f"two years of withdrawals ({cash:g}%) in cash and several more years' worth in gilts and "
                   f"bonds, so a fall in shares never forces a sale.")
        if r >= 5:
            why.append("Taking 5% or more a year is above what research finds sustainable: Morningstar's "
                       "2025 study puts the highest safe starting rate at 3.9% for a 30-year retirement. "
                       "Spending flexibly (less after bad years) is the usual way to afford more.")
    else:
        able = float(GLIDE[horizon])
        cash = bonds = None
        why.append({"over20": "With more than 20 years to go, the plan starts where target-date funds do, "
                              "at about 90% in shares.",
                    "10to20": "With 10 to 20 years to go, about 80% in shares, as target-date funds hold "
                              "at that stage.",
                    "5to10": "With 5 to 10 years to go, shares come down towards the 50% target-date funds "
                             "hold at retirement, to protect the years when a fall does most harm.",
                    "under5": "Money needed within five years has little time to recover from a fall, so "
                              "most of it is kept out of shares."}[horizon])
    g = a.get("guaranteed")
    if g == "most":
        able += 10
        why.append("Guaranteed income covers most of your essentials, so this pot can take more risk: "
                   "a secure pension behaves like a large bond holding.")
    elif g == "little":
        able -= 5
    able = max(10.0, min(100.0, able))

    # 2. What they are willing to take. The plan uses the lower of the two.
    w = willingness(a)
    willing = 30.0 + 70.0 * w
    equity = _half(min(able, willing))
    if willing < able:
        why.append(f"Your answers on how you'd feel in a fall put you at about {willing:.0f}% in shares at "
                   f"most. The plan never asks you to take more risk than you're willing to, even when your "
                   f"situation could carry it.")
    if equity >= 95:
        why.append("At this horizon, research on 39 countries found a global all-share portfolio built the "
                   "most wealth; other researchers dispute how far that applies. The plan keeps a little cash.")
        equity = min(equity, 97.0)

    # 3. The safe part: cash first, then gilts, with inflation protection nearer retirement.
    safe = 100.0 - equity
    if cash is None:
        cash = max(3.0, _half(0.25 * safe))
    cash = min(cash, safe)
    if a.get("emergency") == "no":
        cash += 5
        equity = max(0.0, equity - 5)
        why.append("There are no emergency savings yet, so 5 extra points are kept as cash here. Better "
                   "still is three months' spending in an easy-access savings account first.")
    rest = max(0.0, 100.0 - equity - cash)
    linked = _half(rest * 0.35) if (drawing or older or horizon in ("under5", "5to10")) and rest >= 4 else 0.0
    gilts = _half(rest - linked)
    if linked:
        why.append("Part of the safe money is index-linked gilts, which rise with inflation: the job gold "
                   "is often given but, over practical horizons, does unreliably.")

    # 4. Shares: a global core, with themes as small satellites.
    share_of_eq, cap = SATELLITES[style]
    if drawing:
        share_of_eq, cap = min(share_of_eq, 0.15), min(cap, 5.0)
    each = _half(min(cap, equity * share_of_eq / len(themes))) if themes else 0.0
    core = equity - each * len(themes)
    why.append(f"{core:g}% goes to a global index fund: one fund holding thousands of companies across many "
               f"countries, the usual core.")
    if themes:
        why.append(f"Each theme you picked gets {each:g}%: small enough that one going wrong doesn't sink the "
                   f"plan. The index already owns every theme in proportion; these add to it.")

    sleeves = [{"name": "Global core index", "target": core, "ai_share": None}]
    sleeves += [{"name": THEMES[t][0], "target": each, "ai_share": THEMES[t][1]} for t in themes]
    if gilts > 0:
        sleeves.append({"name": "Gilts and bonds", "target": gilts, "ai_share": 0})
    if linked > 0:
        sleeves.append({"name": "Index-linked gilts", "target": linked, "ai_share": 0})
    sleeves.append({"name": "Cash", "target": cash, "ai_share": 0, "is_cash": True})
    sleeves = [s for s in sleeves if s["target"] > 0 or s.get("is_cash")]
    sleeves[0]["target"] = round(sleeves[0]["target"] + 100.0 - sum(s["target"] for s in sleeves), 2)

    rules = []
    if a.get("ai_cap") in ("20", "30", "40"):
        rules.append({"kind": "ai_cap", "trigger": float(a["ai_cap"]),
                      "note": f"Keep money riding on AI, counting what funds hold, under {a['ai_cap']}%."})
        why.append(f"A rule warns you if more than {a['ai_cap']}% of your money rides on AI. Set an AI share "
                   f"on each fund (Holdings) so it can count properly.")
    limit = 78000 if a.get("buffer") == "78000" else 85000
    platforms = []
    chosen = a.get("platforms") or []
    if "freetrade" in chosen:
        platforms.append({"name": "Freetrade ISA", "provider": "freetrade", "wrapper": "isa",
                          "flexible": False, "limit": limit})
    if "trading212" in chosen:
        platforms.append({"name": "Trading 212 ISA", "provider": "trading212", "wrapper": "isa",
                          "flexible": True, "limit": limit})
    crash = ("Spend from the Cash sleeve. After good years, top it up from shares; after bad years, "
             "top it up from gilts and leave shares to recover. Don't sell shares in a fall."
             if drawing else
             "Keep contributing as normal. Rebalance only when a sleeve leaves its band, using new "
             "money first. Don't sell in a fall.")
    why.append("This is a starting point from published research and common practice, not advice. Change "
               "any figure in Settings, Your plan, and pick your own funds for each sleeve.")
    plan = {"whiskers_plan": 1, "about": "Built from your answers to the plan questions.",
            "replace_sleeves": True, "sleeves": sleeves, "rules": rules, "platforms": platforms,
            "plans": {"crash": crash}}
    return {"plan": plan, "why": why, "growth": equity, "safe": 100.0 - equity,
            "willingness": round(w, 2), "sources": SOURCES}
