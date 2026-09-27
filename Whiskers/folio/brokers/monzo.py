"""Monzo, read-only, through Monzo's own developer API.

Monzo publishes an API meant for connecting to your own account ("You may only connect
to your own account or those of a small set of users you explicitly allow"), so no
aggregator, contract or fee is involved: you create a private client for yourself at
developers.monzo.com and paste its ID and secret into Whiskers. Of the accounts Allan
asked about (HSBC, Monzo, Spring, American Express, Barclays), Monzo is the only one
that offers this; the others are reachable only through Open Banking companies that
need a licence and a business contract, so their balances are typed in.

What happens, and the two Monzo quirks it handles (both learned in Mittens & Pence):

1. Whiskers sends you to Monzo's sign-in page. Monzo emails you a link; opening it
   brings you back to Whiskers on this computer, which swaps the code for tokens.
2. You must then ALSO approve the request inside the Monzo app. Until you do, Monzo
   answers every call with 403 "verification required", and Whiskers says so in words.
3. Tokens are refreshed by Whiskers itself (the client is "confidential"), so linking is
   a one-off until Monzo or you revoke it.

Only balances are read: your personal current account plus its pots, which Monzo
reports together as the account's total balance. A joint account is left out, being
shared money, and nothing here can move a penny: the API client has no payment calls.
"""

from __future__ import annotations

import datetime as dt
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request

from .. import db, net, security

AUTH = "https://auth.monzo.com/"
API = "https://api.monzo.com"
CALLBACK_PATH = "/oauth/monzo"
#: Links from Monzo's email are good for a while; a pending sign-in is kept 30 minutes.
PENDING_SECONDS = 1800
_pending: dict[str, tuple[int, float]] = {}


class MonzoError(Exception):
    pass


def _ref(platform_id: int) -> str:
    return f"monzo:{platform_id}"


def credentials(platform_id: int) -> dict:
    return security.get(_ref(platform_id)) or {}


def linked(platform_id: int) -> bool:
    return bool(credentials(platform_id).get("refresh"))


def forget(platform_id: int) -> None:
    security.drop(_ref(platform_id))
    db.execute("UPDATE platforms SET cash_source='manual' WHERE id=? AND cash_source='api'",
               (platform_id,))


def redirect_uri(port: int) -> str:
    return f"http://127.0.0.1:{port}{CALLBACK_PATH}"


def begin(platform_id: int, client_id: str, client_secret: str, port: int) -> dict:
    """Keep the client's details and return Monzo's sign-in address."""
    client_id, client_secret = (client_id or "").strip(), (client_secret or "").strip()
    if not client_id.startswith("oauth2client_") or not client_secret:
        raise MonzoError("Paste both the Client ID (it starts oauth2client_) and the Client "
                         "secret from developers.monzo.com.")
    state = secrets.token_urlsafe(24)
    creds = credentials(platform_id)
    creds.update(client_id=client_id, client_secret=client_secret, redirect_uri=redirect_uri(port))
    security.put(_ref(platform_id), creds)
    _pending[state] = (platform_id, time.time() + PENDING_SECONDS)
    q = urllib.parse.urlencode({"client_id": client_id, "redirect_uri": creds["redirect_uri"],
                                "response_type": "code", "state": state})
    return {"url": f"{AUTH}?{q}", "redirect_uri": creds["redirect_uri"]}


def complete(state: str, code: str, error: str | None = None) -> int:
    """The link from Monzo's email lands here. The state must be one this copy handed
    out in the last half hour: anything else is refused, whoever sent it."""
    entry = _pending.pop(state or "", None)
    if not entry or entry[1] < time.time():
        raise MonzoError("That Monzo link is out of date or wasn't started from this copy of "
                         "Whiskers. Start again from Settings.")
    platform_id = entry[0]
    if error or not code:
        raise MonzoError(f"Monzo didn't approve the link ({error or 'no code returned'}).")
    creds = credentials(platform_id)
    payload = _post_token({"grant_type": "authorization_code", "client_id": creds["client_id"],
                           "client_secret": creds["client_secret"],
                           "redirect_uri": creds["redirect_uri"], "code": code})
    _store(platform_id, creds, payload)
    return platform_id


def _post_token(fields: dict) -> dict:
    """The one POST this module makes, to Monzo's token endpoint and nowhere else."""
    req = urllib.request.Request(f"{API}/oauth2/token", method="POST",
                                 data=urllib.parse.urlencode(fields).encode(),
                                 headers={"Content-Type": "application/x-www-form-urlencoded",
                                          "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise MonzoError(f"Monzo refused the sign-in ({e.code}): {detail}") from None
    except (urllib.error.URLError, OSError) as e:
        raise MonzoError(f"Couldn't reach Monzo: {e}") from None


def _store(platform_id: int, creds: dict, payload: dict) -> None:
    ttl = int(payload.get("expires_in") or 21600)
    creds.update(access=payload.get("access_token"),
                 refresh=payload.get("refresh_token") or creds.get("refresh"),
                 expires=time.time() + ttl - 120)
    security.put(_ref(platform_id), creds)


def _token(platform_id: int, creds: dict) -> str:
    if creds.get("access") and float(creds.get("expires") or 0) > time.time():
        return creds["access"]
    if not creds.get("refresh"):
        raise MonzoError("Monzo isn't linked yet: use Connect in Settings.")
    payload = _post_token({"grant_type": "refresh_token", "client_id": creds["client_id"],
                           "client_secret": creds["client_secret"], "refresh_token": creds["refresh"]})
    _store(platform_id, creds, payload)
    return creds["access"]


def _get(platform_id: int, creds: dict, path: str) -> dict:
    try:
        body = net.get(f"{API}{path}", headers={"Authorization": f"Bearer {_token(platform_id, creds)}",
                                                  "Accept": "application/json"}, timeout=20)
    except net.FetchError as e:
        if e.status == 403:
            raise MonzoError("Monzo needs you to approve Whiskers inside the Monzo app. Open the "
                             "app, tap the waiting request, allow it, then press Refresh.") from None
        if e.status == 401:
            raise MonzoError("Monzo has ended this link (that happens if access is revoked). "
                             "Use Connect in Settings to link it again.") from None
        raise MonzoError(f"Monzo didn't answer: {e}") from None
    return json.loads(body.decode("utf-8") if isinstance(body, bytes) else body)


def parse_balance(b: dict) -> float:
    """Pence to pounds. total_balance is the account plus its pots; balance alone is the
    account without them, used only when Monzo doesn't send the total."""
    pence = b.get("total_balance", b.get("balance"))
    return round(float(pence) / 100.0, 2)


def sync(platform_id: int) -> dict:
    creds = credentials(platform_id)
    try:
        accounts = [a for a in (_get(platform_id, creds, "/accounts").get("accounts") or [])
                    if not a.get("closed") and a.get("type") == "uk_retail"]
        if not accounts:
            raise MonzoError("Monzo returned no open personal current account.")
        total = 0.0
        for a in accounts:
            total += parse_balance(_get(platform_id, creds,
                                        f"/balance?account_id={urllib.parse.quote(a['id'])}"))
    except MonzoError as e:
        db.execute("UPDATE platforms SET last_error=? WHERE id=?", (str(e), platform_id))
        raise
    now = db.now()
    db.execute("UPDATE platforms SET cash=?, cash_as_of=?, cash_source='api', last_sync=?, "
               "last_error=NULL WHERE id=?", (total, now, now, platform_id))
    return {"balance": total, "accounts": len(accounts),
            "as_of": dt.datetime.now().replace(microsecond=0).isoformat(sep=" ")}
