"""The indices and gauges worth watching for this kind of portfolio.

Each entry says what the thing is and why it matters to somebody holding a long-term,
growth-tilted ISA — in words a family member can follow. `sources` are tried in
order; the first that answers is used and the chart says which one it was.

`sleeve_words` links an index to the sleeves it stands for, matched against sleeve
names. It is deliberately loose: it answers "how much of me moves with this?", not
"what is my exact exposure", and the screen words it that way.
"""

from __future__ import annotations

REFERENCE: dict[str, dict] = {
    # ------------------------------------------------------------ world markets
    "SP500": dict(
        label="S&P 500", unit="pts", group="markets",
        sources=[("yahoo", "^GSPC"), ("fred", "SP500")],
        sleeve_words=["global", "core", "index", "us "],
        blurb="The 500 largest US companies, weighted by size.",
        why="The US is well over half of the world's stock markets by value, so this is "
            "the biggest single driver of any global index fund."),
    "WORLD": dict(
        label="FTSE All-World (in £)", unit="£", group="markets",
        sources=[("yahoo", "VWRL.L")],
        sleeve_words=["global", "core", "index"],
        blurb="Vanguard's FTSE All-World fund, used as a stand-in for the whole world's "
              "stock market priced in pounds.",
        why="Close to what a 'global core' holding should do. If your core funds lag "
            "this badly, something about them is different from the market."),
    "FTSE100": dict(
        label="FTSE 100", unit="pts", group="markets",
        sources=[("yahoo", "^FTSE")],
        sleeve_words=["uk", "consumer", "financ", "energy"],
        blurb="The 100 largest companies listed in London — banks, oil, miners, "
              "medicines, drinks and tobacco.",
        why="Earns most of its money abroad and has little technology in it, so it "
            "often behaves differently from US and AI-heavy holdings."),
    "FTSE250": dict(
        label="FTSE 250", unit="pts", group="markets",
        sources=[("yahoo", "^FTMC")],
        sleeve_words=["uk"],
        blurb="The next 250 London-listed companies.",
        why="Much more tied to the UK economy itself than the FTSE 100 is."),
    "EM": dict(
        label="Emerging markets (in £)", unit="£", group="markets",
        sources=[("yahoo", "EMIM.L")],
        sleeve_words=["global", "core", "emerging"],
        blurb="iShares Core MSCI EM IMI, pound-priced class — China, India, Taiwan, "
              "Korea, Brazil and others.",
        why="Taiwan and Korea are home to the biggest chip makers, so even emerging "
            "markets carry a slice of the AI trade."),

    # ------------------------------------------------------------ AI and tech
    "NDX": dict(
        label="Nasdaq-100", unit="pts", group="ai",
        sources=[("yahoo", "^NDX"), ("fred", "NASDAQ100")],
        sleeve_words=["tech", " ai", "ai "],
        blurb="The 100 largest non-financial companies on the Nasdaq exchange.",
        why="Dominated by the big technology and AI names, so it moves first and "
            "furthest when feeling about AI changes."),
    "SOX": dict(
        label="Semiconductors (SOX)", unit="pts", group="ai",
        sources=[("yahoo", "^SOX")],
        sleeve_words=["tech", " ai", "ai ", "semi"],
        blurb="The PHLX Semiconductor index: 30 of the largest US-listed chip designers, "
              "makers and equipment suppliers.",
        why="Chips are what AI spending is spent on. This is the part of the market most "
            "directly tied to whether that spending keeps growing."),
    "NVDA": dict(
        label="Nvidia", unit="$", group="ai",
        sources=[("yahoo", "NVDA")],
        sleeve_words=["tech", " ai", "ai "],
        blurb="The largest seller of AI chips, and the company most identified with the "
              "AI boom.",
        why="It is also one of the biggest weights in US and world index funds, so it "
            "reaches you through your core funds as well as any direct holding."),
    "SMH": dict(
        label="Chip-stock fund (SMH)", unit="$", group="ai", hidden=True,
        sources=[("yahoo", "SMH")],
        blurb="VanEck Semiconductor ETF, used for the leadership ratio.",
        why=""),
    "SPY": dict(
        label="S&P 500 fund (SPY)", unit="$", group="ai", hidden=True,
        sources=[("yahoo", "SPY")],
        blurb="SPDR S&P 500 ETF, the denominator of the ratios.", why=""),
    "RSP": dict(
        label="Equal-weight S&P 500 fund (RSP)", unit="$", group="ai", hidden=True,
        sources=[("yahoo", "RSP")],
        blurb="Invesco S&P 500 Equal Weight ETF — every company the same size.", why=""),

    # ------------------------------------------------------------ sectors
    "HEALTH": dict(
        label="US healthcare", unit="$", group="sectors",
        sources=[("yahoo", "XLV")], sleeve_words=["health"],
        blurb="Health Care Select Sector SPDR — the large US drug, device and "
              "insurance companies.",
        why="Tends to be steadier than the market as a whole, because people need "
            "medicine whatever the economy does."),
    "INDUSTRIALS": dict(
        label="US industrials", unit="$", group="sectors",
        sources=[("yahoo", "XLI")], sleeve_words=["industr", "material"],
        blurb="Industrial Select Sector SPDR — machinery, transport, aerospace, "
              "building.",
        why="Rises and falls with the business cycle; freight companies in particular "
            "are an early read on it."),
    "FINANCIALS": dict(
        label="US financials", unit="$", group="sectors",
        sources=[("yahoo", "XLF")], sleeve_words=["financ", "bank"],
        blurb="Financial Select Sector SPDR — banks, insurers, and Berkshire Hathaway.",
        why="Banks earn more when interest rates are higher and suffer when loans "
            "go bad."),
    "STAPLES": dict(
        label="US consumer staples", unit="$", group="sectors",
        sources=[("yahoo", "XLP")], sleeve_words=["consumer", "staple"],
        blurb="Consumer Staples Select Sector SPDR — food, drink, household goods.",
        why="Things people keep buying in a downturn; usually falls less than the "
            "market in a sell-off."),
    "ENERGY": dict(
        label="US energy", unit="$", group="sectors",
        sources=[("yahoo", "XLE")], sleeve_words=["energy", "oil"],
        blurb="Energy Select Sector SPDR — oil and gas producers and services.",
        why="Moves mostly with the oil price, which is why it can rise when everything "
            "else falls, and the other way round."),
    "DEFENCE": dict(
        label="US aerospace & defence", unit="$", group="sectors",
        sources=[("yahoo", "ITA")], sleeve_words=["defen", "aerospace"],
        blurb="iShares U.S. Aerospace & Defense ETF.",
        why="Driven by government budgets and conflict more than the economy."),
    "PROPERTY": dict(
        label="US property", unit="$", group="sectors",
        sources=[("yahoo", "VNQ")], sleeve_words=["real", "property", "reit", "infra"],
        blurb="Vanguard Real Estate ETF — companies that own property and collect rent.",
        why="Borrow heavily, so they are sensitive to interest rates."),

    # ------------------------------------------------------------ real things
    "GOLD": dict(
        label="Gold", unit="$/oz", group="commodities",
        sources=[("yahoo", "GC=F")], sleeve_words=["commod", "gold", "metal", "real"],
        blurb="Gold futures, in dollars per ounce.",
        why="Often holds up when confidence in paper assets falls — though not in every "
            "sell-off, and not reliably."),
    "COPPER": dict(
        label="Copper", unit="$/lb", group="commodities",
        sources=[("yahoo", "HG=F")], sleeve_words=["commod", "metal", "industr", "material"],
        blurb="Copper futures, in dollars per pound weight.",
        why="A read on factory and building demand worldwide — and now on the power "
            "grids and data centres that AI needs."),
    "BRENT": dict(
        label="Brent crude oil", unit="$/bbl", group="commodities",
        sources=[("yahoo", "BZ=F")], sleeve_words=["energy", "oil", "commod"],
        blurb="The global oil price benchmark, in dollars a barrel.",
        why="Drives an energy sleeve directly and inflation everywhere else."),
    "GILTS": dict(
        label="UK government bonds", unit="£", group="rates",
        sources=[("yahoo", "IGLT.L")], sleeve_words=["gilt", "bond"],
        blurb="iShares Core UK Gilts ETF, priced in pounds.",
        why="Gilt prices rise when interest rates fall — often, but not always, when "
            "shares are falling."),

    # ------------------------------------------------------------ rates, money, fear
    "US10Y": dict(
        label="US 10-year interest rate", unit="%", group="rates",
        sources=[("fred", "DGS10")], sleeve_words=[],
        blurb="The yield on 10-year US government bonds.",
        why="Higher rates make profits far in the future worth less today, which weighs "
            "hardest on expensive growth and technology shares."),
    "UK10Y": dict(
        label="UK 10-year gilt yield", unit="%", group="rates",
        sources=[("fred", "IRLTLT01GBM156N")], sleeve_words=["gilt"],
        blurb="The yield on 10-year UK government bonds, as a monthly average.",
        why="What your gilts pay, and a gauge of UK inflation worries. Above about 5.5% gilts "
            "have tended to fall with shares rather than cushion them."),
    "CURVE": dict(
        label="Yield curve (10-year less 3-month)", unit="%", group="stress",
        sources=[("fred", "T10Y3M")], sleeve_words=[],
        blurb="The US 10-year government yield minus the 3-month one.",
        why="Below zero (inverted) has come before most US recessions, usually by a year or "
            "more, and the turn back up after a long inversion has tended to come nearer the start."),
    "SAHM": dict(
        label="Sahm recession indicator", unit="", group="stress",
        sources=[("fred", "SAHMREALTIME")], sleeve_words=[],
        blurb="How far US unemployment's 3-month average has risen above its low of the past year.",
        why="A rise of 0.5 points has marked the early months of every US recession since 1970. "
            "Monthly, so it lags a few weeks."),
    "FSI": dict(
        label="Financial stress index", unit="", group="stress",
        sources=[("fred", "STLFSI4")], sleeve_words=[],
        blurb="The St. Louis Fed's weekly blend of 18 market measures of strain.",
        why="Zero is average. Above zero means more strain than usual across rates, spreads and "
            "volatility together; above 1 has come only with real trouble."),
    "IGOAS": dict(
        label="Investment-grade credit spread", unit="%", group="stress",
        sources=[("fred", "BAMLC0A0CM")], sleeve_words=[],
        blurb="What solid US companies pay to borrow, over the government.",
        why="Moves with the junk-bond spread but starts from safer borrowers: a widening here "
            "means strain has reached companies that normally borrow easily."),
    "GBPUSD": dict(
        label="Pound in dollars", unit="$", group="rates",
        sources=[("yahoo", "GBPUSD=X"), ("fred", "DEXUSUK")], sleeve_words=[],
        blurb="How many US dollars one pound buys.",
        why="When the pound rises your US holdings are worth fewer pounds even if their "
            "dollar price hasn't moved — and the other way round."),
    "VIX": dict(
        label="Fear gauge (VIX)", unit="", group="stress",
        sources=[("fred", "VIXCLS"), ("yahoo", "^VIX")], sleeve_words=[],
        blurb="The options market's estimate of how much the S&P 500 will swing over "
              "the next month.",
        why="Below 20 is calm. Above 30 has historically meant genuine fear — it spikes "
            "during sell-offs rather than before them."),
    "HYOAS": dict(
        label="Credit stress (junk-bond spread)", unit="%", group="stress",
        sources=[("fred", "BAMLH0A0HYM2")], sleeve_words=[],
        blurb="The extra interest riskier US companies pay to borrow, over and above the "
              "government (ICE BofA US High Yield index).",
        why="Widens when lenders get nervous about companies paying their debts back. "
            "A share sell-off with calm credit markets is usually less serious than one "
            "where this is widening too."),
}

#: FX series: units of the currency per one pound.
FX_SOURCES = {
    "USD": [("yahoo", "GBPUSD=X"), ("fred", "DEXUSUK")],
    "EUR": [("yahoo", "GBPEUR=X"), ("fred_cross", "DEXUSUK/DEXUSEU")],
}


def fx_sources(ccy: str) -> list[tuple[str, str]]:
    return FX_SOURCES.get(ccy, [("yahoo", f"GBP{ccy}=X")])


def visible() -> list[str]:
    return [k for k, v in REFERENCE.items() if not v.get("hidden")]
