"""The local web server behind the window.

Standard library only, bound to 127.0.0.1. The request checks at the bottom are the
ones Mittens & Pence needed after finding that any web page open in the same browser
could post to its local server, tightened one step further: requests must come from
this app's own port, so Whiskers and Mittens & Pence cannot reach each other either.
"""

from __future__ import annotations

import datetime as dt
import hmac
import json
import mimetypes
import os
import pathlib
import re
import socket
import threading
import traceback
import unicodedata
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .. import config, db, net, security, updates
from ..brokers import freetrade, monzo, symbols, trading212
from ..engine import (allocation, export, isa, mathx, narrative, plan, planbuilder, playbook, portfolio,
                      rules, sample, signals, stress)
from ..market import catalogue, sources, store

STATIC = pathlib.Path(__file__).resolve().parent / "static"


def _static_dir() -> pathlib.Path:
    frozen = config.resource_dir() / "web" / "static"
    return frozen if frozen.exists() else STATIC


class ApiError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status
        self.message = message


ROUTES: list[tuple[str, re.Pattern, callable]] = []


def route(method: str, pattern: str):
    rx = re.compile("^" + re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", pattern) + "$")

    def deco(fn):
        ROUTES.append((method, rx, fn))
        return fn
    return deco


def _int(v, what="number") -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        raise ApiError(f"That {what} isn't valid.") from None


def _float(v, what="number", lo=None, hi=None, allow_none=False):
    if (v is None or v == "") and allow_none:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise ApiError(f"{what} needs to be a number.") from None
    if (lo is not None and f < lo) or (hi is not None and f > hi):
        raise ApiError(f"{what} needs to be between {lo:g} and {hi:g}.")
    return f


def _spark(key: str, days: int = 365, n: int = 60) -> list:
    pts = mathx.thin(store.gbp_points(key, (dt.date.today() - dt.timedelta(days=days)).isoformat()), n)
    return [[d, round(v, 4)] for d, v in pts]


# ============================================================================ bootstrap

@route("GET", "/api/bootstrap")
def api_bootstrap(req, m, q, body):
    s = config.settings.all()
    return {
        "app": {"name": config.APP_NAME, "version": config.APP_VERSION,
                "tagline": config.APP_TAGLINE, "fake_market": config.fake_market()},
        "settings": {k: s.get(k) for k in ("user_name", "toured", "help_email", "isa_allowance",
                                           "fscs_limit", "refresh_on_open", "theme",
                                           "hide_amounts")},
        "platforms": db.scalar("SELECT COUNT(*) FROM platforms", (), 0),
        "holdings": db.scalar("SELECT COUNT(*) FROM positions", (), 0),
        "sleeves": db.scalar("SELECT COUNT(*) FROM sleeves", (), 0),
        "sample": sample.loaded(),
        "browser_tls": net.have_browser_tls(),
        "refresh": store.job_state(),
    }


# ============================================================================ overview

def _everything():
    pos = portfolio.positions()
    tot = portfolio.totals(pos)
    alloc = allocation.view(pos, tot)
    exp = stress.exposure(pos, tot)
    market = signals.evaluate()
    back = portfolio.backdated(5 * 365, pos)
    cash_sleeve = next((r["value"] for r in alloc["sleeves"] if r["is_cash"]), tot["cash"])
    pb = playbook.evaluate(back, cash_sleeve)
    ht = allocation.holding_targets(pos, tot["total"] or 0.0)
    warns = rules.evaluate(pos, tot, alloc, exp, market, pb, ht)
    return pos, tot, alloc, exp, market, warns, back, pb, ht


@route("GET", "/api/overview")
def api_overview(req, m, q, body):
    pos, tot, alloc, exp, market, warns, back, pb, ht = _everything()
    movers = sorted([x for x in pos if x["day_change"] is not None],
                    key=lambda x: abs(x["day_change"]), reverse=True)[:6]
    return {
        "totals": tot, "warnings": warns,
        "allocation": {"sleeves": alloc["sleeves"], "extra": alloc["extra"],
                       "outside": alloc["outside"], "drifting": alloc["drifting"],
                       "in_band": alloc["in_band"], "waffle": allocation.waffle(alloc)},
        "exposure": {"ai_pct": exp["ai_pct"], "ai_value": exp["ai_value"],
                     "unknown": len(exp["unknown"])},
        "market": {k: market[k] for k in ("regime", "label", "text", "gauge", "have", "of", "groups")}
                  | {"lights": [{k: x.get(k) for k in ("key", "title", "level", "words", "group", "since",
                                                        "direction")} for x in market["lights"]]},
        "big_picture": narrative.big_picture(market, pb, exp, alloc, tot),
        "isa": isa.allowance(),
        "playbook": {"firing": pb["firing"], "of": pb["of"], "known": pb["known"], "tier": pb["tier"],
                     "ai_firing": sum(1 for r in pb["signals"] if r["group"] == "ai" and r["firing"]),
                     "drop": pb["ladder"]["drop"]},
        "history": {"points": [[d, v] for d, v in mathx.thin(back["points"], 520)],
                    "coverage": back["coverage"], "missing": back["missing"],
                    "worst": back.get("worst")},
        "snapshots": [[d, v] for d, v in portfolio.snapshots()],
        "money_in": [[d, v] for d, v in portfolio.money_in()],
        "movers": [{k: x[k] for k in ("name", "day_change", "day_pct", "instrument_id")} for x in movers],
    }


# ============================================================================ holdings

@route("GET", "/api/holdings")
def api_holdings(req, m, q, body):
    pos = portfolio.positions()
    tot = portfolio.totals(pos)
    total = tot["total"] or 0
    for x in pos:
        x["weight"] = (x["value"] / total) if (x["value"] is not None and total) else None
        x["spark"] = _spark(store.sec_key(x["market_symbol"])) if x["market_symbol"] else []
    return {"rows": pos, "totals": tot, "sleeves": allocation.sleeves()}


@route("GET", "/api/holding/{iid}")
def api_holding(req, m, q, body):
    iid = _int(m["iid"])
    inst = db.one("SELECT i.*, s.name AS sleeve FROM instruments i LEFT JOIN sleeves s "
                  "ON s.id=i.sleeve_id WHERE i.id=?", (iid,))
    if not inst:
        raise ApiError("No such holding.", 404)
    pos = [x for x in portfolio.positions() if x["instrument_id"] == iid]
    key = store.sec_key(inst["market_symbol"]) if inst["market_symbol"] else None
    pts = store.points(key) if key else []
    meta = store.meta(key) if key else None
    vals = [v for _, v in pts]
    s50, s200 = mathx.sma(vals, 50), mathx.sma(vals, 200)
    dd = mathx.drawdowns(vals, 252) if vals else []
    trades = db.rows("SELECT t.*, p.name AS platform FROM trades t JOIN platforms p ON "
                     "p.id=t.platform_id WHERE instrument_id=? ORDER BY traded_on", (iid,))
    divs = db.rows("SELECT d.*, p.name AS platform FROM dividends d JOIN platforms p ON "
                   "p.id=d.platform_id WHERE instrument_id=? ORDER BY paid_on DESC", (iid,))
    look = db.rows("SELECT company, weight, as_of FROM lookthrough WHERE fund_id=? ORDER BY weight DESC",
                   (iid,))
    return {
        "instrument": inst, "positions": pos,
        "series": [[d, round(v, 6)] for d, v in pts],
        "sma50": [[pts[i][0], round(a, 6)] for i, a in enumerate(s50) if a is not None],
        "sma200": [[pts[i][0], round(a, 6)] for i, a in enumerate(s200) if a is not None],
        "drawdown": dd[-1] if dd else None,
        "high": max(pts[-252:], key=lambda p: p[1]) if pts else None,
        "currency": (meta or {}).get("currency"), "source": (meta or {}).get("source"),
        "fetched": (meta or {}).get("last_ok"), "price_error": None if pts else (meta or {}).get("last_error"),
        "trades": trades, "dividends": divs, "lookthrough": look,
        "changes": {k: mathx.change_over(pts, d) for k, d in
                    (("1m", 30), ("3m", 91), ("1y", 365), ("5y", 1826))},
        "sleeves": allocation.sleeves(),
        "suggested_sleeve": allocation.suggest(inst["name"] or inst["symbol"], allocation.sleeves()),
    }


INSTRUMENT_FIELDS = {"sleeve_id", "ai_share", "market_symbol", "company", "theme", "notes", "name"}


@route("PATCH", "/api/instrument/{iid}")
def api_patch_instrument(req, m, q, body):
    iid = _int(m["iid"])
    changes = {k: v for k, v in (body or {}).items() if k in INSTRUMENT_FIELDS}
    if "ai_share" in changes:
        changes["ai_share"] = _float(changes["ai_share"], "The AI share", 0, 100, allow_none=True)
    if "sleeve_id" in changes and changes["sleeve_id"] not in (None, ""):
        changes["sleeve_id"] = _int(changes["sleeve_id"], "sleeve")
        if not db.one("SELECT 1 FROM sleeves WHERE id=?", (changes["sleeve_id"],)):
            raise ApiError("That sleeve doesn't exist any more.")
    elif "sleeve_id" in changes:
        changes["sleeve_id"] = None
    for k in ("market_symbol", "company", "theme", "notes", "name"):
        if k in changes:
            changes[k] = (str(changes[k] or "").strip() or None)
    if not changes:
        raise ApiError("Nothing to change.")
    sets = ", ".join(f"{k}=?" for k in changes)
    db.execute(f"UPDATE instruments SET {sets} WHERE id=?", (*changes.values(), iid))
    if changes.get("market_symbol"):
        threading.Thread(target=store.fetch_one, args=(store.sec_key(changes["market_symbol"]),),
                         kwargs={"force": True}, daemon=True).start()
    return db.one("SELECT * FROM instruments WHERE id=?", (iid,))


@route("POST", "/api/assign")
def api_assign(req, m, q, body):
    """Several holdings into sleeves at once: [{instrument_id, sleeve_id}]."""
    items = (body or {}).get("items") or []
    with db.tx() as c:
        for it in items:
            c.execute("UPDATE instruments SET sleeve_id=? WHERE id=?",
                      (it.get("sleeve_id") or None, _int(it.get("instrument_id"))))
    return {"ok": True, "assigned": len(items)}


@route("POST", "/api/check-symbol")
def api_check_symbol(req, m, q, body):
    """Try a price symbol without saving it, so a correction can be seen to work first."""
    sym = str((body or {}).get("symbol") or "").strip()
    if not sym or len(sym) > 32 or not re.fullmatch(r"[A-Za-z0-9.^=\-]+", sym):
        raise ApiError("That doesn't look like a ticker symbol.")
    try:
        got = sources.synthetic(sym) if config.fake_market() else sources.yahoo(sym, "1mo")
    except sources.SourceError as e:
        return {"ok": False, "message": str(e)}
    last = got["points"][-1] if got["points"] else None
    return {"ok": bool(last), "name": got.get("name"), "currency": got.get("currency"),
            "price": got.get("live") or (last[1] if last else None),
            "date": last[0] if last else None}


@route("POST", "/api/positions")
def api_add_position(req, m, q, body):
    b = body or {}
    pid = _int(b.get("platform_id"), "platform")
    plat = db.one("SELECT * FROM platforms WHERE id=?", (pid,))
    if not plat:
        raise ApiError("Choose a platform first.")
    sym = str(b.get("symbol") or "").strip().upper()
    if not sym:
        raise ApiError("Type the ticker, e.g. VWRP or NVDA.")
    qty = _float(b.get("quantity"), "The number of shares", 0.000001)
    cost = _float(b.get("cost"), "What it cost", 0, allow_none=True)
    ex = b.get("exchange") or ("LSE" if b.get("london") else "US")
    with db.tx() as c:
        iid = symbols.upsert_instrument(c, sym, ex, (b.get("name") or "").strip() or None, None, None)
        if b.get("market_symbol"):
            c.execute("UPDATE instruments SET market_symbol=? WHERE id=?", (b["market_symbol"], iid))
        c.execute("INSERT INTO positions(platform_id,instrument_id,quantity,cost,source,updated_at)"
                  " VALUES(?,?,?,?,'manual',?) ON CONFLICT(platform_id,instrument_id) DO UPDATE SET"
                  " quantity=excluded.quantity, cost=excluded.cost, source='manual',"
                  " updated_at=excluded.updated_at", (pid, iid, qty, cost, db.now()))
    ms = db.scalar("SELECT market_symbol FROM instruments WHERE id=?", (iid,))
    if ms:
        threading.Thread(target=store.fetch_one, args=(store.sec_key(ms),), daemon=True).start()
    return {"ok": True, "instrument_id": iid}


@route("POST", "/api/positions/adjust")
def api_adjust(req, m, q, body):
    b = body or {}
    pid, iid = _int(b.get("platform_id")), _int(b.get("instrument_id"))
    src = db.scalar("SELECT source FROM positions WHERE platform_id=? AND instrument_id=?", (pid, iid))
    if src == "api":
        raise ApiError("This holding comes straight from Trading 212, so it is always what "
                       "Trading 212 says. Nothing to correct here.")
    qty = _float(b.get("quantity"), "The share count", 0)
    if src == "manual":
        db.execute("UPDATE positions SET quantity=?, updated_at=? WHERE platform_id=? AND "
                   "instrument_id=?", (qty, db.now(), pid, iid))
        return {"ok": True, "delta": None}
    return {"ok": True, "delta": freetrade.adjust_quantity(pid, iid, qty, "Corrected by hand")}


@route("DELETE", "/api/positions/{pid}/{iid}")
def api_delete_position(req, m, q, body):
    pid, iid = _int(m["pid"]), _int(m["iid"])
    src = db.scalar("SELECT source FROM positions WHERE platform_id=? AND instrument_id=?", (pid, iid))
    if src in ("api", "csv"):
        raise ApiError("This holding comes from the broker's own records and would come back "
                       "on the next update. Correct its share count instead.")
    db.execute("DELETE FROM positions WHERE platform_id=? AND instrument_id=?", (pid, iid))
    return {"ok": True}


# ============================================================================ allocation

@route("GET", "/api/allocation")
def api_allocation(req, m, q, body):
    pos, tot, alloc, exp, market, warns, back, pb, ht = _everything()
    sl = allocation.sleeves()
    unassigned = [{"instrument_id": x["instrument_id"], "name": x["name"], "value": x["value"],
                   "platform": x["platform"],
                   "suggested": allocation.suggest(x["name"], sl)}
                  for x in pos if x["sleeve_id"] is None]
    seen, dedup = set(), []
    for u in unassigned:
        if u["instrument_id"] not in seen:
            seen.add(u["instrument_id"])
            dedup.append(u)
    statuses = []
    for s in rules.rule_status(pos, tot, exp):
        r = s["rule"]
        statuses.append({"id": r["id"], "kind": r["kind"], "subject": r["subject"],
                         "trigger": r["trigger_pct"], "target": r["target_pct"], "basis": r["basis"],
                         "note": r["note"], "now": s["now"], "level": s["level"],
                         "trim": s.get("trim"), "amber_from": s.get("amber_from"),
                         "detail": s.get("detail")})
    by_sleeve = {}
    for x in pos:
        by_sleeve.setdefault(x["sleeve_id"], []).append(
            {"name": x["name"], "value": x["value"], "platform": x["platform"],
             "instrument_id": x["instrument_id"]})
    return {"view": alloc, "waffle": allocation.waffle(alloc), "sleeves": sl,
            "unassigned": dedup, "rules": statuses, "total": tot["total"], "holding_targets": ht,
            "members": {str(k): v for k, v in by_sleeve.items()},
            "warnings": [w for w in warns if w["kind"] in ("drift", "company_cap", "theme_cap",
                                                           "ai_cap", "data")]}


@route("POST", "/api/allocation/new-money")
def api_new_money(req, m, q, body):
    amount = _float((body or {}).get("amount"), "The amount", 1, 10_000_000)
    pos = portfolio.positions()
    tot = portfolio.totals(pos)
    return {"split": allocation.new_money(amount, allocation.view(pos, tot))}


# ============================================================================ AI watch

@route("GET", "/api/ai")
def api_ai(req, m, q, body):
    pos, tot, alloc, exp, market, warns, back, pb, ht = _everything()
    plans = {r["topic"]: r for r in db.rows("SELECT * FROM plans")}
    cap = db.one("SELECT * FROM rules WHERE kind='ai_cap' AND enabled=1")
    return {"exposure": exp, "totals": {k: tot[k] for k in ("total", "cash", "invested")},
            "market": market, "context": signals.context(), "plans": plans,
            "dotcom": stress.DOTCOM, "worst": back.get("worst"), "playbook": pb,
            "narratives": narrative.watch(market, pb),
            "coverage": back["coverage"], "cap": cap}


@route("PUT", "/api/signals/{key}")
def api_set_signal(req, m, q, body):
    b = body or {}
    try:
        if "ticked" in b:
            return playbook.set_manual(m["key"], ticked=list(b.get("ticked") or []))
        value = b.get("value")
        if value not in (None, ""):
            value = _float(value, "That figure", -1000, 1000)
        return playbook.set_manual(m["key"], value=value)
    except KeyError:
        raise ApiError("That signal is filled in automatically.") from None


@route("PUT", "/api/plans/{topic}")
def api_save_plan(req, m, q, body):
    topic = m["topic"]
    if topic not in ("ai", "crash", "drift"):
        raise ApiError("Unknown plan.")
    text = str((body or {}).get("body") or "")[:4000]
    with db.tx() as c:
        c.execute("INSERT INTO plans(topic,body,updated_at) VALUES(?,?,?) ON CONFLICT(topic) DO "
                  "UPDATE SET body=excluded.body, updated_at=excluded.updated_at",
                  (topic, text, db.now()))
    return {"ok": True, "updated_at": db.now()}


# ============================================================================ markets

@route("GET", "/api/markets")
def api_markets(req, m, q, body):
    sl = allocation.sleeves()
    pos = portfolio.positions()
    tot = portfolio.totals(pos)
    view = {r["id"]: r for r in allocation.view(pos, tot)["sleeves"]}
    out = []
    for key in catalogue.visible():
        ref = catalogue.REFERENCE[key]
        sk = store.ref_key(key)
        pts = store.points(sk)
        meta = store.meta(sk) or {}
        words = ref.get("sleeve_words") or []
        linked = [s for s in sl if words and any(w in f" {s['name'].lower()} " for w in words)]
        vals = [v for _, v in pts]
        dd = mathx.drawdowns(vals, 252)[-1] if len(vals) > 60 else None
        out.append({
            "key": key, "label": ref["label"], "unit": ref["unit"], "group": ref["group"],
            "blurb": ref["blurb"], "why": ref["why"],
            "value": pts[-1][1] if pts else None, "as_of": pts[-1][0] if pts else None,
            "changes": {k: (mathx.points_change(pts, d) if ref["unit"] == "%" else
                            mathx.change_over(pts, d))
                        for k, d in (("1m", 30), ("1y", 365), ("5y", 1826))},
            "changes_in_points": ref["unit"] == "%",
            "drawdown": dd,
            # A fall from the high means something for a price, not for a yield, a
            # spread or the VIX, where lower is the calm direction.
            "priced": ref["group"] not in ("stress",) and ref["unit"] != "%" and key != "GBPUSD",
            "spark": [[d, round(v, 6)] for d, v in mathx.thin(mathx.since(pts, 365), 90)],
            "source": meta.get("source"), "fetch_error": None if pts else meta.get("last_error"),
            "linked": [{"name": s["name"], "actual": (view.get(s["id"]) or {}).get("actual")}
                       for s in linked],
        })
    return {"series": out, "narratives": narrative.markets(out, signals.evaluate()["lights"])}


@route("GET", "/api/series")
def api_series(req, m, q, body):
    keys = [k for k in (q.get("keys") or "").split(",") if k][:10]
    days = min(_int(q.get("days") or 365, "period"), 5 * 366)
    since = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    out = []
    for k in keys:
        if not re.fullmatch(r"(REF|SEC|FX):[A-Za-z0-9.^=\-]+", k):
            continue
        pts = store.points(k, since)
        label = catalogue.REFERENCE.get(k[4:], {}).get("label") if k.startswith("REF:") else k[4:]
        if q.get("rebase"):
            pts = mathx.rebase(pts)
        out.append({"key": k, "label": label, "points": [[d, round(v, 4)] for d, v in mathx.thin(pts, 500)]})
    return {"series": out}


# ============================================================================ activity

@route("GET", "/api/activity")
def api_activity(req, m, q, body):
    trades = db.rows("SELECT t.traded_on, t.side, t.quantity, t.value_gbp, t.fees_gbp, t.source,"
                     " i.name, i.symbol, i.id AS instrument_id, p.name AS platform FROM trades t"
                     " LEFT JOIN instruments i ON i.id=t.instrument_id JOIN platforms p ON"
                     " p.id=t.platform_id ORDER BY t.traded_on DESC, t.id DESC LIMIT 400")
    since = (dt.date.today() - dt.timedelta(days=365)).isoformat()
    by_holding = db.rows("SELECT i.name, SUM(d.amount_gbp) AS amount FROM dividends d LEFT JOIN "
                         "instruments i ON i.id=d.instrument_id WHERE d.paid_on>=? GROUP BY i.id "
                         "ORDER BY amount DESC LIMIT 12", (since,))
    moves = db.rows("SELECT c.*, p.name AS platform FROM cash_moves c JOIN platforms p ON "
                    "p.id=c.platform_id ORDER BY happened_on DESC LIMIT 60")
    fees = db.scalar("SELECT SUM(fees_gbp) FROM trades WHERE traded_on>=?", (since,))
    return {"trades": trades, "dividends": portfolio.dividends_by_month(24),
            "dividends_by_holding": by_holding, "isa": isa.allowance(),
            "isa_history": isa.history(6), "moves": moves, "fees_12m": fees,
            "money_in": [[d, v] for d, v in portfolio.money_in()]}


# ============================================================================ settings

@route("GET", "/api/settings")
def api_settings(req, m, q, body):
    plats = portfolio.platforms_summary()
    for p in plats:
        p["has_key"] = bool(trading212.credentials(p["id"])) if p["provider"] == "trading212" else None
        p["monzo_linked"] = monzo.linked(p["id"]) if p["provider"] == "bank" else False
        p["cash_estimate"] = freetrade.cash_estimate(p["id"]) if p["provider"] == "freetrade" else None
    wanted = set(store.wanted_keys())
    meta = [r for r in db.rows("SELECT key, source, last_ok, last_error, fetched_at FROM series_meta "
                               "ORDER BY key") if r["key"] in wanted]
    return {
        "settings": config.settings.all(), "platforms": plats, "sleeves": allocation.sleeves(),
        "rules": db.rows("SELECT * FROM rules ORDER BY id"),
        "sources": {"ok": sum(1 for r in meta if r["last_ok"] and not r["last_error"]),
                    "failing": [r for r in meta if r["last_error"]][:40],
                    "total": len(meta), "browser_tls": net.have_browser_tls(),
                    "browser_tls_problem": net.browser_tls_problem()},
        "vault": security.storage_backend(), "data_dir": str(config.data_dir()),
        "version": config.APP_VERSION, "sample": sample.loaded(),
        "plan_loaded": db.get_meta("plan_loaded"),
    }


SETTABLE = {"user_name", "isa_allowance", "fscs_limit", "refresh_on_open", "stooq_key",
            "check_for_updates", "auto_download_updates", "update_url", "toured", "theme",
            "hide_amounts"}


@route("PATCH", "/api/settings")
def api_patch_settings(req, m, q, body):
    incoming = {k: v for k, v in (body or {}).items() if k in SETTABLE}
    if "update_url" in incoming:
        url = str(incoming["update_url"] or "").strip()
        if url and not url.lower().startswith("https://"):
            raise ApiError("The update address has to start with https://")
        incoming["update_url"] = url
    for k in ("isa_allowance", "fscs_limit"):
        if k in incoming:
            incoming[k] = _float(incoming[k], "That limit", 0, 10_000_000)
    if "user_name" in incoming:
        incoming["user_name"] = str(incoming["user_name"] or "").strip()[:60]
    if "theme" in incoming and incoming["theme"] not in ("clock", "system", "light", "dark"):
        raise ApiError("Unknown theme.")
    if "hide_amounts" in incoming:
        incoming["hide_amounts"] = bool(incoming["hide_amounts"])
    if "stooq_key" in incoming:
        incoming["stooq_key"] = re.sub(r"[^A-Za-z0-9]", "", str(incoming["stooq_key"] or ""))[:80]
    config.settings.update(incoming)
    if {"update_url", "check_for_updates"} & set(incoming):
        updates.start_check(force=True)
    return {"ok": True, "settings": config.settings.all()}


PROVIDERS = {"freetrade", "trading212", "bank", "card", "other"}
WRAPPERS = ("isa", "gia", "sipp", "lisa", "cash")


@route("POST", "/api/platforms")
def api_add_platform(req, m, q, body):
    b = body or {}
    name = str(b.get("name") or "").strip()
    provider = b.get("provider") if b.get("provider") in PROVIDERS else "other"
    if not name:
        raise ApiError("Give the platform a name, e.g. “Freetrade ISA”.")
    bank = provider in ("bank", "card")
    wrapper = "cash" if bank else (b.get("wrapper") if b.get("wrapper") in WRAPPERS else "isa")
    flexible = 0 if bank else (1 if (b.get("flexible") if b.get("flexible") is not None
                                     else provider == "trading212") else 0)
    # A bank account's cash sits beside the portfolio unless asked to count in the plan.
    in_plan = 1 if (b.get("in_plan", not bank) and provider != "card") else 0
    cash = _float(b.get("cash"), "The balance", -1_000_000, 100_000_000, allow_none=True)
    if provider == "card":
        owed = _float(b.get("owed"), "What you owe", 0, 10_000_000, allow_none=True)
        cash = -owed if owed is not None else None
    with db.tx() as c:
        cur = c.execute("INSERT INTO platforms(name,provider,wrapper,flexible,limit_gbp,in_plan,cash,"
                        "cash_as_of,cash_source,sort) VALUES(?,?,?,?,?,?,?,?,?,"
                        "(SELECT COALESCE(MAX(sort),0)+1 FROM platforms))",
                        (name, provider, wrapper, flexible,
                         _float(b.get("limit"), "The limit", 0, allow_none=True), in_plan, cash,
                         db.now() if cash is not None else None, "manual" if cash is not None else None))
    return {"ok": True, "id": cur.lastrowid}


@route("PATCH", "/api/platforms/{pid}")
def api_patch_platform(req, m, q, body):
    pid = _int(m["pid"])
    b = body or {}
    sets, vals = [], []
    if "name" in b:
        name = str(b["name"] or "").strip()
        if not name:
            raise ApiError("A platform needs a name.")
        sets.append("name=?"), vals.append(name)
    if "flexible" in b:
        sets.append("flexible=?"), vals.append(1 if b["flexible"] else 0)
    if "in_plan" in b:
        sets.append("in_plan=?"), vals.append(1 if b["in_plan"] else 0)
    if "wrapper" in b and b["wrapper"] in WRAPPERS:
        sets.append("wrapper=?"), vals.append(b["wrapper"])
    if "limit" in b:
        sets.append("limit_gbp=?"), vals.append(_float(b["limit"], "The limit", 0, allow_none=True))
    if "owed" in b:                     # a credit card: what is owed, kept as a negative balance
        owed = _float(b["owed"], "What you owe", 0, 10_000_000, allow_none=True)
        b = dict(b, cash=(-owed if owed is not None else None))
    if "cash" in b:
        cash = _float(b["cash"], "Cash", -1_000_000, 100_000_000, allow_none=True)
        sets += ["cash=?", "cash_as_of=?", "cash_source=?"]
        vals += [cash, db.now(), "manual" if cash is not None else None]
    if not sets:
        raise ApiError("Nothing to change.")
    db.execute(f"UPDATE platforms SET {', '.join(sets)} WHERE id=?", (*vals, pid))
    return {"ok": True}


@route("DELETE", "/api/platforms/{pid}")
def api_delete_platform(req, m, q, body):
    pid = _int(m["pid"])
    trading212.forget_credentials(pid)
    db.execute("DELETE FROM platforms WHERE id=?", (pid,))
    return {"ok": True}


@route("POST", "/api/platforms/{pid}/t212")
def api_t212_connect(req, m, q, body):
    pid = _int(m["pid"])
    b = body or {}
    key, secret = str(b.get("api_key") or "").strip(), str(b.get("api_secret") or "").strip()
    if not key:
        raise ApiError("Paste the API key first.")
    try:
        out = trading212.connect(pid, key, secret)
    except trading212.T212Error as e:
        raise ApiError(str(e)) from None
    db.execute("UPDATE platforms SET provider='trading212' WHERE id=?", (pid,))
    store.start_refresh(before=_sync_brokers)
    return out


@route("POST", "/api/platforms/{pid}/monzo")
def api_monzo_begin(req, m, q, body):
    b = body or {}
    try:
        return monzo.begin(_int(m["pid"]), b.get("client_id"), b.get("client_secret"),
                           req.server.server_address[1])
    except monzo.MonzoError as e:
        raise ApiError(str(e)) from None


@route("DELETE", "/api/platforms/{pid}/monzo")
def api_monzo_forget(req, m, q, body):
    monzo.forget(_int(m["pid"]))
    return {"ok": True}


@route("DELETE", "/api/platforms/{pid}/t212")
def api_t212_forget(req, m, q, body):
    trading212.forget_credentials(_int(m["pid"]))
    return {"ok": True}


@route("POST", "/api/platforms/{pid}/import")
def api_import(req, m, q, body):
    pid = _int(m["pid"])
    if not db.one("SELECT 1 FROM platforms WHERE id=?", (pid,)):
        raise ApiError("That platform doesn't exist.")
    if not isinstance(body, (bytes, bytearray)) or not body:
        raise ApiError("No file arrived.")
    try:
        rep = freetrade.import_csv(pid, bytes(body))
    except freetrade.NotFreetrade as e:
        raise ApiError(str(e)) from None
    rep["cash_estimate"] = freetrade.cash_estimate(pid)
    store.start_refresh()
    return rep


# ---- sleeves

def _sleeve_fields(b: dict, partial: bool) -> dict:
    out = {}
    if "name" in b or not partial:
        name = str(b.get("name") or "").strip()
        if not name:
            raise ApiError("A sleeve needs a name.")
        out["name"] = name[:60]
    if "target" in b or not partial:
        out["target"] = _float(b.get("target", 0), "The target", 0, 100)
    if "band" in b:
        out["band"] = _float(b["band"], "The band", allocation.BAND_MIN, allocation.BAND_MAX,
                             allow_none=True)
    if "ai_share" in b:
        out["ai_share"] = _float(b["ai_share"], "The AI share", 0, 100, allow_none=True)
    if "is_cash" in b:
        out["is_cash"] = 1 if b["is_cash"] else 0
    if "colour" in b:
        c = str(b["colour"] or "")
        out["colour"] = c if re.fullmatch(r"#[0-9a-fA-F]{6}", c) else None
    return out


@route("POST", "/api/sleeves")
def api_add_sleeve(req, m, q, body):
    f = _sleeve_fields(body or {}, partial=False)
    if db.one("SELECT 1 FROM sleeves WHERE name=?", (f["name"],)):
        raise ApiError("There's already a sleeve with that name.")
    with db.tx() as c:
        if f.get("is_cash"):
            c.execute("UPDATE sleeves SET is_cash=0")
        cols = list(f) + ["sort"]
        cur = c.execute(f"INSERT INTO sleeves({','.join(cols)}) VALUES({','.join('?' * len(cols))})",
                        (*f.values(), (c.execute("SELECT COALESCE(MAX(sort),0)+1 FROM sleeves")
                                       .fetchone()[0])))
    return {"ok": True, "id": cur.lastrowid}


@route("PATCH", "/api/sleeves/{sid}")
def api_patch_sleeve(req, m, q, body):
    sid = _int(m["sid"])
    f = _sleeve_fields(body or {}, partial=True)
    if not f:
        raise ApiError("Nothing to change.")
    if "name" in f and db.one("SELECT 1 FROM sleeves WHERE name=? AND id!=?", (f["name"], sid)):
        raise ApiError("There's already a sleeve with that name.")
    with db.tx() as c:
        if f.get("is_cash"):
            c.execute("UPDATE sleeves SET is_cash=0 WHERE id!=?", (sid,))
        c.execute(f"UPDATE sleeves SET {', '.join(f'{k}=?' for k in f)} WHERE id=?", (*f.values(), sid))
    return {"ok": True}


@route("DELETE", "/api/sleeves/{sid}")
def api_delete_sleeve(req, m, q, body):
    sid = _int(m["sid"])
    move_to = (body or {}).get("move_to") if isinstance(body, dict) else None
    with db.tx() as c:
        c.execute("UPDATE instruments SET sleeve_id=? WHERE sleeve_id=?",
                  (_int(move_to) if move_to else None, sid))
        c.execute("DELETE FROM sleeves WHERE id=?", (sid,))
    return {"ok": True}


# ---- rules and look-through

@route("POST", "/api/rules")
def api_add_rule(req, m, q, body):
    b = body or {}
    kind = b.get("kind")
    if kind not in plan.KINDS:
        raise ApiError("Unknown kind of rule.")
    subject = str(b.get("subject") or "").strip() or None
    if kind != "ai_cap" and not subject:
        raise ApiError("Say which company or theme the rule is about.")
    trig = _float(b.get("trigger"), "The trigger", 0.1, 100)
    tgt = _float(b.get("target"), "The level to bring it back to", 0, 100, allow_none=True)
    if tgt is not None and tgt >= trig:
        raise ApiError("The level to trim back to has to be below the trigger.")
    with db.tx() as c:
        cur = c.execute("INSERT INTO rules(kind,subject,trigger_pct,target_pct,basis,note) "
                        "VALUES(?,?,?,?,?,?)", (kind, subject, trig, tgt,
                                                "true" if b.get("basis") == "true" else "direct",
                                                str(b.get("note") or "")[:300] or None))
    return {"ok": True, "id": cur.lastrowid}


@route("DELETE", "/api/rules/{rid}")
def api_delete_rule(req, m, q, body):
    db.execute("DELETE FROM rules WHERE id=?", (_int(m["rid"]),))
    return {"ok": True}


@route("POST", "/api/lookthrough")
def api_lookthrough(req, m, q, body):
    b = body or {}
    fund = _int(b.get("fund_id"), "fund")
    company = str(b.get("company") or "").strip()
    if not company:
        raise ApiError("Which company?")
    weight = _float(b.get("weight"), "The weight", 0, 100, allow_none=True)
    with db.tx() as c:
        if weight is None:
            c.execute("DELETE FROM lookthrough WHERE fund_id=? AND lower(company)=lower(?)", (fund, company))
        else:
            c.execute("INSERT INTO lookthrough(fund_id,company,weight,as_of) VALUES(?,?,?,?) "
                      "ON CONFLICT(fund_id,company) DO UPDATE SET weight=excluded.weight,"
                      " as_of=excluded.as_of", (fund, company, weight, db.today()))
    return {"ok": True}


# ---- plan files, sample

@route("POST", "/api/plan/import")
def api_plan_import(req, m, q, body):
    try:
        return {"ok": True, "report": plan.import_plan(body if isinstance(body, dict) else (body or b""))}
    except plan.PlanError as e:
        raise ApiError(str(e)) from None


@route("GET", "/api/plan/questions")
def api_plan_questions(req, m, q, body):
    return {"questions": planbuilder.QUESTIONS}


@route("POST", "/api/plan/build")
def api_plan_build(req, m, q, body):
    """A draft only: nothing is saved until the person chooses to use it."""
    return planbuilder.build((body or {}).get("answers") or {})


@route("GET", "/api/export/xlsx")
def api_export_xlsx(req, m, q, body):
    try:
        blob = export.build()
    except Exception as e:
        db.log("export.error", {"detail": str(e)})
        raise ApiError("Couldn't build the spreadsheet. The details are in the log inside the "
                       f"{config.APP_NAME} data folder.") from None
    return {"_file": blob, "_name": export.filename(),
            "_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}


@route("GET", "/api/plan/export")
def api_plan_export(req, m, q, body):
    blob = json.dumps(plan.export_plan(), indent=2).encode("utf-8")
    return {"_file": blob, "_name": f"{config.APP_FILE_NAME} plan.json", "_type": "application/json"}


@route("POST", "/api/sample/load")
def api_sample_load(req, m, q, body):
    out = sample.load()
    store.start_refresh()
    return out


@route("POST", "/api/sample/remove")
def api_sample_remove(req, m, q, body):
    return sample.remove()


# ============================================================================ refreshing

def _sync_brokers():
    freetrade.rebuild_all()          # bills that matured since the last import drop out
    for p in db.rows("SELECT id, name FROM platforms WHERE provider='bank'"):
        if monzo.linked(p["id"]):
            try:
                store.JOB.update(current=f"{p['name']}: balance")
                monzo.sync(p["id"])
            except monzo.MonzoError as e:
                store.JOB["errors"].append({"key": p["name"], "message": str(e)})
    for p in db.rows("SELECT id FROM platforms WHERE provider='trading212'"):
        if not trading212.credentials(p["id"]):
            continue
        try:
            trading212.sync(p["id"], progress=lambda msg: store.JOB.update(current=msg))
        except trading212.T212Error as e:
            store.JOB["errors"].append({"key": "Trading 212", "message": str(e)})


@route("POST", "/api/refresh")
def api_refresh(req, m, q, body):
    started = store.start_refresh(force=bool((body or {}).get("force")), before=_sync_brokers)
    return {"started": started, "state": store.job_state()}


@route("GET", "/api/refresh")
def api_refresh_state(req, m, q, body):
    return store.job_state()


# ============================================================================ updates, links

@route("GET", "/api/update")
def api_update_state(req, m, q, body):
    return updates.state()


@route("POST", "/api/update/check")
def api_update_check(req, m, q, body):
    return updates.check(force=True)


@route("POST", "/api/update/download")
def api_update_download(req, m, q, body):
    if not updates.state().get("download"):
        raise ApiError("There's nothing to download — check for an update first.")
    updates.start_download()
    return updates.state()


@route("POST", "/api/update/dismiss")
def api_update_dismiss(req, m, q, body):
    updates.dismiss((body or {}).get("version"))
    return updates.state()


@route("POST", "/api/update/reveal")
def api_update_reveal(req, m, q, body):
    """Open the folder the verified download is in. The folder, never a path the page
    supplies: a route that opens whatever it is handed would run an .exe as happily
    as it opens a folder."""
    return _open_path(updates.downloads_dir())


@route("POST", "/api/open-data-folder")
def api_open_data(req, m, q, body):
    return _open_path(config.data_dir())


def _open_path(target: pathlib.Path) -> dict:
    import subprocess
    import sys
    try:
        if os.name == "nt":
            os.startfile(str(target))                # noqa: S606 — a folder we chose
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target)])
        return {"opened": True, "path": str(target)}
    except Exception as e:
        return {"opened": False, "problem": str(e), "path": str(target)}


