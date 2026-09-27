"""Every test gets its own empty data folder, so nothing leaks between them and nothing
ever touches a real Whiskers database. Mittens & Pence learned this the hard way: tests
that leaned on each other's leftovers passed alone and failed in the full run."""

import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("WHISKERS_DATA_DIR", str(ROOT / ".pytest-data"))


@pytest.fixture(autouse=True)
def fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("WHISKERS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("WHISKERS_FAKE_MARKET", raising=False)
    from folio import config, db
    from folio.market import store
    db.forget_initialised()
    config.settings._data = None
    store._fx_cache.clear()
    # No test may reach the internet or leave a refresh running behind it. On Allan's PC
    # a sample-portfolio test started a real background refresh of 40-odd price series;
    # it was still going when the next test swapped in a fresh empty database, and failed
    # there with "no such table: series" (and the checks took four times as long).
    from folio import net

    def offline(*a, **k):
        raise net.FetchError("Tests never use the internet.")
    monkeypatch.setattr(net, "get", offline)
    monkeypatch.setattr(store, "start_refresh", lambda *a, **k: False)
    db.init()
    yield tmp_path
    db.forget_initialised()
    config.settings._data = None
    store._fx_cache.clear()
