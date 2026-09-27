"""UK Treasury bills, as Freetrade sells them.

Freetrade offers 28-day bills from the Debt Management Office's weekly tender and, by
default, rolls each one into the next when it matures. Every bill has its own ISIN, so a
year of rolling makes a dozen "holdings", and Freetrade's activity export lists each
purchase but not the maturity: the bill simply expires and the money comes back as cash.
Read naively, the file says every bill ever bought is still held. Allan's first run of
Whiskers showed 38 of them, all being looked up on Yahoo, which has no price for any.

So a bill is recognised, given a maturity date, and dropped once that date has passed.
Until then it is valued at what it cost: a bill held to maturity repays its face value,
and over 28 days the difference is a fraction of a per cent.

Recognition is deliberately narrow. The name has to say "bill" (or T-bill, or UKTB), and
must not say "gilt": a gilt runs for years, and wrongly expiring one would make a real
holding vanish. Anything unrecognised is left alone and shown as a holding with no public
price, which is visible and harmless.
"""

from __future__ import annotations

import datetime as dt
import re

ISIN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
_BILL = re.compile(r"\bbills?\b|\bt-?bills?\b|\buktb\b", re.I)
_NOT_A_BILL = re.compile(r"\bgilt|\bstock\b|\bnote\b|\bbond", re.I)
#: Freetrade's bills run 28 days from issue; issue follows the Friday tender. When a
#: name carries no readable date, a bill is taken to have matured this long after it
#: was bought — later than any 28-day bill can run, so a live one is never dropped early.
FALLBACK_DAYS = 35
#: A date read from a name is believed only if it lands this soon after the purchase.
MAX_TERM_DAYS = 200

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def is_isin(s: str | None) -> bool:
    return bool(ISIN.match((s or "").strip().upper()))


def is_tbill(name: str | None, symbol: str | None = None, isin: str | None = None) -> bool:
    text = name or ""
    if not _BILL.search(text) or _NOT_A_BILL.search(text):
        return False
    code = (isin or symbol or "").strip().upper()
    return not code or code.startswith("GB")


def _year(y: str) -> int:
    n = int(y)
    return n + 2000 if n < 100 else n


def _candidates(name: str) -> list[dt.date]:
    out: list[dt.date] = []

    def add(y, m, d):
        try:
            out.append(dt.date(y, m, d))
        except ValueError:
            pass

    for y, m, d in re.findall(r"(\d{4})-(\d{1,2})-(\d{1,2})", name):
        add(int(y), int(m), int(d))
    for a, b, y in re.findall(r"(?<!\d)(\d{1,2})[/.](\d{1,2})[/.](\d{2,4})(?!\d)", name):
        add(_year(y), int(b), int(a))           # UK order, 30/09/2024
        add(_year(y), int(a), int(b))           # and US order, as Bloomberg writes UKTB 0 09/30/24
    for d, mon, y in re.findall(r"(?<!\d)(\d{1,2})\s*([A-Za-z]{3,9})\.?\s*(\d{2,4})(?!\d)", name):
        m = _MONTHS.get(mon[:3].lower())
        if m:
            add(_year(y), m, int(d))
    return out


def maturity(name: str | None, first_bought: str | dt.date | None) -> dt.date | None:
    """The date the bill repays. Read from its name when the name carries a date that
    makes sense for a bill bought on `first_bought`; otherwise a safe upper bound."""
    if not first_bought:
        return None
    bought = first_bought if isinstance(first_bought, dt.date) else dt.date.fromisoformat(str(first_bought)[:10])
    ok = [d for d in _candidates(name or "")
          if bought - dt.timedelta(days=3) <= d <= bought + dt.timedelta(days=MAX_TERM_DAYS)]
    if ok:
        # Both readings of 03/04 can fit; the one nearest a 28-day term is the bill's.
        return min(ok, key=lambda d: abs((d - (bought + dt.timedelta(days=28))).days))
    return bought + dt.timedelta(days=FALLBACK_DAYS)


def matured(name: str | None, first_bought, today: dt.date | None = None) -> bool:
    when = maturity(name, first_bought)
    return bool(when and when < (today or dt.date.today()))
