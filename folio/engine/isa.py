"""The ISA allowance: how much has gone in this tax year, across every ISA.

The UK tax year runs 6 April to 5 April. The allowance is per person across all ISAs,
so both platforms count against the one limit.

*Flexible* ISAs (Trading 212's is one) let money taken out be put back in the same tax
year without using allowance twice; for those, what counts is deposits less
withdrawals. For a non-flexible ISA every deposit counts, whatever came out.

Transfers from another ISA provider are not subscriptions and are left out — but they
are shown, because a transfer of *this* year's money carries its subscription with it,
and that is worth a person knowing.
"""

from __future__ import annotations

import datetime as dt

from .. import config, db


def tax_year(d: dt.date | None = None) -> int:
    """The calendar year the tax year starts in: 5 April 2026 -> 2025."""
    d = d or dt.date.today()
    return d.year if (d.month, d.day) >= (4, 6) else d.year - 1


def label(y: int) -> str:
    return f"{y}/{str(y + 1)[-2:]}"


def bounds(y: int) -> tuple[dt.date, dt.date]:
    return dt.date(y, 4, 6), dt.date(y + 1, 4, 5)


def allowance(y: int | None = None) -> dict:
    y = tax_year() if y is None else y
    start, end = bounds(y)
    limit = float(config.settings.get("isa_allowance") or 20000)
    rows = []
    used = 0.0
    transfers = 0.0
    for p in db.rows("SELECT * FROM platforms WHERE wrapper='isa' ORDER BY sort, id"):
        def total(kind, sign=1):
            return sign * (db.scalar("SELECT SUM(amount_gbp) FROM cash_moves WHERE platform_id=?"
                                     " AND kind=? AND happened_on BETWEEN ? AND ?",
                                     (p["id"], kind, start.isoformat(), end.isoformat()), 0.0))
        dep = total("DEPOSIT")
        wd = total("WITHDRAWAL", -1)                   # stored negative; make positive
        tr = total("TRANSFER")
        mine = max(0.0, dep - wd) if p["flexible"] else dep
        used += mine
        transfers += tr
        rows.append({"id": p["id"], "name": p["name"], "deposits": dep, "withdrawals": wd,
                     "flexible": bool(p["flexible"]), "used": mine, "transfers": tr})
    today = dt.date.today()
    return {"year": y, "label": label(y), "start": start.isoformat(), "end": end.isoformat(),
            "days_left": max(0, (end - today).days) if start <= today <= end else None,
            "limit": limit, "used": used, "remaining": max(0.0, limit - used),
            "over": used > limit + 0.005, "platforms": rows, "transfers": transfers,
            "has_data": bool(db.scalar("SELECT COUNT(*) FROM cash_moves", (), 0))}


def history(years: int = 6) -> list[dict]:
    now = tax_year()
    return [{"label": label(y), **{k: allowance(y)[k] for k in ("used", "limit")}}
            for y in range(now - years + 1, now + 1)]
