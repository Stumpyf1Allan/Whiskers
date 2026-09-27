"""The local copy of every price series the app uses, and how it is kept fresh.

Keys are namespaced so the same symbol can never be two things at once:

    REF:SP500     a reference series from catalogue.REFERENCE
    SEC:PCGH.L    a holding, by the symbol the price feed knows it by
    FX:USD        dollars per pound (always "units of that currency per £1")

Values are stored in the series' own major currency — pence have already been turned
into pounds by the source layer — and converted to pounds only when a screen asks.

A series is fetched in full the first time (five years) and then topped up with the
last month. When the source changes (Yahoo went quiet, FRED answered instead) the old
points are replaced rather than merged, so no chart ever splices two feeds together.

Every attempt is recorded — when it last worked, and what went wrong if it didn't — so
the app can say "last good data 3 days ago, Yahoo refusing requests" instead of showing
a stale number as though it were today's.
"""

from __future__ import annotations

import bisect
import datetime as dt
import threading
import time

from .. import config, db
from . import catalogue, sources

FULL_RANGE = "5y"
KEEP_DAYS = 6 * 366
#: A series fetched this recently is left alone unless somebody presses Refresh.
FRESH_FOR = 4 * 3600


def ref_key(name: str) -> str:
    return f"REF:{name}"


def sec_key(market_symbol: str) -> str:
    return f"SEC:{market_symbol}"


def fx_key(ccy: str) -> str:
    return f"FX:{ccy}"


# ---------------------------------------------------------------------------- reading

def points(key: str, since: str | None = None) -> list[tuple[str, float]]:
    if since:
        got = db.rows("SELECT d, v FROM series WHERE key=? AND d>=? ORDER BY d", (key, since))
    else:
        got = db.rows("SELECT d, v FROM series WHERE key=? ORDER BY d", (key,))
    return [(r["d"], r["v"]) for r in got]


def meta(key: str) -> dict | None:
    return db.one("SELECT * FROM series_meta WHERE key=?", (key,))


def metas(keys: list[str]) -> dict[str, dict]:
    if not keys:
        return {}
    q = ",".join("?" * len(keys))
    return {r["key"]: r for r in db.rows(f"SELECT * FROM series_meta WHERE key IN ({q})", keys)}


def latest(key: str) -> dict | None:
    """The newest value we have: the live price if the feed gave one that is at least
    as new as the last daily close, otherwise the last close."""
    row = db.one("SELECT d, v FROM series WHERE key=? ORDER BY d DESC LIMIT 1", (key,))
    m = meta(key) or {}
    if m.get("live") is not None and m.get("live_at") and \
            (not row or m["live_at"][:10] >= row["d"]):
        return {"value": m["live"], "as_of": m["live_at"], "live": True,
                "currency": m.get("currency"), "source": m.get("source")}
    if not row:
        return None
    return {"value": row["v"], "as_of": row["d"], "live": False,
            "currency": m.get("currency"), "source": m.get("source")}


# ---------------------------------------------------------------------------- writing

def _save(key: str, got: dict, source: str, replace: bool):
    now = db.now()
    pts = got.get("points") or []
    cutoff = (dt.date.today() - dt.timedelta(days=KEEP_DAYS)).isoformat()
    with db.tx() as c:
        if replace:
            c.execute("DELETE FROM series WHERE key=?", (key,))
        c.executemany("INSERT INTO series(key,d,v) VALUES(?,?,?) "
                      "ON CONFLICT(key,d) DO UPDATE SET v=excluded.v",
                      [(key, d, v) for d, v in pts if d >= cutoff])
        c.execute("DELETE FROM series WHERE key=? AND d<?", (key, cutoff))
        c.execute(
            "INSERT INTO series_meta(key,source,currency,name,live,live_at,fetched_at,last_ok,"
            "last_error) VALUES(?,?,?,?,?,?,?,?,NULL) ON CONFLICT(key) DO UPDATE SET "
            "source=excluded.source, currency=COALESCE(excluded.currency, series_meta.currency),"
            " name=COALESCE(excluded.name, series_meta.name), live=excluded.live,"
            " live_at=excluded.live_at, fetched_at=excluded.fetched_at,"
            " last_ok=excluded.last_ok, last_error=NULL",
            (key, source, got.get("currency"), got.get("name"), got.get("live"),
             got.get("live_at"), now, now))


