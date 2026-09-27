"""Freetrade: no API, so holdings are worked out from the activity export.

In the Freetrade app: Activity → the share icon → export. The file has one row per
event and its column names are self-describing. Two of them were renamed at some point
— "Total Amount" became "Total Amount in Account Currency" and "Total Shares Amount"
became "Total Amount in Instrument Currency" — and both spellings are accepted, since
older exports keep the old names. (Mittens & Pence reads only the new one, so an older
export imports every trade with no amount.)

Timestamps are UTC. The tax year turns at midnight UK time on 5/6 April, which is BST,
so a top-up stamped 23:30 UTC on 5 April belongs to the *next* tax year. `uk_date()`
works that out without the tz database — Python on Windows doesn't ship one, and a
dependency that is only missing on Windows is exactly the kind of bug that is only ever
found by the person on Windows.

What the file cannot describe — shares transferred out in specie, some corporate
actions — shows up as a holding whose share count doesn't match the app. Those can be
corrected by hand on the Holdings screen, and the correction is kept as an adjustment
so it survives the next import.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import re

from .. import db
from . import symbols, tbills

ALIASES = {"totalamountinaccountcurrency": "totalamount",
           "totalamountininstrumentcurrency": "totalsharesamount"}
IGNORED = {"MONTHLY_STATEMENT", "TAX_CERTIFICATE", "ANNUAL_STATEMENT"}


class NotFreetrade(ValueError):
    pass


def _norm(name: str) -> str:
    k = re.sub(r"[^a-z0-9]+", "", (name or "").lower())
    return ALIASES.get(k, k)


def _last_sunday(year: int, month: int) -> dt.date:
    d = dt.date(year, month + 1, 1) - dt.timedelta(days=1) if month < 12 else dt.date(year, 12, 31)
    return d - dt.timedelta(days=(d.weekday() + 1) % 7)


def uk_date(stamp: str) -> str | None:
    """'2025-04-05T23:30:00.000Z' -> '2025-04-06' (BST).  UK summer time runs from
    01:00 UTC on the last Sunday of March to 01:00 UTC on the last Sunday of October."""
    s = (stamp or "").strip()
    if not s:
        return None
    try:
        t = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        try:
            return dt.date.fromisoformat(s[:10]).isoformat()
        except ValueError:
            return None
    if t.tzinfo is not None:
        t = t.astimezone(dt.timezone.utc).replace(tzinfo=None)
    start = dt.datetime.combine(_last_sunday(t.year, 3), dt.time(1))
    end = dt.datetime.combine(_last_sunday(t.year, 10), dt.time(1))
    if start <= t < end:
        t += dt.timedelta(hours=1)
    return t.date().isoformat()


def _num(v) -> float | None:
    s = str(v or "").strip().replace(",", "").replace("£", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def read_rows(data: bytes) -> list[dict]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp1252", "replace")
    rdr = csv.reader(io.StringIO(text))
    header = next(rdr, None) or []
    keys = [_norm(h) for h in header]
    if not {"type", "timestamp", "totalamount"} <= set(keys):
        raise NotFreetrade("That file doesn't look like a Freetrade activity export — it has "
                           "no Type, Timestamp and Total Amount columns.")
    out = []
    for row in rdr:
        if not any(x.strip() for x in row):
            continue
        out.append({k: (row[i].strip() if i < len(row) else "") for i, k in enumerate(keys)})
    return out


def import_csv(platform_id: int, data: bytes) -> dict:
    rows = read_rows(data)
    rep = {"rows": len(rows), "trades": 0, "dividends": 0, "cash": 0, "skipped": 0,
           "warnings": [], "unknown_types": {}, "first": None, "last": None}
    with db.tx() as c:
        for r in rows:
            typ = (r.get("type") or "").upper()
            day = uk_date(r.get("timestamp") or r.get("dividendpaydate"))
            if not day:
                rep["skipped"] += 1
                continue
            rep["first"] = min(filter(None, [rep["first"], day]))
            rep["last"] = max(filter(None, [rep["last"], day]))
            total = _num(r.get("totalamount"))
            ref = r.get("orderid") or ""
            if typ in IGNORED:
                continue
            if typ in ("ORDER", "FREESHARE_ORDER") and (r.get("ticker") or r.get("isin")):
                side = (r.get("buysell") or "BUY").upper()
                qty = _num(r.get("quantity")) or 0.0
                if not qty:
                    rep["skipped"] += 1
                    continue
                iid = _instrument(c, r)
                fees = (_num(r.get("stampduty")) or 0) + (_num(r.get("fxfeeamount")) or 0)
                # A free share cost nothing: recording its market value as cost would hide
                # the gift inside the cost basis.
                value = 0.0 if typ == "FREESHARE_ORDER" else abs(total or 0.0)
                fp = db.fingerprint("ft", platform_id, ref or (day, r.get("isin"), side, qty, total))
                rep["trades"] += c.execute(
                    "INSERT OR IGNORE INTO trades(platform_id,instrument_id,traded_on,side,quantity,"
                    "price,price_ccy,value_gbp,fees_gbp,ref,source,fp) VALUES(?,?,?,?,?,?,?,?,?,?,'csv',?)",
                    (platform_id, iid, day, "SELL" if side == "SELL" else "BUY", qty,
                     _num(r.get("pricepershareinaccountcurrency")), "GBP", value, fees, ref,
                     fp)).rowcount
            elif typ == "DIVIDEND" and (r.get("ticker") or r.get("isin")):
                iid = _instrument(c, r)
                amount = total
                if amount is None:
                    net = _num(r.get("dividendnetdistributionamount"))
                    fx = _num(r.get("basefxrate")) or 1.0
                    amount = None if net is None else net * fx
                if amount is None:
                    rep["skipped"] += 1
                    continue
                fp = db.fingerprint("ft", platform_id, "div", day, r.get("isin"), amount)
                rep["dividends"] += c.execute(
                    "INSERT OR IGNORE INTO dividends(platform_id,instrument_id,paid_on,amount_gbp,"
                    "withheld_gbp,ref,source,fp) VALUES(?,?,?,?,?,?,'csv',?)",
                    (platform_id, iid, day, amount,
                     _num(r.get("dividendwithheldtaxamount")), ref, fp)).rowcount
            elif typ in ("TOP_UP", "WITHDRAWAL", "INTEREST_FROM_CASH"):
                kind = {"TOP_UP": "DEPOSIT", "WITHDRAWAL": "WITHDRAWAL",
                        "INTEREST_FROM_CASH": "INTEREST"}[typ]
                amt = abs(total or 0.0) * (-1 if kind == "WITHDRAWAL" else 1)
                fp = db.fingerprint("ft", platform_id, kind, r.get("timestamp"), amt)
                rep["cash"] += c.execute(
                    "INSERT OR IGNORE INTO cash_moves(platform_id,happened_on,kind,amount_gbp,ref,"
                    "source,fp) VALUES(?,?,?,?,?,'csv',?)",
                    (platform_id, day, kind, amt, r.get("title"), fp)).rowcount
            else:
                if "SPLIT" in typ:
                    rep["warnings"].append(
                        f"A stock split on {r.get('ticker') or r.get('title')} ({day}) — check "
                        f"that holding's share count against Freetrade.")
                rep["unknown_types"][typ or "(blank)"] = rep["unknown_types"].get(typ, 0) + 1
                rep["skipped"] += 1
        c.execute("UPDATE platforms SET last_sync=?, last_error=NULL WHERE id=?",
                  (db.now(), platform_id))
    rep["positions"] = rebuild_positions(platform_id)
    return rep


def _instrument(c, r: dict) -> int:
    ticker = (r.get("ticker") or "").strip()
    isin = (r.get("isin") or "").strip()
    ccy = (r.get("instrumentcurrency") or "").strip() or None
    ex = symbols.exchange_from(r.get("venue"), isin, ccy)
    return symbols.upsert_instrument(c, ticker, ex, r.get("title") or None, isin or None, ccy)


def rebuild_positions(platform_id: int) -> int:
    """Share counts and average cost from every trade on this platform, in date order.

    Cost is pooled the way HMRC pools it: a sale takes away its share of the pool at
    the average cost, not at the price of any particular purchase. Inside an ISA there
    is no tax to work out, but the same arithmetic gives the honest figure for "what the
    shares I still own cost me".
    """
    trades = db.rows("SELECT * FROM trades WHERE platform_id=? ORDER BY traded_on, id",
                     (platform_id,))
    gone = matured_bills(platform_id)
    pools: dict[int, list[float]] = {}
    for t in trades:
        q, cost = pools.setdefault(t["instrument_id"], [0.0, 0.0])
        n = t["quantity"] or 0.0
        if t["side"] in ("BUY", "TRANSFER_IN"):
            q, cost = q + n, cost + (t["value_gbp"] or 0.0)
        elif t["side"] in ("SELL", "TRANSFER_OUT"):
            if q > 0:
                cost -= cost * min(1.0, n / q)
            q -= n
        elif t["side"] == "ADJUST":
            q += n                               # a hand correction: shares, not money
        elif t["side"] == "COST":
            cost += t["value_gbp"] or 0.0        # a correction to what the holding cost
        elif t["side"] == "SET":
            # "From this day the holding is exactly this": everything earlier is replaced.
            # A delta would be wrong whenever the file sells shares it never saw arrive
            # (a transfer in), because the running count has gone negative by then.
            keep = cost if q > 0 else 0.0
            q = n
            cost = keep if t["value_gbp"] is None else t["value_gbp"]
        pools[t["instrument_id"]] = [q, cost]
    now = db.now()
    kept = 0
    with db.tx() as c:
        c.execute("DELETE FROM positions WHERE platform_id=? AND source='csv'", (platform_id,))
        for iid, (q, cost) in pools.items():
            if q > 1e-6 and iid not in gone:
                c.execute("INSERT OR REPLACE INTO positions(platform_id,instrument_id,quantity,cost,"
                          "source,updated_at) VALUES(?,?,?,?,'csv',?)",
                          (platform_id, iid, round(q, 8), round(cost, 2), now))
                kept += 1
    return kept


def matured_bills(platform_id: int) -> dict[int, float]:
    """Treasury bills on this platform that have repaid, with what they cost. Freetrade's
    export records the purchase and not the maturity, so the date decides."""
    out = {}
    for r in db.rows("SELECT i.id, i.name, i.symbol, i.isin, MIN(t.traded_on) AS first,"
                     " SUM(CASE WHEN t.side='BUY' THEN t.value_gbp ELSE 0 END) -"
                     " SUM(CASE WHEN t.side='SELL' THEN t.value_gbp ELSE 0 END) AS cost"
                     " FROM trades t JOIN instruments i ON i.id=t.instrument_id"
                     " WHERE t.platform_id=? GROUP BY i.id", (platform_id,)):
        if tbills.is_tbill(r["name"], r["symbol"], r["isin"]) and tbills.matured(r["name"], r["first"]):
            out[r["id"]] = r["cost"] or 0.0
    return out


def rebuild_all() -> None:
    """Re-derive every Freetrade platform's holdings — how a fix to the arithmetic (a bill
    that has matured since the last import, say) reaches data already imported."""
    cash = db.scalar("SELECT id FROM sleeves WHERE is_cash=1 LIMIT 1")
    for p in db.rows("SELECT id FROM platforms WHERE provider='freetrade'"):
        rebuild_positions(p["id"])
    if cash:
        for i in db.rows("SELECT id, name, symbol, isin FROM instruments WHERE sleeve_id IS NULL"):
            if tbills.is_tbill(i["name"], i["symbol"], i["isin"]):
                db.execute("UPDATE instruments SET sleeve_id=? WHERE id=?", (cash, i["id"]))


def set_holding(platform_id: int, instrument_id: int, shares: float, cost: float | None,
                note: str) -> None:
    """Bring a holding to what the broker actually shows, from today. Freetrade's export
    leaves out shares that arrive by transfer and holdings changed by a corporate action
    such as a fund merger; this records one SET, which later trades then build on."""
    with db.tx() as c:
        c.execute("INSERT INTO trades(platform_id,instrument_id,traded_on,side,quantity,value_gbp,ref,"
                  "source,fp) VALUES(?,?,?,'SET',?,?,?,'manual',?)",
                  (platform_id, instrument_id, db.today(), float(shares),
                   None if cost is None or float(shares) <= 0 else round(float(cost), 2), note[:200],
                   db.fingerprint("set", platform_id, instrument_id, db.now(), shares)))
    rebuild_positions(platform_id)


def adjust_quantity(platform_id: int, instrument_id: int, correct_quantity: float,
                    note: str = "") -> float:
    """Record the difference between what the file adds up to and what the broker
    actually shows, as an ADJUST trade dated today, then rebuild."""
    current = db.scalar("SELECT quantity FROM positions WHERE platform_id=? AND instrument_id=?",
                        (platform_id, instrument_id), 0.0)
    delta = float(correct_quantity) - float(current)
    if abs(delta) < 1e-9:
        return 0.0
    set_holding(platform_id, instrument_id, float(correct_quantity), None, note or "Corrected by hand")
    return delta


def cash_estimate(platform_id: int) -> float | None:
    """What the file says should be sitting uninvested — only meaningful when the file
    covers the account from the day it opened, which is why the app offers it as a
    suggestion and never overwrites a figure somebody typed in."""
    moves = db.scalar("SELECT SUM(amount_gbp) FROM cash_moves WHERE platform_id=?", (platform_id,), 0.0)
    buys = db.scalar("SELECT SUM(value_gbp) FROM trades WHERE platform_id=? AND side='BUY'",
                     (platform_id,), 0.0)
    sells = db.scalar("SELECT SUM(value_gbp) FROM trades WHERE platform_id=? AND side='SELL'",
                      (platform_id,), 0.0)
    divs = db.scalar("SELECT SUM(amount_gbp) FROM dividends WHERE platform_id=?", (platform_id,), 0.0)
    if not (moves or buys or sells or divs):
        return None
    repaid = sum(matured_bills(platform_id).values())   # bills repay at least what they cost
    return round(moves - buys + sells + divs + repaid, 2)
