"""Whiskers entry point.

Starts the local server, then opens the window. Three ways to show it, tried in order:
a native window (pywebview), an app-mode Chrome or Edge window, and finally the default
browser. Whichever works, it is the same app.
"""

from __future__ import annotations

import argparse
import logging
import os
import pathlib
import shutil
import subprocess
import sys
import threading
import time
import webbrowser

from . import config, db
from .web import server


def _setup_logging(verbose: bool = False) -> pathlib.Path:
    logfile = config.logs_dir() / "whiskers.log"
    handlers: list[logging.Handler] = [logging.FileHandler(logfile, encoding="utf-8")]
    if verbose:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s",
                        handlers=handlers)
    return logfile


def _startup_jobs():
    try:
        db.init()
    except Exception:
        logging.exception("database init failed")
        return
    try:
        from .brokers import freetrade
        freetrade.rebuild_all()
    except Exception:
        logging.exception("rebuilding Freetrade holdings failed")
    if config.settings.get("refresh_on_open", True) and \
            db.scalar("SELECT COUNT(*) FROM platforms", (), 0):
        def later():
            time.sleep(1.5)       # let the window open first
            try:
                from .market import store
                store.start_refresh(before=server._sync_brokers)
            except Exception:
                logging.exception("refresh on open failed")
        threading.Thread(target=later, daemon=True).start()
    try:
        from . import updates
        updates.start_up()
    except Exception:
        logging.exception("update check failed to start")


def _try_pywebview(url: str) -> bool:
    try:
        import webview
    except Exception:
        return False
    try:
        # pywebview's embedded window silently swallows every file download unless asked
        # not to: a click that would save a file anywhere else just does nothing here, with
        # no error, which is exactly what both the plan-file and spreadsheet exports hit.
        webview.settings["ALLOW_DOWNLOADS"] = True
        # Maximised, not fullscreen: fullscreen hides the title bar and its close button.
        webview.create_window(config.APP_NAME, url, width=1380, height=900, text_select=True,
                              min_size=(1024, 680), maximized=True)
        webview.start()
        return True
    except Exception:
        logging.exception("pywebview failed")
        return False


_CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]


def _try_app_window(url: str) -> subprocess.Popen | None:
    exes = [p for p in _CHROME_CANDIDATES if pathlib.Path(p).exists()]
    for name in ("google-chrome", "chromium", "chromium-browser", "microsoft-edge"):
        found = shutil.which(name)
        if found:
            exes.append(found)
    if not exes:
        return None
    profile = config.data_dir() / "window"
    try:
        return subprocess.Popen(
            [exes[0], f"--app={url}", f"--user-data-dir={profile}", "--window-size=1380,900",
             "--no-first-run", "--no-default-browser-check"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        logging.exception("app-mode window failed")
        return None


def run(open_ui: bool = True, port: int | None = None, prefer: str = "auto"):
    logfile = _setup_logging(bool(os.environ.get("WHISKERS_VERBOSE")))
    logging.info("%s %s starting", config.APP_NAME, config.APP_VERSION)
    httpd, port = server.serve(port=port, block=False)
    url = f"http://127.0.0.1:{port}/"
    _startup_jobs()
    print(f"\n  {config.APP_NAME} {config.APP_VERSION} — {config.APP_TAGLINE}")
    print(f"  Open:  {url}")
    print(f"  Data:  {config.data_dir()}")
    print(f"  Log:   {logfile}")
    print("  Close this window to stop.\n")
    if not open_ui:
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            return
    if prefer in ("auto", "native") and _try_pywebview(url):
        return
    proc = _try_app_window(url) if prefer in ("auto", "app") else None
    if proc is None:
        webbrowser.open(url)
        print("  Opened in your browser. Leave this window running.\n")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
    else:
        try:
            proc.wait()
        except KeyboardInterrupt:
            proc.terminate()
    httpd.shutdown()


def run_phone(port: int) -> int:
    """Start (or find) the server on the phone, then open it in the phone's browser with
    this copy's key in the link. Chrome keeps the key; the link is needed only once."""
    import socket
    os.environ["WHISKERS_PHONE"] = "1"
    url = f"http://127.0.0.1:{port}/#key={config.phone_key()}"
    with socket.socket() as s:
        running = s.connect_ex(("127.0.0.1", port)) == 0
    opener = shutil.which("termux-open-url")
    if running:                                   # already going: just show it
        if opener:
            subprocess.Popen([opener, url])
        print(url)
        return 0
    _setup_logging(False)
    db.init()
    httpd, port = server.serve(port=port, block=False)
    _startup_jobs()
    print(f"\n  {config.APP_NAME} is running. Leave Termux open in the background.\n  {url}\n")
    if opener:
        subprocess.Popen([opener, url])
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        httpd.shutdown()
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog=config.APP_SLUG, description=config.APP_TAGLINE)
    ap.add_argument("--port", type=int, help=f"port to listen on (default {config.PREFERRED_PORT})")
    ap.add_argument("--no-window", action="store_true", help="just run the server")
    ap.add_argument("--window", choices=["auto", "native", "app", "browser"], default="auto")
    ap.add_argument("--refresh", action="store_true", help="sync and fetch prices, then exit")
    ap.add_argument("--version", action="store_true")
    ap.add_argument("--phone", action="store_true", help="run on an Android phone, inside Termux")
    args = ap.parse_args(argv)
    if args.version:
        print(f"{config.APP_NAME} {config.APP_VERSION}")
        return 0
    if args.phone:
        return run_phone(args.port or config.PREFERRED_PORT)
    db.init()
    if args.refresh:
        from .market import store
        server._sync_brokers()
        rep = store.refresh(force=True)
        print(f"{rep['updated']} series updated, {rep['failed']} failed.")
        for e in rep["errors"][:20]:
            print(f"  {e['key']}: {e['message']}")
        return 0
    run(open_ui=not args.no_window, port=args.port, prefer=args.window)
    return 0


if __name__ == "__main__":
    sys.exit(main())
