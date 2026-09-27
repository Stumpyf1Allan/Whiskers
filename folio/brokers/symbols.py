"""One company, three spellings.

Trading 212 writes `PCGHl_EQ` (the lower-case letter is the venue), Freetrade writes
`SN.` with a trailing full stop for some London tickers, and Yahoo wants `PCGH.L`,
`SN.L`, `BRK-B`. This module turns each broker's spelling into (symbol, exchange) and
then into the price feed's symbol, and it is the only place that knows the rules.

Where the rules run out — Ouster still trades at Trading 212 under its old SPAC ticker
`CLA` — the instrument's price symbol can be corrected by hand in the app, and the
correction sticks.
"""

from __future__ import annotations

import re

from .. import db
from . import tbills

T212_TICKER = re.compile(
    r"^(?P<base>[A-Z0-9._]+?)(?P<venue>[a-z])?(?:_(?P<country>[A-Z]{2}))?_EQ$")

T212_VENUE = {"l": "LSE", "a": "AMS", "d": "XETRA", "p": "PAR", "m": "MIL",
              "e": "MAD", "s": "SIX", "z": "SIX", "n": "US", "q": "US"}

YAHOO_SUFFIX = {"LSE": ".L", "XETRA": ".DE", "AMS": ".AS", "PAR": ".PA", "MIL": ".MI",
                "MAD": ".MC", "SIX": ".SW", "US": ""}

#: Share classes and duplicates that are one company for concentration purposes.
#: Anything else is linked by hand (or by an imported plan).
BUILTIN_COMPANIES = {"GOOGL": "Alphabet", "GOOG": "Alphabet",
                     "BRK-B": "Berkshire Hathaway", "BRK-A": "Berkshire Hathaway"}


def parse_t212(raw: str) -> tuple[str, str | None]:
    """'PCGHl_EQ' -> ('PCGH','LSE'); 'BRK_B_US_EQ' -> ('BRK-B','US');
    'BT_Al_EQ' -> ('BT.A','LSE')."""
    raw = (raw or "").strip()
    m = T212_TICKER.match(raw)
    if not m:
        return raw.replace("_EQ", ""), None
    base, venue, country = m.group("base"), m.group("venue"), m.group("country")
    if country == "US":
        return base.replace("_", "-"), "US"
    ex = T212_VENUE.get(venue) if venue else None
    return (base.replace("_", ".") if ex == "LSE" else base), ex


def exchange_from(venue: str | None, isin: str | None, currency: str | None) -> str | None:
    v = (venue or "").lower()
    if "london" in v or v == "lse":
        return "LSE"
    if any(w in v for w in ("nyse", "nasdaq", "new york", "bats", "cboe", "arca")):
        return "US"
    if "xetra" in v or "frankfurt" in v:
        return "XETRA"
    if "amsterdam" in v:
        return "AMS"
    if "paris" in v:
        return "PAR"
    p = (isin or "")[:2].upper()
    if p in ("GB", "IE", "JE", "GG", "IM", "LU"):
        return "LSE"            # UK shares, and UCITS funds as UK platforms buy them
    if p in ("US", "CA"):
        return "US"
    if p == "DE":
        return "XETRA"
    if p == "NL":
        return "AMS"
    if p == "FR":
        return "PAR"
    if currency in ("GBP", "GBX", "GBp"):
        return "LSE"
    if currency == "USD":
        return "US"
    return None


def market_symbol(symbol: str, exchange: str | None) -> str:
    s = (symbol or "").strip().upper()
    # Freetrade lists things with no exchange ticker (Treasury bills, for one) by ISIN.
    # No price feed knows an ISIN as a symbol, so don't ask one: 38 "GB00….L" lookups
    # failing on every refresh is what Allan's first run showed.
    if not s or tbills.is_isin(s):
        return ""
    if exchange == "LSE":
        return s.rstrip(".").replace(".", "-") + ".L"
    if exchange == "US" or exchange is None:
        return s.replace(".", "-")
    return s + YAHOO_SUFFIX.get(exchange, "")


