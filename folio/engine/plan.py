"""A plan is everything a person decides, as opposed to everything a broker reports:
the sleeves and their targets, the rules, which shares count as one company, which
holdings form one theme, and per-holding choices like an AI share or a price symbol.

It travels as a small JSON file so it can be set up once, backed up, and loaded into
another copy — and so a personal allocation never has to live in the app's public source
code. Importing merges: sleeves and platforms are matched by name, rules by what they
are about, and nothing already there is deleted.
"""

from __future__ import annotations

import json

from .. import db
from . import allocation
from ..brokers import symbols

FORMAT = 1
KINDS = {"company_cap", "theme_cap", "ai_cap"}


class PlanError(ValueError):
    pass


def _pct(v, what: str, allow_none: bool = False) -> float | None:
    if v is None and allow_none:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise PlanError(f"{what} should be a number, not {v!r}") from None
    if not 0 <= f <= 100:
        raise PlanError(f"{what} should be between 0 and 100, not {f:g}")
    return f


def import_plan(data: dict | str | bytes) -> dict:
    if isinstance(data, (bytes, str)):
        try:
            data = json.loads(data)
        except ValueError:
            raise PlanError("That file isn't a plan — it isn't valid JSON.") from None
    if not isinstance(data, dict) or data.get("whiskers_plan") is None:
        raise PlanError("That file isn't a Whiskers plan.")
    if int(data["whiskers_plan"]) > FORMAT:
        raise PlanError("That plan was made by a newer version of Whiskers. Update first.")
    # Check every holding setting before writing anything, so a bad line can't leave
    # half a plan behind.
    instruments = {}
    for ident, conf in (data.get("instruments") or {}).items():
        if not isinstance(conf, dict):
            raise PlanError(f"The settings for {ident} aren't in the expected form.")
        conf = dict(conf)
        if "ai_share" in conf:
            conf["ai_share"] = _pct(conf["ai_share"], f"{ident}'s AI share", True)
        instruments[symbols.plan_key(ident)] = conf
    rep = {"sleeves": 0, "rules": 0, "platforms": 0, "instruments": 0, "companies": 0, "removed": []}
    with db.tx() as c:
        for i, s in enumerate(data.get("sleeves") or []):
            name = str(s.get("name") or "").strip()
            if not name:
                raise PlanError("Every sleeve needs a name.")
            target = _pct(s.get("target", 0), f"The target for {name}")
            band = s.get("band")
            if band is not None:
                try:
                    band = float(band)
                except (TypeError, ValueError):
                    raise PlanError(f"The band for {name} should be a number, not {band!r}") from None
                if not allocation.BAND_MIN <= band <= allocation.BAND_MAX:
                    raise PlanError(f"The band for {name} should be between {allocation.BAND_MIN:g} "
                                    f"and {allocation.BAND_MAX:g}, not {band:g}")
            c.execute("INSERT INTO sleeves(name,target,band,ai_share,is_cash,colour,sort) "
                      "VALUES(?,?,?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET target=excluded.target,"
                      " band=excluded.band, ai_share=excluded.ai_share, is_cash=excluded.is_cash,"
                      " colour=COALESCE(excluded.colour, sleeves.colour), sort=excluded.sort",
                      (name, target, band, _pct(s.get("ai_share"), f"{name}'s AI share", True),
                       1 if s.get("is_cash") else 0, s.get("colour"), i))
            rep["sleeves"] += 1
        if data.get("replace_sleeves"):
            # The plan is the whole list: sleeves it doesn't name (a template's "Global
            # core" beside the plan's "Global core index", say) would otherwise leave the
            # targets adding up to far more than 100.
            named = [str(s.get("name") or "").strip() for s in data.get("sleeves") or []]
            for old in c.execute("SELECT id, name FROM sleeves").fetchall():
                if old["name"] not in named:
                    c.execute("UPDATE instruments SET sleeve_id=NULL WHERE sleeve_id=?", (old["id"],))
                    c.execute("DELETE FROM sleeves WHERE id=?", (old["id"],))
                    rep["removed"].append(old["name"])
        for r in data.get("rules") or []:
            kind = r.get("kind")
            if kind not in KINDS:
                raise PlanError(f"Unknown rule kind {kind!r}")
            subject = (r.get("subject") or "").strip() or None
            if kind != "ai_cap" and not subject:
                raise PlanError(f"A {kind} rule needs a subject.")
            c.execute("DELETE FROM rules WHERE kind=? AND COALESCE(lower(subject),'')=?",
                      (kind, (subject or "").lower()))
            c.execute("INSERT INTO rules(kind,subject,trigger_pct,target_pct,basis,note) "
                      "VALUES(?,?,?,?,?,?)",
                      (kind, subject, _pct(r.get("trigger"), "A rule's trigger"),
                       _pct(r.get("target"), "A rule's target", True),
                       "true" if r.get("basis") == "true" else "direct", r.get("note")))
            rep["rules"] += 1
        for i, p in enumerate(data.get("platforms") or []):
            name = str(p.get("name") or "").strip()
            if not name:
                continue
            row = c.execute("SELECT id FROM platforms WHERE name=?", (name,)).fetchone()
            bank = p.get("provider") == "bank"
            vals = (p.get("provider") or "other", p.get("wrapper") or ("cash" if bank else "isa"),
                    1 if p.get("flexible") else 0, p.get("limit"),
                    1 if p.get("in_plan", not bank) else 0)
            if row:
                c.execute("UPDATE platforms SET provider=?, wrapper=?, flexible=?, limit_gbp=?, "
                          "in_plan=? WHERE id=?", (*vals, row["id"]))
            else:
                c.execute("INSERT INTO platforms(name,provider,wrapper,flexible,limit_gbp,in_plan,sort) "
                          "VALUES(?,?,?,?,?,?,?)", (name, *vals, i))
            rep["platforms"] += 1
        companies = {symbols.alias_key(k): v for k, v in (data.get("companies") or {}).items()}
        themes = {symbols.alias_key(k): v for k, v in (data.get("themes") or {}).items()}
        if companies:
            have = c.execute("SELECT value FROM meta WHERE key='company_aliases'").fetchone()
            merged = json.loads(have["value"]) if have else {}
            merged.update(companies)
            c.execute("INSERT INTO meta(key,value) VALUES('company_aliases',?) ON CONFLICT(key) "
                      "DO UPDATE SET value=excluded.value", (json.dumps(merged),))
        for inst in c.execute("SELECT id, symbol, isin FROM instruments").fetchall():
            sym = symbols.alias_key(inst["symbol"])
            if sym in companies:
                c.execute("UPDATE instruments SET company=? WHERE id=?", (companies[sym], inst["id"]))
                rep["companies"] += 1
            if sym in themes:
                c.execute("UPDATE instruments SET theme=? WHERE id=?", (themes[sym], inst["id"]))
        known = {}
        for inst in c.execute("SELECT id, symbol, isin FROM instruments").fetchall():
            known.setdefault(symbols.plan_key(inst["symbol"]), inst["id"])
            if inst["isin"]:
                known.setdefault(symbols.plan_key(inst["isin"]), inst["id"])
        for ident, conf in instruments.items():
            iid = known.get(ident)
            if not iid:
                continue                      # waits in meta for the holding to arrive
            if "sleeve" in conf:
                sl = c.execute("SELECT id FROM sleeves WHERE name=?", (conf["sleeve"],)).fetchone()
                c.execute("UPDATE instruments SET sleeve_id=? WHERE id=?",
                          (sl["id"] if sl else None, iid))
            if "ai_share" in conf:
                c.execute("UPDATE instruments SET ai_share=? WHERE id=?", (conf["ai_share"], iid))
            if conf.get("market_symbol"):
                c.execute("UPDATE instruments SET market_symbol=? WHERE id=?",
                          (str(conf["market_symbol"]).strip(), iid))
            rep["instruments"] += 1
    if isinstance(data.get("targets"), dict):
        targets = {}
        for k, v in data["targets"].items():
            targets[symbols.plan_key(k)] = _pct(v, f"The target for {k}")
        db.set_meta("holding_targets", targets)
        rep["targets"] = len(targets)
    if isinstance(data.get("playbook"), dict):
        pb = dict(data["playbook"])
        manual = pb.pop("manual", None)
        db.set_meta("playbook", pb)
        rep["playbook"] = True
        if isinstance(manual, dict):
            from . import playbook as _pb
            keys = {x["key"] for x in _pb.SIGNALS if x["kind"] == "manual"}
            vals = _pb.manual_values()
            for k, v in manual.items():
                if k in keys and isinstance(v, dict):
                    vals[k] = {"value": v.get("value"), "ticked": v.get("ticked") or [],
                               "updated": str(v.get("updated") or db.today())[:10]}
            db.set_meta("manual_signals", vals)
    for topic, text in (data.get("plans") or {}).items():
        if topic in ("ai", "crash", "drift") and isinstance(text, str):
            with db.tx() as c:
                c.execute("INSERT INTO plans(topic,body,updated_at) VALUES(?,?,?) ON CONFLICT(topic) "
                          "DO UPDATE SET body=excluded.body, updated_at=excluded.updated_at",
                          (topic, text[:4000], db.now()))
    if instruments:
        waiting = db.get_meta("plan_instruments", {}) or {}
        waiting.update(instruments)
        db.set_meta("plan_instruments", waiting)
    if themes:
        merged = db.get_meta("theme_aliases", {}) or {}
        merged.update(themes)
        db.set_meta("theme_aliases", merged)
    # Last, once sleeves, themes and waiting holding settings are all in place, so a
    # holding the correction has to create lands in its sleeve like any other.
    corr = data.get("corrections")
    if isinstance(corr, dict) and corr.get("id") and isinstance(corr.get("holdings"), dict):
        rep["corrections"] = _apply_corrections(corr)
    rep["sorted"] = db.scalar("SELECT COUNT(DISTINCT p.instrument_id) FROM positions p JOIN instruments i "
                              "ON i.id=p.instrument_id WHERE i.sleeve_id IS NOT NULL", (), 0)
    rep["unsorted"] = db.scalar("SELECT COUNT(DISTINCT p.instrument_id) FROM positions p JOIN instruments i "
                                "ON i.id=p.instrument_id WHERE i.sleeve_id IS NULL", (), 0)
    db.set_meta("plan_loaded", {"at": db.now(), "about": str(data.get("about") or "")[:200]})
    return rep


