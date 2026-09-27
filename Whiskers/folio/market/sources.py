"""Where prices come from, and how each source's reply is read.

Every source returns the same shape — {"points": [(date, close), ...], "currency",
"name", "live", "live_at"} — with pence already turned into pounds, so nothing
downstream has to know which feed a number came from.

Checked in September 2026:

* **Yahoo** `/v8/finance/chart` — the only free source covering London ETFs and trusts,
  US shares and world indices together. Needs no key or cookie. The `/v7/quote`
  endpoint that Mittens & Pence tries first has answered 401 since January 2026, so it
  is not used here at all. Unofficial: it can change or throttle without notice.
* **FRED** (Federal Reserve Bank of St Louis) `fredgraph.csv` — official and keyless.
  The backbone for the market-stress readings: VIX, credit spreads, US rates, the
  pound–dollar rate, and the S&P 500 and Nasdaq-100 themselves. If Yahoo is down, the
  most important warning lights still work.
* **Stooq** — required an API key from April 2026 (obtained through a captcha on their
  site). Used only if one has been pasted into Settings.

The parse_* functions take the raw reply and nothing else, so the tests can feed them
recorded payloads without touching the network.
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import json
import math
import random
import urllib.parse

from .. import config, net

YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range={rng}&interval=1d"
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
STOOQ_CSV = "https://stooq.com/q/d/l/?s={sym}&i=d&apikey={key}"


class SourceError(Exception):
    pass


def normalise(value: float | None, currency: str | None) -> tuple[float | None, str | None]:
    """1723.5 GBp -> (17.235, 'GBP'). Leaves everything else alone."""
    if currency in config.MINOR_UNIT_CURRENCIES:
        major, div = config.MINOR_UNIT_CURRENCIES[currency]
        return (None if value is None else value / div), major
    return value, currency


def _clean(points: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """Sorted, one value per date (the last one wins), no NaNs, no non-positive prices
    that would wreck a percentage."""
    seen: dict[str, float] = {}
    for d, v in points:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            continue
        seen[d] = float(v)
    return sorted(seen.items())


# ---------------------------------------------------------------------------- Yahoo

def parse_yahoo_chart(payload: dict) -> dict:
    chart = (payload or {}).get("chart") or {}
    if chart.get("error"):
        err = chart["error"]
        raise SourceError(err.get("description") or err.get("code") or "Yahoo reported an error")
    result = (chart.get("result") or [None])[0]
    if not result:
        raise SourceError("Yahoo sent back no data for that symbol")
    meta = result.get("meta") or {}
    raw_ccy = meta.get("currency")
    offset = int(meta.get("gmtoffset") or 0)
    stamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    pts = []
    for ts, c in zip(stamps, closes):
        if c is None:
            continue
        # The stamp is the session's opening moment in UTC. Shifting by the exchange's
        # own offset before taking the date stops a Tokyo or Sydney close landing on
        # the previous day — and stops London's summer-time sessions doing the same.
        day = dt.datetime.fromtimestamp(int(ts) + offset, dt.timezone.utc).date().isoformat()
        v, _ = normalise(float(c), raw_ccy)
        pts.append((day, v))
    live, ccy = normalise(meta.get("regularMarketPrice"), raw_ccy)
    live_at = None
    if meta.get("regularMarketTime"):
        live_at = dt.datetime.fromtimestamp(int(meta["regularMarketTime"]) + offset,
                                            dt.timezone.utc).replace(tzinfo=None) \
            .isoformat(sep=" ", timespec="minutes")
    return {"points": _clean(pts), "currency": ccy, "raw_currency": raw_ccy,
            "name": meta.get("longName") or meta.get("shortName"),
            "live": live, "live_at": live_at,
            "exchange": meta.get("exchangeName"), "kind": meta.get("instrumentType")}


def yahoo(symbol: str, rng: str = "5y") -> dict:
    url = YAHOO_CHART.format(sym=urllib.parse.quote(symbol, safe="^=-."), rng=rng)
    try:
        body = net.get(url, browser=True, timeout=20)
    except net.FetchError as e:
        if e.status == 404:
            raise SourceError(f"Yahoo doesn't recognise “{symbol}”.") from None
        if e.status == 429:
            hint = "" if net.have_browser_tls() else \
                " (the curl_cffi package is missing, which makes this far more likely)"
            raise SourceError("Yahoo is refusing requests from this computer for now"
                              f"{hint}. It usually clears within the hour.") from None
        raise SourceError(str(e)) from None
    try:
        return parse_yahoo_chart(json.loads(body))
    except ValueError:
        raise SourceError("Yahoo's reply wasn't readable") from None


# ---------------------------------------------------------------------------- FRED

def parse_fred_csv(text: str) -> list[tuple[str, float]]:
    """Two columns, date then value. The header was `DATE` until 2024 and is
    `observation_date` now; missing days are '.' or empty. Neither is assumed."""
    rdr = csv.reader(io.StringIO(text))
    header = next(rdr, None)
    if not header or len(header) < 2:
        raise SourceError("FRED sent back something that isn't a data file")
    pts = []
    for row in rdr:
        if len(row) < 2:
            continue
        d, v = row[0].strip(), row[1].strip()
        if not d or v in ("", "."):
            continue
        try:
            dt.date.fromisoformat(d)
            pts.append((d, float(v)))
        except ValueError:
            continue
    return _clean(pts)


def fred(series_id: str) -> dict:
    try:
        body = net.get(FRED_CSV.format(sid=urllib.parse.quote(series_id)), timeout=25)
    except net.FetchError as e:
        raise SourceError(f"FRED: {e}") from None
    text = body.decode("utf-8", "replace")
    if text.lstrip().startswith("<"):
        raise SourceError("FRED sent a web page instead of data — the series may have moved")
    return {"points": parse_fred_csv(text), "currency": None, "name": None,
            "live": None, "live_at": None}


# ---------------------------------------------------------------------------- Stooq

def parse_stooq_csv(text: str) -> list[tuple[str, float]]:
    rdr = csv.DictReader(io.StringIO(text))
    pts = []
    for row in rdr:
        d, c = (row.get("Date") or "").strip(), (row.get("Close") or "").strip()
        try:
            pts.append((dt.date.fromisoformat(d).isoformat(), float(c)))
        except ValueError:
            continue
    return _clean(pts)


def stooq_symbol(yahoo_symbol: str) -> tuple[str, str | None] | None:
    """Only the translations that are certain: US shares, and the indices below."""
    s = yahoo_symbol.upper()
    fixed = {"^GSPC": ("^spx", None), "^NDX": ("^ndx", None), "^FTSE": ("^ukx", None)}
    if s in fixed:
        return fixed[s]
    if s.isalpha() and len(s) <= 5:
        return (s.lower() + ".us", "USD")
    if "-" in s and s.replace("-", "").isalpha():          # BRK-B
        return (s.lower().replace("-", ".") + ".us", "USD")
    return None


def stooq(yahoo_symbol: str, key: str) -> dict:
    mapped = stooq_symbol(yahoo_symbol)
    if not mapped:
        raise SourceError(f"No certain Stooq name for {yahoo_symbol}")
    sym, ccy = mapped
    try:
        body = net.get(STOOQ_CSV.format(sym=urllib.parse.quote(sym), key=urllib.parse.quote(key)))
    except net.FetchError as e:
        raise SourceError(f"Stooq: {e}") from None
    text = body.decode("utf-8", "replace")
    if "apikey" in text.lower() and "Date" not in text[:40]:
        raise SourceError("Stooq wants a (new) API key — see Settings → Data sources")
    return {"points": parse_stooq_csv(text), "currency": ccy, "name": None,
            "live": None, "live_at": None}


# ---------------------------------------------------------------------------- synthetic

#: Rough starting levels, so synthetic charts look like the thing they stand in for.
_SYNTH_LEVEL = {"^VIX": 17, "VIXCLS": 17, "BAMLH0A0HYM2": 3.4, "DGS10": 4.2,
                "GBPUSD=X": 1.30, "DEXUSUK": 1.30, "GBPEUR=X": 1.17, "DEXUSEU": 1.10}


def synthetic(ident: str, days: int = 1400, anchor: float | None = None) -> dict:
    """A deterministic made-up series, for tests and screenshots only.

    Never reachable unless WHISKERS_FAKE_MARKET=1 is set, and the interface shows a
    red banner whenever it is — made-up prices that look real are worse than none.
    """
    seed = int(hashlib.sha1(ident.encode()).hexdigest()[:8], 16)
    rnd = random.Random(seed)
    level = _SYNTH_LEVEL.get(ident)
    mean_revert = ident in ("^VIX", "VIXCLS", "BAMLH0A0HYM2", "DGS10")
    if level is None:
        level = 20 + rnd.random() * 400
    drift = 0.0002 + rnd.random() * 0.0005
    vol = 0.006 if ("=X" in ident or ident.startswith("DEX")) else 0.009 + rnd.random() * 0.014
    base = level
    # One late shock in every risky series, of a size that varies by name — so the
    # warning lights come out a mixture of colours rather than all the same.
    shock_at = days - 40 - rnd.randint(0, 160)
    shock = -(0.02 + rnd.random() * 0.30)
    end = dt.date.today()
    pts = []
    d = end - dt.timedelta(days=int(days * 7 / 5) + 10)
    v = level * (0.55 + rnd.random() * 0.2) if not mean_revert else level
    i = 0
    while d <= end:
        if d.weekday() < 5:
            if mean_revert:
                v += (base - v) * 0.04 + rnd.gauss(0, base * 0.05)
                if shock_at <= i < shock_at + 25:
                    v += base * 0.06
                v = max(base * 0.4, v)
            else:
                step = drift + rnd.gauss(0, vol)
                if shock_at <= i < shock_at + 30:
                    step += shock / 30
                v *= math.exp(step)
            pts.append((d.isoformat(), round(v, 4)))
            i += 1
        d += dt.timedelta(days=1)
    if anchor and pts and pts[-1][1]:
        k = anchor / pts[-1][1]                   # end where the caller says it should
        pts = [(d, round(v * k, 4)) for d, v in pts]
    return {"points": pts, "currency": None, "name": None,
            "live": pts[-1][1], "live_at": pts[-1][0] + " 16:30"}