def _fail(key: str, message: str):
    with db.tx() as c:
        c.execute("INSERT INTO series_meta(key,fetched_at,last_error) VALUES(?,?,?) "
                  "ON CONFLICT(key) DO UPDATE SET fetched_at=excluded.fetched_at,"
                  " last_error=excluded.last_error", (key, db.now(), message[:400]))


# ---------------------------------------------------------------------------- sources

def sources_for(key: str) -> list[tuple[str, str]]:
    kind, _, ident = key.partition(":")
    if kind == "REF":
        return list((catalogue.REFERENCE.get(ident) or {}).get("sources") or [])
    if kind == "FX":
        return catalogue.fx_sources(ident)
    if kind == "SEC":
        out = [("yahoo", ident)]
        if config.settings.get("stooq_key"):
            out.append(("stooq", ident))
        return out
    return []


def _currency_hint(key: str) -> str | None:
    """Only used for synthetic data, which has no feed to say."""
    kind, _, ident = key.partition(":")
    if kind == "SEC":
        return "GBP" if ident.upper().endswith(".L") else "USD"
    if kind == "REF":
        unit = (catalogue.REFERENCE.get(ident) or {}).get("unit", "")
        return {"£": "GBP", "$": "USD", "$/oz": "USD", "$/lb": "USD", "$/bbl": "USD"}.get(unit)
    return None


def _fetch(kind: str, ident: str, rng: str) -> dict:
    if config.fake_market():
        return sources.synthetic(ident, anchor=_fake_anchor(ident))
    if kind == "yahoo":
        return sources.yahoo(ident, rng)
    if kind == "fred":
        return sources.fred(ident)
    if kind == "fred_cross":
        top, bottom = ident.split("/")
        a = dict(sources.fred(top)["points"])
        b = dict(sources.fred(bottom)["points"])
        pts = [(d, a[d] / b[d]) for d in sorted(set(a) & set(b)) if b[d]]
        return {"points": pts, "currency": None, "name": None, "live": None, "live_at": None}
    if kind == "stooq":
        return sources.stooq(ident, config.settings.get("stooq_key") or "")
    raise sources.SourceError(f"unknown source {kind}")


def _fake_anchor(ident: str) -> float | None:
    """Test mode only: end the sample's made-up price series at the sample's own prices,
    so screenshots look like a portfolio rather than random numbers."""
    from ..engine import sample
    for _, sym, ex, _, _, _, price, _, _ in sample.HOLDINGS:
        from ..brokers import symbols
        if symbols.market_symbol(sym, ex) == ident:
            return price if ident.endswith(".L") else price * 1.30
    return None


def fetch_one(key: str, force: bool = False) -> dict:
    """Bring one series up to date. Returns {"status": ok|fresh|error, "message"}."""
    m = meta(key) or {}
    if not force and m.get("last_ok") and m.get("fetched_at"):
        try:
            age = time.time() - dt.datetime.fromisoformat(m["fetched_at"]).timestamp()
        except ValueError:
            age = FRESH_FOR + 1
        if age < FRESH_FOR:
            return {"status": "fresh"}
    last = db.scalar("SELECT MAX(d) FROM series WHERE key=?", (key,))
    errors = []
    for kind, ident in sources_for(key):
        same_source = m.get("source") == f"{kind}:{ident}"
        recent = last and (dt.date.today() - dt.date.fromisoformat(last)).days < 20
        rng = "1mo" if (same_source and recent) else FULL_RANGE
        try:
            got = _fetch(kind, ident, rng)
        except sources.SourceError as e:
            errors.append(str(e))
            continue
        except Exception as e:                       # a surprise must not stop the batch
            errors.append(f"{kind}: {e}")
            continue
        if not got.get("points"):
            errors.append(f"{kind} returned no prices for {ident}")
            continue
        if config.fake_market() and not got.get("currency"):
            got["currency"] = _currency_hint(key)
        _save(key, got, f"{kind}:{ident}", replace=not (same_source and recent))
        return {"status": "ok", "source": f"{kind}:{ident}"}
    msg = " · ".join(dict.fromkeys(errors)) or "no source for this series"
    _fail(key, msg)
    return {"status": "error", "message": msg}