def alias_key(symbol: str) -> str:
    """One spelling for matching: 'brk.b' / 'BRK-B' -> 'BRK-B', 'SN.' -> 'SN'."""
    return (symbol or "").strip().upper().replace(".", "-").rstrip("-")


def company_for(symbol: str) -> str | None:
    aliases = db.get_meta("company_aliases", {}) or {}
    s = alias_key(symbol)
    return aliases.get(s) or BUILTIN_COMPANIES.get(s)


def theme_for(symbol: str) -> str | None:
    return (db.get_meta("theme_aliases", {}) or {}).get(alias_key(symbol))


def upsert_instrument(c, symbol: str, exchange: str | None, name: str | None = None,
                      isin: str | None = None, currency: str | None = None) -> int:
    """Find or create, inside the caller's transaction `c`. ISIN first — it is the one
    identifier both brokers agree on, and it is how a holding split across platforms
    (the FSCS duplicates) is recognised as one instrument."""
    symbol = (symbol or "").strip().upper()
    isin = (isin or "").strip().upper() or None
    row = None
    if isin:
        row = c.execute("SELECT * FROM instruments WHERE isin=?", (isin,)).fetchone()
    if row is None and symbol:
        # One spelling for the ticker (Freetrade's BRK.B is Trading 212's BRK-B), and never
        # a row that already carries a different ISIN: that is a different security.
        row = c.execute("SELECT * FROM instruments WHERE rtrim(replace(upper(symbol),'.','-'),'-')=? "
                        "AND (exchange IS ? OR exchange=? OR exchange IS NULL) "
                        "AND (isin IS NULL OR ? IS NULL OR isin=?) ORDER BY id LIMIT 1",
                        (alias_key(symbol), exchange, exchange, isin, isin)).fetchone()
    if row is not None:
        c.execute("UPDATE instruments SET name=COALESCE(NULLIF(name,''),?),"
                  " isin=COALESCE(isin,?), currency=COALESCE(currency,?),"
                  " exchange=COALESCE(exchange,?) WHERE id=?",
                  (name, isin, currency, exchange, row["id"]))
        return row["id"]
    if not symbol and not isin:
        raise ValueError("an instrument needs a ticker or an ISIN")
    cur = c.execute(
        "INSERT INTO instruments(isin,symbol,exchange,name,currency,market_symbol,company,"
        "theme,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
        (isin, symbol or isin, exchange, name, currency, market_symbol(symbol, exchange),
         company_for(symbol), theme_for(symbol), db.now()))
    _apply_plan(c, cur.lastrowid, symbol, isin)
    if tbills.is_tbill(name, symbol, isin):
        cash = c.execute("SELECT id FROM sleeves WHERE is_cash=1 LIMIT 1").fetchone()
        if cash:
            c.execute("UPDATE instruments SET sleeve_id=COALESCE(sleeve_id, ?) WHERE id=?",
                      (cash["id"], cur.lastrowid))
    return cur.lastrowid


def plan_key(ident: str) -> str:
    """An ISIN as it is; anything else in the one spelling used for matching."""
    s = (ident or "").strip().upper()
    return s if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", s) else alias_key(s)


def _apply_plan(c, iid: int, symbol: str, isin: str | None) -> None:
    """A plan can name holdings before any broker has reported them: Ouster's price
    symbol, say, since Trading 212 still lists it under its old SPAC ticker, CLA. Those
    settings wait in meta and land the moment the holding first appears."""
    pending = db.get_meta("plan_instruments", {}) or {}
    conf = (pending.get(plan_key(isin)) if isin else None) or pending.get(plan_key(symbol))
    if not conf:
        return
    if conf.get("market_symbol"):
        c.execute("UPDATE instruments SET market_symbol=? WHERE id=?",
                  (str(conf["market_symbol"]).strip(), iid))
    if conf.get("ai_share") is not None:
        c.execute("UPDATE instruments SET ai_share=? WHERE id=?", (float(conf["ai_share"]), iid))
    if conf.get("sleeve"):
        row = c.execute("SELECT id FROM sleeves WHERE name=?", (conf["sleeve"],)).fetchone()
        if row:
            c.execute("UPDATE instruments SET sleeve_id=? WHERE id=?", (row["id"], iid))
