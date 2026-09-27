"""Talking to the internet.

Two kinds of server, treated differently:

* **Official APIs** (Trading 212, FRED) are called with the standard library. They
  document their behaviour and have no reason to turn a well-formed request away.

* **Yahoo's chart feed** is unofficial. Since 2025 it has answered "429 Too Many
  Requests" to anything whose TLS handshake doesn't look like a browser's — whatever
  headers it sends — so a plain Python request can be refused on its very first call.
  `curl_cffi` presents a real browser's handshake, which is how the widely used
  `yfinance` library keeps working. It is in requirements.txt and bundled in the
  build; if it is ever missing the app falls back to urllib and says so plainly when
  Yahoo refuses, rather than showing empty charts with no reason.

A machine with no internet should fail fast rather than sit through a dozen timeouts,
so after several connection failures in a row everything short-circuits for a minute.
"""

from __future__ import annotations

import threading
import time
import urllib.error
import urllib.parse
import urllib.request

BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/140.0 Safari/537.36")

#: Seconds to leave between two requests to the same host. Yahoo throttles bursts;
#: FRED and Trading 212 publish their own limits, which the callers respect.
MIN_GAP = {"query1.finance.yahoo.com": 0.7, "query2.finance.yahoo.com": 0.7}

_FAIL_THRESHOLD = 4
_FAIL_COOLDOWN = 60.0
_state = {"fails": 0, "until": 0.0}
_last: dict[str, float] = {}
_gap_lock = threading.Lock()


class FetchError(Exception):
    """A request that did not produce a usable body. `status` is the HTTP code when
    there was one, None for a connection that never completed."""

    def __init__(self, message: str, status: int | None = None, url: str = "",
                 headers: dict | None = None):
        super().__init__(message)
        self.status = status
        self.url = url
        self.headers = headers or {}


def offline() -> bool:
    return _state["until"] > time.time()


def reset():
    _state["fails"] = 0
    _state["until"] = 0.0


def _note_connection_failure():
    _state["fails"] += 1
    if _state["fails"] >= _FAIL_THRESHOLD:
        _state["until"] = time.time() + _FAIL_COOLDOWN


def _pace(url: str):
    host = urllib.parse.urlparse(url).hostname or ""
    gap = MIN_GAP.get(host)
    if not gap:
        return
    with _gap_lock:
        wait = _last.get(host, 0.0) + gap - time.time()
        if wait > 0:
            time.sleep(wait)
        _last[host] = time.time()


def have_browser_tls() -> bool:
    return browser_tls_problem() is None


def browser_tls_problem() -> str | None:
    """None when curl_cffi loads; otherwise the reason it didn't, word for word — a
    missing module in a built app and a failed install need different fixes."""
    try:
        import curl_cffi  # noqa: F401
        return None
    except Exception as e:
        return f"{type(e).__name__}: {e}"


def get(url: str, *, timeout: float = 15.0, headers: dict | None = None,
        browser: bool = False) -> bytes:
    """GET a URL and return the body, or raise FetchError."""
    if offline():
        raise FetchError("This computer seems to be offline — trying again shortly.", url=url)
    _pace(url)
    if browser and have_browser_tls():
        return _get_curl(url, timeout, headers)
    hdrs = {"User-Agent": BROWSER_UA if browser else "Whiskers (personal portfolio app)",
            "Accept": "application/json,text/csv,*/*;q=0.8",
            "Accept-Language": "en-GB,en;q=0.9"}
    hdrs.update(headers or {})
    req = urllib.request.Request(url, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
        _state["fails"] = 0
        return body
    except urllib.error.HTTPError as e:
        _state["fails"] = 0                    # the server answered: we are online
        try:
            detail = e.read()[:300].decode("utf-8", "replace")
        except Exception:
            detail = ""
        raise FetchError(f"HTTP {e.code} {detail}".strip(), status=e.code, url=url,
                         headers=dict(e.headers or {})) from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        _note_connection_failure()
        raise FetchError(f"Couldn't connect: {getattr(e, 'reason', e)}", url=url) from None


def _get_curl(url: str, timeout: float, headers: dict | None) -> bytes:
    from curl_cffi import requests as creq
    try:
        r = creq.get(url, impersonate="chrome", timeout=timeout, headers=headers or None)
    except Exception as e:                     # curl_cffi raises its own error types
        _note_connection_failure()
        raise FetchError(f"Couldn't connect: {e}", url=url) from None
    _state["fails"] = 0
    if r.status_code >= 400:
        raise FetchError(f"HTTP {r.status_code} {r.text[:300]}".strip(), status=r.status_code,
                         url=url, headers=dict(r.headers or {}))
    return r.content