def _apply_corrections(corr: dict) -> dict:
    """Set holdings on one platform to the share counts and costs the plan gives, once.
    Recorded by id, so loading the same plan again never undoes later trades."""
    from ..brokers import freetrade
    done = db.get_meta("applied_corrections", []) or []
    if corr["id"] in done:
        return {"skipped": "already applied"}
    plat = db.one("SELECT id FROM platforms WHERE name=?", (corr.get("platform"),))
    if not plat:
        return {"skipped": f"no platform called {corr.get('platform')!r} yet"}
    insts = db.rows("SELECT id, symbol, isin, market_symbol FROM instruments")
    changed, missing = [], []
    for ticker, want in corr["holdings"].items():
        key = symbols.plan_key(ticker)
        hit = next((i for i in insts if key in (symbols.plan_key(i["symbol"]),
                                                symbols.plan_key(i["isin"] or ""))), None)
        if not hit:
            # Even a zero is recorded when it can be: the file may arrive after the plan,
            # and a zero set today still outranks the file's older purchase.
            if not want.get("exchange"):
                if float(want.get("shares") or 0) <= 0:
                    continue
                missing.append(ticker)
                continue
            # Nothing in the file ever mentioned it (no trades, no dividends): make it.
            with db.tx() as c:
                iid = symbols.upsert_instrument(c, ticker, want["exchange"], want.get("name"), None, None)
            hit = {"id": iid}
        freetrade.set_holding(plat["id"], hit["id"], float(want.get("shares") or 0),
                              want.get("cost"), corr.get("note") or "Corrected from the plan file")
        changed.append(ticker)
    if not missing:
        db.set_meta("applied_corrections", done + [corr["id"]])
    return {"changed": changed, "missing": missing}


