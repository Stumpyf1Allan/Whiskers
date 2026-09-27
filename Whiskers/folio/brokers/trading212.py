"""Trading 212 — read-only, against the API as documented in September 2026.

READ PERMISSIONS ONLY. The key needs Account data, Portfolio, History and Metadata.
It never needs "Orders - Execute" or "Pies - Write": this app does not contain a single
request that could place, change or cancel an order, and a test fails the build if one
ever appears. Mittens & Pence once told Allan to tick every box on the strength of a
third party's setup page; he refused, and he was right. A missing permission is a 403;
a 401 is the credentials themselves.

Shapes, from docs.trading212.com (checked for this build, not assumed):

    GET /api/v0/equity/account/summary      1 req / 5 s
        {id, currency, totalValue,
         cash: {availableToTrade, inPies, reservedForOrders},
         investments: {currentValue, totalCost, realizedProfitLoss, unrealizedProfitLoss}}

    GET /api/v0/equity/positions            1 req / 1 s
        [{instrument: {ticker, name, isin, currency}, quantity, averagePricePaid,
          currentPrice,                     <- instrument currency (GBX for London)
          walletImpact: {currency, currentValue, totalCost, unrealizedProfitLoss,
                         fxImpact}}]        <- account currency, i.e. pounds

    GET /api/v0/equity/history/orders       6 req / min, pages of 50
        {items: [{order: {id, side, status, createdAt, instrument{...}, ...},
                  fill:  {id, filledAt, price, quantity, type,
                          walletImpact: {currency, netValue, fxRate, taxes[...]}}}],
         nextPagePath}

    GET /api/v0/equity/history/dividends    6 req / min
    GET /api/v0/equity/history/transactions 6 req / min

`walletImpact` is the useful part: Trading 212 has already converted each position into
pounds at its own rate, so a Trading 212 holding needs no currency arithmetic here at
all. Mittens & Pence's client reads order history from the pre-2025 flat shape and so
imports none of it from a current account; this one reads the nested shape first and
the flat one only as a fallback.
"""

from __future__ import annotations

import base64
import json
import time

from .. import db, net, security
from ..market import store
from . import symbols

LIVE = "https://live.trading212.com"
DEMO = "https://demo.trading212.com"
P_SUMMARY = "/api/v0/equity/account/summary"
P_POSITIONS = "/api/v0/equity/positions"
P_HISTORY = {"orders": "/api/v0/equity/history/orders",
             "dividends": "/api/v0/equity/history/dividends",
             "transactions": "/api/v0/equity/history/transactions"}
#: The documented limit for history is six requests a minute.
HISTORY_GAP = 10.5
MAX_PAGES = 60