@route("POST", "/api/open-url")
def api_open_url(req, m, q, body):
    url = str((body or {}).get("url") or "").strip()
    if not url.lower().startswith(("https://", "http://", "mailto:")):
        raise ApiError("Only web links and email addresses can be opened.")
    if any(ch in url for ch in "\r\n\x00"):
        raise ApiError("That link isn't valid.")
    import webbrowser
    try:
        webbrowser.open(url)
        return {"opened": True}
    except Exception as e:
        return {"opened": False, "problem": str(e), "url": url}


# ============================================================================ plumbing

class Handler(BaseHTTPRequestHandler):
    server_version = f"{config.APP_SLUG}/{config.APP_VERSION}"
    protocol_version = "HTTP/1.1"
    MAX_BODY = 25 * 1024 * 1024

    def log_message(self, fmt, *args):
        if os.environ.get("WHISKERS_VERBOSE"):
            super().log_message(fmt, *args)

    def _send(self, status: int, payload: bytes, ctype: str, extra: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for k, v in (extra or {}).items():
            # HTTP headers are latin-1; an em dash in a filename once broke a whole
            # download in Mittens & Pence with nothing in the log to say why.
            self.send_header(k, str(v).encode("latin-1", "replace").decode("latin-1"))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def _json(self, obj, status=200):
        self._send(status, json.dumps(obj, default=str).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > self.MAX_BODY:
            raise ApiError("That file is too big.", 413)
        raw = self.rfile.read(length) if length else b""
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip()
        if ctype == "application/json" and raw:
            try:
                return json.loads(raw)
            except ValueError:
                raise ApiError("That request wasn't valid JSON.") from None
        return raw

    # -- who may talk to us ------------------------------------------------
    # Binding to 127.0.0.1 keeps other computers out; it does not keep other web pages
    # out. Every page open in a browser on this machine can send requests here. So:
    #   Host must be the loopback address (a DNS-rebound domain carries its own name);
    #   a browser request that says it is cross-site or same-site is refused;
    #   anything that changes state must come from our own origin — this port, not
    #   merely this machine. "Origin: null" (a sandboxed frame) is refused outright.
    # A request with no Origin at all is a tool (a test, curl, the desktop shell):
    # browsers always send one on a cross-site POST, so it cannot be a page.
    LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}

    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").strip()
        if not host:
            return True
        name = host.rsplit(":", 1)[0] if not host.startswith("[") else host.split("]")[0] + "]"
        return name.lower() in self.LOCAL_HOSTS

    def _origin_ok(self, method: str) -> bool:
        site = (self.headers.get("Sec-Fetch-Site") or "").strip().lower()
        if site in ("cross-site", "same-site"):
            return False
        if method in ("GET", "HEAD"):
            return True
        origin = (self.headers.get("Origin") or "").strip()
        if not origin:
            return True
        if origin.lower() == "null":
            return False
        try:
            parsed = urllib.parse.urlparse(origin)
            port = parsed.port
        except ValueError:
            return False
        return ((parsed.hostname or "").lower() in self.LOCAL_HOSTS
                and port == self.server.server_address[1])

    def _dispatch(self, method: str):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        q = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
        # The link in Monzo's sign-in email is always a cross-site navigation, so this one
        # address skips the same-site check; the one-time state it must carry is the guard.
        if path == monzo.CALLBACK_PATH and method == "GET" and self._host_ok():
            return self._monzo_callback(q)
        if not self._host_ok() or not self._origin_ok(method):
            return self._json({"error": f"{config.APP_NAME} only answers this computer."}, 403)
        if config.phone_mode() and path.startswith("/api/") and not hmac.compare_digest(
                (self.headers.get("X-Whiskers-Key") or "").encode(), config.phone_key().encode()):
            return self._json({"error": "Open Whiskers from its own start-up link: on a phone, "
                                        "the app answers only its own browser tab."}, 401)
        if not path.startswith("/api/"):
            if method not in ("GET", "HEAD"):
                return self._json({"error": "Not found"}, 404)
            return self._serve_static(path)
        for meth, rx, fn in ROUTES:
            if meth != method:
                continue
            mt = rx.match(path)
            if not mt:
                continue
            try:
                body = self._read_body() if method in ("POST", "PATCH", "PUT", "DELETE") else None
                out = fn(self, mt.groupdict(), q, body)
                if isinstance(out, dict) and "_file" in out:
                    name = out.get("_name", "download")
                    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
                    ascii_name = re.sub(r'[\\"]', "", ascii_name) or "download"
                    quoted = urllib.parse.quote(name, safe="")
                    return self._send(200, out["_file"], out.get("_type", "application/octet-stream"),
                                      {"Content-Disposition":
                                       f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quoted}'})
                return self._json(out)
            except ApiError as e:
                return self._json({"error": e.message}, e.status)
            except Exception as e:
                db.log("api.error", {"path": path, "error": str(e),
                                     "trace": traceback.format_exc()[-3000:]})
                if os.environ.get("WHISKERS_VERBOSE"):
                    traceback.print_exc()
                return self._json({"error": f"Something went wrong: {e}. The details are in the "
                                            f"log inside the {config.APP_NAME} data folder."}, 500)
        self._json({"error": f"No route for {method} {path}"}, 404)

    def _monzo_callback(self, q: dict):
        try:
            pid = monzo.complete(q.get("state", ""), q.get("code", ""), q.get("error"))
            name = db.scalar("SELECT name FROM platforms WHERE id=?", (pid,), "Monzo")
            title, text = f"{name} is linked", (
                "One more step: open the Monzo app, tap the request waiting there and allow it. "
                "Then go back to Whiskers and press Refresh. You can close this tab.")
        except monzo.MonzoError as e:
            title, text = "Monzo wasn't linked", str(e)
        esc = lambda s: str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")  # noqa: E731
        page = (f"<!doctype html><meta charset=utf-8><title>{esc(title)}</title>"
                f"<body style='font:16px system-ui;max-width:34em;margin:4em auto;padding:0 1em'>"
                f"<h1 style='font-size:1.4em'>{esc(title)}</h1><p>{esc(text)}</p></body>")
        self._send(200, page.encode("utf-8"), "text/html; charset=utf-8",
                   {"Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'"})

    def _serve_static(self, path: str):
        root = _static_dir().resolve()
        rel = urllib.parse.unquote(path).lstrip("/") or "index.html"
        try:
            target = (root / rel).resolve()
        except (OSError, ValueError):
            target = root / "index.html"
        # is_relative_to, not a string prefix: "static-evil/x" starts with "static".
        if not target.is_relative_to(root) or not target.is_file():
            target = root / "index.html"
            if not target.is_file():
                return self._send(404, b"The app's interface files are missing.", "text/plain")
        ctype, _ = mimetypes.guess_type(str(target))
        if target.suffix == ".js":
            ctype = "text/javascript"
        elif target.suffix == ".svg":
            ctype = "image/svg+xml"
        elif target.suffix == ".webmanifest":
            ctype = "application/manifest+json"
        self._send(200, target.read_bytes(), (ctype or "application/octet-stream") +
                   ("; charset=utf-8" if (ctype or "").startswith("text/") else ""),
                   {"Content-Security-Policy":
                    "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                    "script-src 'self'; connect-src 'self'; frame-ancestors 'none'"})

    def do_GET(self):
        self._dispatch("GET")

    def do_HEAD(self):
        self._dispatch("HEAD")

    def do_POST(self):
        self._dispatch("POST")

    def do_PATCH(self):
        self._dispatch("PATCH")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_DELETE(self):
        self._dispatch("DELETE")


def _free_port(preferred: int = config.PREFERRED_PORT) -> int:
    for port in [preferred] + list(range(preferred + 1, preferred + 40)):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def serve(port: int | None = None, block: bool = True):
    db.init()
    port = port or _free_port()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    httpd.daemon_threads = True
    if block:
        httpd.serve_forever()
        return httpd, port
    threading.Thread(target=httpd.serve_forever, daemon=True, name="http").start()
    return httpd, port
