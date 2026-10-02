"""Names, paths and settings for Whiskers.

THE NAME LIVES HERE AND NOWHERE ELSE. Mittens & Pence was renamed twice, and a blanket
find-and-replace across the tree caught it four separate times — most dangerously by
rewriting values whose whole job was to remember the *old* name. So: the Python package
is called `folio`, which describes what it is rather than what it is called, and every
human-facing name is read from the constants below. Renaming the app before anybody has
installed it is a one-line change here plus the repository name in UPDATE_MANIFEST_URL.
Renaming it after people have data is not — see the data_dir() docstring.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import threading

APP_NAME = "Whiskers"
#: The same name with nothing a shell or a filename can misread. Identical today —
#: kept separate because Mittens & Pence learned the hard way that "&" is a command
#: separator in batch files, and the next name might not be one plain word.
APP_FILE_NAME = "Whiskers"
APP_SLUG = "whiskers"
APP_VERSION = "1.0.0"
APP_TAGLINE = "Investment tracker"

#: Where every copy looks for new versions: the latest GitHub release of the repository.
#: Filled in before the repository exists, deliberately (the Mittens & Pence lesson): a
#: copy pointed at an address with nothing there yet starts working the moment something
#: is published, while a copy built with this blank can never be told about an update.
UPDATE_MANIFEST_URL = (
    "https://github.com/Stumpyf1Allan/whiskers"
    "/releases/latest/download/latest.json")

#: Mittens & Pence listens on 8765. A different number means both apps can be open at
#: the same time, and the security checks in the server pin requests to our own port so
#: one app's page can never post to the other.
PREFERRED_PORT = 8766

#: Money quoted in the minor unit. London prices arrive in pence as often as in pounds,
#: and which one depends on the source: Yahoo writes "GBp", Trading 212 writes "GBX".
#: Case matters — "GBp" is pence and "GBP" is pounds — so nothing may upper-case a
#: currency code before it has been looked up here.
MINOR_UNIT_CURRENCIES = {
    "GBp": ("GBP", 100), "GBX": ("GBP", 100), "GBx": ("GBP", 100),
    "ZAc": ("ZAR", 100), "ZAC": ("ZAR", 100),
    "ILA": ("ILS", 100),
}

DEFAULTS = {
    "check_for_updates": True,
    "auto_download_updates": True,
    "update_url": "",
    #: Stocks and shares ISA subscription limit per tax year. A setting, not a
    #: constant, because the Chancellor can change it and the app should not need a
    #: new release when that happens.
    "isa_allowance": 20000,
    #: FSCS protection for an investment firm's failure, per person per firm. The
    #: deposit limit rose to £120,000 in December 2025; this one did not.
    "fscs_limit": 85000,
    "refresh_on_open": True,
    #: Optional. Stooq started requiring a key in April 2026; without one the app
    #: simply does not use it.
    "stooq_key": "",
    "user_name": "",
    "help_email": "allan.michaelclark@gmail.com",
    "toured": False,
    #: "clock" darkens the screen from 7pm to 7am, as asked for in Mittens & Pence;
    #: "system" follows the computer; "light" and "dark" are fixed.
    "theme": "clock",
    "hide_amounts": False,
}


def _is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def resource_dir() -> pathlib.Path:
    """Read-only bundled files (the web front end)."""
    if _is_frozen():
        return pathlib.Path(getattr(sys, "_MEIPASS", pathlib.Path(sys.executable).parent))
    return pathlib.Path(__file__).resolve().parent


def _data_root() -> pathlib.Path:
    if sys.platform.startswith("win"):
        base = pathlib.Path(os.environ.get("LOCALAPPDATA")
                            or os.path.expanduser("~\\AppData\\Local"))
        return base / APP_FILE_NAME
    if sys.platform == "darwin":
        return pathlib.Path.home() / "Library" / "Application Support" / APP_FILE_NAME
    base = pathlib.Path(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"))
    return base / APP_SLUG


def data_dir() -> pathlib.Path:
    """Per-user writable folder: database, settings, logs, downloaded updates.

    If this app is ever renamed after people are using it, this function must learn to
    look in the old folder first — Mittens & Pence's `data_dir()` shows how. Moving
    somebody's data to tidy up a rename is how it gets lost.
    """
    override = os.environ.get("WHISKERS_DATA_DIR")
    p = pathlib.Path(override) if override else _data_root()
    key = str(p)
    if key not in _made:                  # every database call lands here; mkdir once
        p.mkdir(parents=True, exist_ok=True)
        _made.add(key)
    return p


_made: set[str] = set()


def db_path() -> pathlib.Path:
    return data_dir() / "whiskers.db"


def logs_dir() -> pathlib.Path:
    p = data_dir() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def exports_dir() -> pathlib.Path:
    p = data_dir() / "exports"
    p.mkdir(parents=True, exist_ok=True)
    return p


def phone_mode() -> bool:
    """Running on a phone (inside Termux). There, other apps share the loopback address,
    so the API answers only requests carrying this copy's key."""
    return os.environ.get("WHISKERS_PHONE") == "1"


def phone_key() -> str:
    """Made once and kept in the app's private folder, where other apps cannot read it."""
    import secrets
    f = data_dir() / "phone-key"
    if not f.exists():
        f.write_text(secrets.token_hex(24), encoding="utf-8")
        try:
            f.chmod(0o600)
        except OSError:
            pass
    return f.read_text(encoding="utf-8").strip()


def fake_market() -> bool:
    """Synthetic prices for tests and screenshots. Never on unless asked for, and the
    UI puts a red banner across the top whenever it is."""
    return os.environ.get("WHISKERS_FAKE_MARKET") == "1"


class Settings:
    """settings.json in the data folder, read once and written on every change."""

    def __init__(self):
        self._lock = threading.Lock()
        self._data: dict | None = None

    def _file(self) -> pathlib.Path:
        return data_dir() / "settings.json"

    def _load(self) -> dict:
        if self._data is None:
            data = dict(DEFAULTS)
            f = self._file()
            if f.exists():
                try:
                    data.update(json.loads(f.read_text(encoding="utf-8")))
                except (OSError, ValueError):
                    pass            # a damaged settings file must not stop the app
            self._data = data
        return self._data

    def get(self, key, default=None):
        with self._lock:
            return self._load().get(key, DEFAULTS.get(key, default))

    def __getitem__(self, key):
        return self.get(key)

    def __setitem__(self, key, value):
        self.update({key: value})

    def update(self, changes: dict) -> dict:
        with self._lock:
            data = self._load()
            data.update({k: v for k, v in changes.items() if k in DEFAULTS})
            tmp = self._file().with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
            tmp.replace(self._file())
            return dict(data)

    def all(self) -> dict:
        with self._lock:
            return dict(self._load())

    def reset_cache(self):
        with self._lock:
            self._data = None


settings = Settings()