class T212Error(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def _vault_ref(platform_id: int) -> str:
    return f"t212:{platform_id}"


def credentials(platform_id: int) -> dict | None:
    return security.get(_vault_ref(platform_id))


def save_credentials(platform_id: int, key: str, secret: str) -> None:
    security.put(_vault_ref(platform_id), {"api_key": (key or "").strip(),
                                           "api_secret": (secret or "").strip()})


def forget_credentials(platform_id: int) -> None:
    security.drop(_vault_ref(platform_id))


def explain(status: int | None, detail: str = "") -> str:
    if status == 403:
        return ("Trading 212 accepted the key but refused this request (403). That means a "
                "missing permission: the key needs the read permissions — Account data, "
                "Portfolio, History and Metadata. It does NOT need 'Orders - Execute'; this "
                "app never places an order. If those boxes are ticked, an IP restriction on "
                "the key is blocking this computer.")
    if status == 401:
        return ("Trading 212 rejected the key (401) — that is about the key itself, not "
                "permissions. Check: both values were pasted (newer keys have a key AND a "
                "secret); neither was clipped when copying; the key hasn't been deleted or "
                "regenerated since; and it belongs to your real account rather than a "
                "Practice one.")
    if status == 429:
        return "Trading 212 is rate-limiting. Wait a minute and try again."
    if status == 404:
        return ("Trading 212 didn't recognise the address asked for, which means their API "
                "has moved again. Use the Help button so it can be updated.")
    return f"Trading 212 didn't answer: {detail}" if detail else "Trading 212 didn't answer."


class Client:
    def __init__(self, key: str, secret: str, host: str = LIVE, style: str | None = None):
        self.key = (key or "").strip()
        self.secret = (secret or "").strip()
        self.host = host
        self.style = style or ("basic" if self.secret else "legacy")

    def _headers(self, style: str | None = None) -> dict:
        style = style or self.style
        if style == "basic" and self.secret:
            # b64encode never wraps lines, but a newline inside this header is a
            # documented cause of a 401 and invisible when you look at it — so be sure.
            raw = base64.b64encode(f"{self.key}:{self.secret}".encode()).decode()
            return {"Authorization": "Basic " + raw.replace("\n", ""),
                    "Accept": "application/json"}
        return {"Authorization": self.key, "Accept": "application/json"}

    def get(self, path: str, style: str | None = None, retries: int = 3):
        url = path if path.startswith("http") else self.host + path
        for attempt in range(retries + 1):
            try:
                body = net.get(url, headers=self._headers(style), timeout=20)
                return json.loads(body) if body else None
            except net.FetchError as e:
                if e.status == 429 and attempt < retries:
                    time.sleep(_wait_for(e.headers))
                    continue
                raise T212Error(explain(e.status, str(e)), e.status) from None
            except ValueError:
                raise T212Error("Trading 212 sent something that wasn't JSON") from None
        raise T212Error(explain(429), 429)

    def probe(self) -> dict:
        """Find the host and header style this key wants. A wrong scheme and a missing
        permission both fail, but need opposite advice, so every scheme is tried before
        anything is concluded about permissions — and a 403 stops the search, because
        it means the key itself was accepted."""
        styles = ["basic", "legacy"] if self.secret else ["legacy"]
        last = None
        for host in (LIVE, DEMO):
            for style in styles:
                self.host = host
                try:
                    summary = self.get(P_SUMMARY, style=style, retries=1)
                except T212Error as e:
                    last = e
                    if e.status == 403:
                        raise
                    continue
                self.style = style
                return {"host": host, "style": style, "summary": summary or {}}
        raise last or T212Error("Trading 212 didn't answer")

    def pages(self, kind: str, stop_when_seen=None):
        """Yield each page's items, newest first, politely. `stop_when_seen(items)`
        returning True ends the walk — a page we already have entirely means everything
        older is already stored too."""
        path = P_HISTORY[kind] + "?limit=50"
        for n in range(MAX_PAGES):
            if n:
                time.sleep(HISTORY_GAP)
            payload = self.get(path)
            items = (payload or {}).get("items") if isinstance(payload, dict) else payload
            if not items:
                return
            yield items
            if stop_when_seen and stop_when_seen(items):
                return
            nxt = (payload or {}).get("nextPagePath") if isinstance(payload, dict) else None
            if not nxt:
                return
            path = nxt if nxt.startswith("/") else "/" + nxt


def _wait_for(headers: dict) -> float:
    """Trading 212 says when the limit resets; believe it, within reason."""
    for k, v in (headers or {}).items():
        if k.lower() == "x-ratelimit-reset":
            try:
                return max(1.0, min(65.0, float(v) - time.time()))
            except ValueError:
                pass
    return HISTORY_GAP


def _num(v):
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------- parsing

def parse_position(p: dict) -> dict | None:
    """Current nested shape first; the pre-2025 flat shape as a fallback."""
    inst = p.get("instrument") or {}
    ticker = inst.get("ticker") or p.get("ticker") or ""
    qty = _num(p.get("quantity"))
    if not ticker or not qty:
        return None
    symbol, exchange = symbols.parse_t212(ticker)
    wi = p.get("walletImpact") or {}
    ccy = inst.get("currency") or ("GBX" if exchange == "LSE" else "USD" if exchange == "US" else None)
    return {"ticker": ticker, "symbol": symbol, "exchange": exchange,
            "name": inst.get("name"), "isin": inst.get("isin"), "currency": ccy,
            "quantity": qty,
            "price": _num(p.get("currentPrice")),
            "avg_price": _num(p.get("averagePricePaid") or p.get("averagePrice")),
            "value_gbp": _num(wi.get("currentValue")),
            "cost_gbp": _num(wi.get("totalCost")),
            "wallet_ccy": wi.get("currency")}


def parse_order(item: dict) -> dict | None:
    order, fill = item.get("order"), item.get("fill")
    if isinstance(order, dict):
        if not isinstance(fill, dict) or not fill:
            return None                        # never filled: cancelled or rejected
        inst = order.get("instrument") or {}
        ticker = inst.get("ticker") or order.get("ticker") or ""
        qty = abs(_num(fill.get("quantity")) or _num(order.get("filledQuantity")) or 0)
        wi = fill.get("walletImpact") or {}
        fees = sum(abs(_num(t.get("quantity")) or 0) for t in (wi.get("taxes") or []))
        side = (order.get("side") or "").upper()
        ftype = (fill.get("type") or "TRADE").upper()
        if ftype in ("FOP", "FOP_CORRECTION"):
            side = "TRANSFER_IN" if side != "SELL" else "TRANSFER_OUT"
        elif ftype != "TRADE":
            side = "CORPORATE"
        when = (fill.get("filledAt") or order.get("createdAt") or "")[:10]
        ref = f"{order.get('id')}:{fill.get('id')}"
        value = abs(_num(wi.get("netValue")) or 0) or None
        return {"ticker": ticker, "name": inst.get("name"), "isin": inst.get("isin"),
                "currency": inst.get("currency"), "side": side or "BUY", "quantity": qty,
                "price": _num(fill.get("price")), "value_gbp": value, "fees_gbp": fees,
                "date": when, "ref": ref}
    # the flat pre-2025 shape
    ticker = item.get("ticker") or ""
    q = _num(item.get("filledQuantity")) or 0
    if not ticker or not q or (item.get("status") or "FILLED").upper() != "FILLED":
        return None
    when = (item.get("dateExecuted") or item.get("dateModified") or item.get("dateCreated") or "")[:10]
    return {"ticker": ticker, "name": None, "isin": None, "currency": None,
            "side": "SELL" if q < 0 else "BUY", "quantity": abs(q),
            "price": _num(item.get("fillPrice")),
            "value_gbp": abs(_num(item.get("fillCost")) or _num(item.get("fillResult")) or 0) or None,
            "fees_gbp": sum(abs(_num(t.get("quantity")) or 0) for t in (item.get("taxes") or [])),
            "date": when, "ref": str(item.get("id") or "")}


TX_KIND = {"DEPOSIT": "DEPOSIT", "WITHDRAW": "WITHDRAWAL", "WITHDRAWAL": "WITHDRAWAL",
           "FEE": "FEE", "TRANSFER": "TRANSFER",
           "INTEREST_ON_FREE_CASH": "INTEREST", "LENDING_INTEREST": "INTEREST"}


def parse_transaction(item: dict) -> dict | None:
    kind = TX_KIND.get((item.get("type") or "").upper())
    amount = _num(item.get("amount"))
    if not kind or amount is None:
        return None
    if kind in ("WITHDRAWAL", "FEE"):
        amount = -abs(amount)
    elif kind in ("DEPOSIT", "INTEREST"):
        amount = abs(amount)
    return {"kind": kind, "amount": amount, "currency": item.get("currency") or "GBP",
            "date": (item.get("dateTime") or item.get("date") or "")[:10],
            "ref": str(item.get("reference") or "")}


# ---------------------------------------------------------------------------- sync

def connect(platform_id: int, key: str, secret: str) -> dict:
    """Test a key, and keep it only if it works."""
    client = Client(key, secret)
    found = client.probe()
    save_credentials(platform_id, key, secret)
    creds = credentials(platform_id) or {}
    creds.update(host=found["host"], style=found["style"])
    security.put(_vault_ref(platform_id), creds)
    s = found["summary"]
    where = "your real account" if found["host"] == LIVE else "a Practice (demo) account"
    return {"ok": True, "message": f"Connected to {where} — currency {s.get('currency') or 'GBP'}.",
            "demo": found["host"] == DEMO}


def _client(platform_id: int) -> Client:
    creds = credentials(platform_id)
    if not creds or not creds.get("api_key"):
        raise T212Error("No Trading 212 key saved for this platform yet.")
    return Client(creds["api_key"], creds.get("api_secret", ""),
                  host=creds.get("host") or LIVE, style=creds.get("style"))


def sync(platform_id: int, history: bool = True, progress=None) -> dict:
    """Summary and positions first — seconds — then history, which the rate limit
    makes slow, so the numbers people came for are on screen straight away."""
    say = progress or (lambda msg: None)
    client = _client(platform_id)
    report = {"positions": 0, "trades": 0, "dividends": 0, "cash": 0, "warnings": []}
    try:
        say("Trading 212: account")
        summary = client.get(P_SUMMARY) or {}
        time.sleep(1.1)
        say("Trading 212: positions")
        raw_positions = client.get(P_POSITIONS) or []
    except T212Error as e:
        db.execute("UPDATE platforms SET last_error=? WHERE id=?", (str(e), platform_id))
        raise

    cash_parts = [_num((summary.get("cash") or {}).get(k))
                  for k in ("availableToTrade", "inPies", "reservedForOrders")]
    cash = sum(v for v in cash_parts if v is not None) if any(
        v is not None for v in cash_parts) else None
    if cash is None:
        report["warnings"].append("Trading 212 didn't report a cash balance in the expected "
                                  "shape, so cash is left unknown rather than guessed at zero.")
    now = db.now()
    items = raw_positions if isinstance(raw_positions, list) else raw_positions.get("items", [])
    parsed = [x for x in (parse_position(p) for p in items) if x]
    with db.tx() as c:
        keep = []
        for p in parsed:
            iid = symbols.upsert_instrument(c, p["symbol"], p["exchange"], p["name"],
                                            p["isin"], p["currency"])
            keep.append(iid)
            c.execute(
                "INSERT INTO positions(platform_id,instrument_id,quantity,cost,broker_value,"
                "broker_price,broker_ccy,valued_at,source,updated_at) VALUES(?,?,?,?,?,?,?,?,'api',?)"
                " ON CONFLICT(platform_id,instrument_id) DO UPDATE SET quantity=excluded.quantity,"
                " cost=excluded.cost, broker_value=excluded.broker_value,"
                " broker_price=excluded.broker_price, broker_ccy=excluded.broker_ccy,"
                " valued_at=excluded.valued_at, source='api', updated_at=excluded.updated_at",
                (platform_id, iid, p["quantity"], p["cost_gbp"], p["value_gbp"],
                 p["price"], p["currency"], now, now))
        q = ",".join("?" * len(keep)) or "NULL"
        c.execute(f"DELETE FROM positions WHERE platform_id=? AND source='api' "
                  f"AND instrument_id NOT IN ({q})", (platform_id, *keep))
        c.execute("UPDATE platforms SET cash=COALESCE(?, cash), cash_as_of=?, cash_source="
                  "CASE WHEN ? IS NULL THEN cash_source ELSE 'api' END, reported_total=?,"
                  " reported_at=?, last_sync=?, last_error=NULL WHERE id=?",
                  (cash, now, cash, _num(summary.get("totalValue")), now, now, platform_id))
    report["positions"] = len(parsed)

    if history:
        for kind in ("orders", "dividends", "transactions"):
            try:
                say(f"Trading 212: {kind} history")
                report[{"orders": "trades", "dividends": "dividends",
                        "transactions": "cash"}[kind]] += _sync_history(client, platform_id, kind)
            except T212Error as e:
                report["warnings"].append(f"{kind.title()} history: {e}")
    return report


def _sync_history(client: Client, platform_id: int, kind: str) -> int:
    added = 0

    def seen(items) -> bool:
        # Only stop early when this page added nothing at all: everything on it, and
        # so everything older, is already stored.
        return page_added[0] == 0

    page_added = [0]
    for items in client.pages(kind, stop_when_seen=seen):
        page_added[0] = 0
        with db.tx() as c:
            for it in items:
                try:
                    n = _store_history_item(c, platform_id, kind, it)
                except (ValueError, TypeError):
                    n = 0
                page_added[0] += n
                added += n
    return added


def _store_history_item(c, platform_id: int, kind: str, it: dict) -> int:
    if kind == "orders":
        o = parse_order(it)
        if not o or not o["date"]:
            return 0
        sym, ex = symbols.parse_t212(o["ticker"])
        iid = symbols.upsert_instrument(c, sym, ex, o["name"], o["isin"], o["currency"])
        fp = db.fingerprint("t212", platform_id, "order", o["ref"])
        return c.execute(
            "INSERT OR IGNORE INTO trades(platform_id,instrument_id,traded_on,side,quantity,price,"
            "price_ccy,value_gbp,fees_gbp,ref,source,fp) VALUES(?,?,?,?,?,?,?,?,?,?,'api',?)",
            (platform_id, iid, o["date"], o["side"], o["quantity"], o["price"], o["currency"],
             o["value_gbp"], o["fees_gbp"], o["ref"], fp)).rowcount
    if kind == "dividends":
        inst = it.get("instrument") or {}
        ticker = inst.get("ticker") or it.get("ticker") or ""
        amount = _num(it.get("amount"))
        when = (it.get("paidOn") or "")[:10]
        if not ticker or amount is None or not when:
            return 0
        sym, ex = symbols.parse_t212(ticker)
        iid = symbols.upsert_instrument(c, sym, ex, inst.get("name"), inst.get("isin"),
                                        inst.get("currency"))
        fp = db.fingerprint("t212", platform_id, "div", it.get("reference") or "", when, ticker, amount)
        return c.execute("INSERT OR IGNORE INTO dividends(platform_id,instrument_id,paid_on,"
                         "amount_gbp,ref,source,fp) VALUES(?,?,?,?,?,'api',?)",
                         (platform_id, iid, when, amount, it.get("reference"), fp)).rowcount
    t = parse_transaction(it)
    if not t or not t["date"]:
        return 0
    amount = t["amount"]
    if t["currency"] not in ("GBP", None):
        amount = store.to_gbp(amount, t["currency"], t["date"])
        if amount is None:
            return 0
    fp = db.fingerprint("t212", platform_id, "tx", t["ref"], t["date"], t["kind"], t["amount"])
    return c.execute("INSERT OR IGNORE INTO cash_moves(platform_id,happened_on,kind,amount_gbp,"
                     "ref,source,fp) VALUES(?,?,?,?,?,'api',?)",
                     (platform_id, t["date"], t["kind"], amount, t["ref"], fp)).rowcount