# ---------------------------------------------------------------------------- the job

JOB = {"running": False, "done": 0, "total": 0, "current": "", "errors": [],
       "started": None, "finished": None, "phase": ""}
_job_lock = threading.Lock()


def repair() -> None:
    """Undo a symbol no source can know: an ISIN given a '.L' ending by an earlier version."""
    from ..brokers import tbills
    for r in db.rows("SELECT id, market_symbol FROM instruments WHERE market_symbol LIKE '%.L'"):
        if tbills.is_isin(r["market_symbol"][:-2]):
            db.execute("UPDATE instruments SET market_symbol=NULL WHERE id=?", (r["id"],))


def prune(wanted: list[str]) -> int:
    """Price series for things no longer held (a symbol corrected, a bill matured, a
    holding sold) are deleted, so their old errors stop being reported as current."""
    keep = set(wanted)
    stale = [r["key"] for r in db.rows("SELECT key FROM series_meta WHERE key LIKE 'SEC:%'")
             if r["key"] not in keep]
    with db.tx() as c:
        for k in stale:
            c.execute("DELETE FROM series WHERE key=?", (k,))
            c.execute("DELETE FROM series_meta WHERE key=?", (k,))
    return len(stale)


def wanted_keys() -> list[str]:
    keys = [ref_key(k) for k in catalogue.REFERENCE]
    ccys = set()
    for r in db.rows("SELECT DISTINCT i.market_symbol, sm.currency FROM positions p "
                     "JOIN instruments i ON i.id=p.instrument_id "
                     "LEFT JOIN series_meta sm ON sm.key = 'SEC:' || i.market_symbol "
                     "WHERE i.market_symbol IS NOT NULL AND i.market_symbol != ''"):
        keys.append(sec_key(r["market_symbol"]))
        if r["currency"]:
            ccys.add(r["currency"])
    for r in db.rows("SELECT DISTINCT currency FROM instruments WHERE currency IS NOT NULL"):
        major = config.MINOR_UNIT_CURRENCIES.get(r["currency"], (r["currency"],))[0]
        ccys.add(major)
    ccys |= {"USD", "EUR"}
    keys += [fx_key(c) for c in sorted(ccys) if c and c != "GBP"]
    return list(dict.fromkeys(keys))


def refresh(force: bool = False, keys: list[str] | None = None,
            on_progress=None) -> dict:
    """Run synchronously. The server calls start_refresh(), which wraps this in a thread."""
    full = keys is None
    if full:
        repair()
    keys = keys or wanted_keys()
    if full:
        prune(keys)
    ok = fresh = 0
    errors = []
    for i, key in enumerate(keys):
        JOB.update(current=key, done=i, total=len(keys))
        if on_progress:
            on_progress(i, len(keys), key)
        res = fetch_one(key, force=force)
        if res["status"] == "ok":
            ok += 1
        elif res["status"] == "fresh":
            fresh += 1
        else:
            errors.append({"key": key, "message": res["message"]})
    JOB.update(done=len(keys))
    return {"updated": ok, "fresh": fresh, "failed": len(errors), "errors": errors}