def export_plan() -> dict:
    sleeves = db.rows("SELECT * FROM sleeves ORDER BY sort, id")
    rules = db.rows("SELECT * FROM rules ORDER BY id")
    plats = db.rows("SELECT * FROM platforms WHERE provider != 'sample' ORDER BY sort, id")
    insts = db.rows("SELECT i.*, s.name AS sleeve FROM instruments i "
                    "LEFT JOIN sleeves s ON s.id=i.sleeve_id ORDER BY i.symbol")
    per = {}
    for i in insts:
        conf = {}
        if i["sleeve"]:
            conf["sleeve"] = i["sleeve"]
        if i["ai_share"] is not None:
            conf["ai_share"] = i["ai_share"]
        if i["market_symbol"] and i["market_symbol"] != symbols.market_symbol(i["symbol"], i["exchange"]):
            conf["market_symbol"] = i["market_symbol"]
        if conf:
            per[i["isin"] or i["symbol"]] = conf
    return {
        "whiskers_plan": FORMAT,
        "sleeves": [{"name": s["name"], "target": s["target"], "band": s["band"],
                     "ai_share": s["ai_share"], "is_cash": bool(s["is_cash"]),
                     "colour": s["colour"]} for s in sleeves],
        "rules": [{"kind": r["kind"], "subject": r["subject"], "trigger": r["trigger_pct"],
                   "target": r["target_pct"], "basis": r["basis"], "note": r["note"]}
                  for r in rules],
        "platforms": [{"name": p["name"], "provider": p["provider"], "wrapper": p["wrapper"],
                       "flexible": bool(p["flexible"]), "limit": p["limit_gbp"],
                       "in_plan": bool(p["in_plan"])} for p in plats],
        "companies": {(i["symbol"] or "").upper(): i["company"] for i in insts if i["company"]},
        "themes": {(i["symbol"] or "").upper(): i["theme"] for i in insts if i["theme"]},
        "instruments": per,
        "targets": db.get_meta("holding_targets", {}) or {},
        "playbook": db.get_meta("playbook", {}) or {},
        "plans": {r["topic"]: r["body"] for r in db.rows("SELECT topic, body FROM plans")},
    }