def start_refresh(force: bool = False, before=None) -> bool:
    """Start a background refresh unless one is running. `before` runs first on the
    same thread — the broker sync, so new holdings are priced in the same pass."""
    with _job_lock:
        if JOB["running"]:
            return False
        JOB.update(running=True, done=0, total=0, current="", errors=[],
                   started=db.now(), finished=None, phase="")

    def work():
        try:
            if before:
                JOB["phase"] = "brokers"
                try:
                    before()
                except Exception as e:
                    JOB["errors"].append({"key": "brokers", "message": str(e)})
            JOB["phase"] = "prices"
            rep = refresh(force=force)
            JOB["errors"].extend(rep["errors"])
            try:
                from ..engine import portfolio
                portfolio.take_snapshot()
            except Exception as e:
                db.log("snapshot.error", str(e))
        finally:
            JOB.update(running=False, finished=db.now(), current="", phase="")

    threading.Thread(target=work, daemon=True, name="refresh").start()
    return True


def job_state() -> dict:
    return dict(JOB, errors=JOB["errors"][-30:])


# ---------------------------------------------------------------------------- money

_fx_cache: dict[str, tuple[float, list[str], list[float]]] = {}


def _fx_table(ccy: str) -> tuple[list[str], list[float]]:
    key = fx_key(ccy)
    stamp = db.scalar("SELECT fetched_at FROM series_meta WHERE key=?", (key,), "")
    hit = _fx_cache.get(key)
    if hit and hit[0] == stamp:
        return hit[1], hit[2]
    pts = points(key)
    ds, vs = [d for d, _ in pts], [v for _, v in pts]
    _fx_cache[key] = (stamp, ds, vs)
    return ds, vs


def fx_rate(ccy: str | None, d: str | None = None) -> float | None:
    """Units of `ccy` per £1 on day `d` (or the latest), None if we have no rate.

    Never falls back to 1.0: silently adding dollars to pounds is exactly the kind of
    wrong number that looks right.
    """
    if not ccy or ccy == "GBP":
        return 1.0
    if ccy in config.MINOR_UNIT_CURRENCIES:
        major, div = config.MINOR_UNIT_CURRENCIES[ccy]
        base = fx_rate(major, d)
        return None if base is None else base * div
    ds, vs = _fx_table(ccy)
    if not ds:
        live = meta(fx_key(ccy))
        return live["live"] if live and live.get("live") else None
    if d is None:
        m = meta(fx_key(ccy)) or {}
        if m.get("live") and m.get("live_at") and m["live_at"][:10] >= ds[-1]:
            return m["live"]
        return vs[-1]
    i = bisect.bisect_right(ds, d) - 1
    if i < 0:
        return None
    # A rate more than a week older than the day asked for is not that day's rate.
    if (dt.date.fromisoformat(d) - dt.date.fromisoformat(ds[i])).days > 7:
        return None
    return vs[i]


def to_gbp(amount: float | None, ccy: str | None, d: str | None = None) -> float | None:
    if amount is None:
        return None
    rate = fx_rate(ccy, d)
    return None if not rate else amount / rate


def gbp_points(key: str, since: str | None = None) -> list[tuple[str, float]]:
    """A price series in pounds, converted day by day at that day's rate.

    Same rule as fx_rate(): a day with no rate within a week is dropped rather than
    converted at some other day's rate. Written as one pass over one rate table —
    looking each day up separately made a five-year chart take seconds.
    """
    m = meta(key) or {}
    ccy = m.get("currency") or "GBP"
    pts = points(key, since)
    div = 1.0
    if ccy in config.MINOR_UNIT_CURRENCIES:
        ccy, div = config.MINOR_UNIT_CURRENCIES[ccy]
    if ccy == "GBP":
        return pts if div == 1 else [(d, v / div) for d, v in pts]
    ds, vs = _fx_table(ccy)
    if not ds:
        return []
    out = []
    week = dt.timedelta(days=7)
    for d, v in pts:
        i = bisect.bisect_right(ds, d) - 1
        if i < 0 or dt.date.fromisoformat(d) - dt.date.fromisoformat(ds[i]) > week or not vs[i]:
            continue
        out.append((d, v / div / vs[i]))
    return out
