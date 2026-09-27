# PyInstaller spec for Whiskers. Adapted from Mittens & Pence's, keeping every guard
# that spec earned.
#
#   pyinstaller build/whiskers.spec --noconfirm            -> dist/Whiskers/Whiskers.exe
#       A folder. Starts in about a second. Right for your own machine.
#
#   set WHISKERS_ONEFILE=1  (Windows)  /  export WHISKERS_ONEFILE=1  (Mac)
#   pyinstaller build/whiskers.spec --noconfirm            -> dist/Whiskers.exe
#       One file that unpacks itself each time it runs: slower to start, but one thing
#       to put on a Drive link.
#
# PyInstaller cannot cross-compile: build the Windows app on Windows and each Mac build
# on that kind of Mac. The GitHub workflow does all three.

import os
import pathlib
import sys

ROOT = pathlib.Path(SPECPATH).parent          # noqa: F821 — SPECPATH is injected
sys.path.insert(0, str(ROOT))
from folio import config as _cfg               # noqa: E402 — needs ROOT on the path

# The package is `folio`, not `whiskers`, so the app can be renamed without touching
# it. A spec pointing at a folder that isn't there builds an app with no interface —
# Mittens & Pence nearly shipped exactly that after a blanket rename — so it asserts.
PKG = ROOT / "folio"
assert (PKG / "web" / "static" / "app.js").exists(), (
    f"the app's front end is not where the spec is looking: {PKG / 'web' / 'static'}")

datas = [(str(PKG / "web" / "static"), "web/static")]
binaries = []
# cffi's compiled backend is imported from C inside curl_cffi, where PyInstaller's
# analysis cannot see it; without it the built app quietly fell back to plain Python.
hiddenimports = ["sqlite3", "webbrowser", "json", "csv", "_cffi_backend", "cffi"]

# curl_cffi carries a compiled libcurl. collect_all brings the library, its data and
# its submodules; without it the frozen app would quietly fall back to plain urllib
# and Yahoo would start refusing it.
try:
    from PyInstaller.utils.hooks import collect_all
    for mod in ("curl_cffi", "cffi", "certifi"):
        try:
            d, b, h = collect_all(mod)
            datas += d
            binaries += b
            hiddenimports += h
        except Exception:
            pass
except Exception:
    pass

# Optional extras: bundled when installed, silently skipped when not.
for opt in ("keyring", "keyring.backends.Windows", "keyring.backends.macOS",
            "keyring.backends.SecretService", "cryptography", "webview"):
    try:
        __import__(opt)
        hiddenimports.append(opt)
    except Exception:
        pass

# Names PyInstaller's own hooks alias. Excluding any of them fails the build with
# "already imported as ExcludedModule" — only on Python 3.12+, only on Windows, only
# with setuptools present, which is how Mittens & Pence found out. A test checks this.
ALIASED_BY_PYINSTALLER = ("distutils", "backports", "importlib_metadata", "jaraco")

excludes = [
    "tkinter", "unittest", "pydoc_data", "test",
    "numpy", "pandas", "matplotlib", "scipy", "IPython", "notebook",
    "pytest", "playwright",
]
assert not set(excludes) & set(ALIASED_BY_PYINSTALLER), (
    "excluding a name PyInstaller aliases makes the build fail with "
    "'already imported as ExcludedModule'")

a = Analysis(                                  # noqa: F821
    [str(ROOT / "run_whiskers.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data)               # noqa: F821

# Per platform: Windows needs .ico and macOS .icns; handing over the wrong one is at
# best a missing icon.
_ICON_FOR = {"win32": "whiskers.ico", "darwin": "whiskers.icns"}
icon = None
_wanted = PKG / "resources" / _ICON_FOR.get(sys.platform, "whiskers.png")
if _wanted.exists():
    icon = str(_wanted)
elif (PKG / "resources" / "whiskers.png").exists():
    icon = str(PKG / "resources" / "whiskers.png")

ONEFILE = os.environ.get("WHISKERS_ONEFILE") == "1"
NAME = _cfg.APP_FILE_NAME

exe = EXE(                                     # noqa: F821
    pyz,
    a.scripts,
    *([a.binaries, a.zipfiles, a.datas] if ONEFILE else [[]]),
    exclude_binaries=not ONEFILE,
    name=NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                                 # UPX trips antivirus heuristics
    console=False,                             # no terminal window on Windows
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon,
)

coll = None
if not ONEFILE:
    coll = COLLECT(                            # noqa: F821
        exe, a.binaries, a.zipfiles, a.datas,
        strip=False, upx=False, upx_exclude=[], name=NAME,
    )

if sys.platform == "darwin":
    app = BUNDLE(                              # noqa: F821
        coll or exe,
        name=f"{NAME}.app",
        icon=icon,
        bundle_identifier="io.github.stumpyf1allan.whiskers",
        info_plist={
            # From config, never typed here: a hard-coded version is invisible until
            # somebody checks Get Info on a build three releases old.
            "CFBundleShortVersionString": _cfg.APP_VERSION,
            "CFBundleVersion": _cfg.APP_VERSION,
            "NSHighResolutionCapable": True,
            "LSApplicationCategoryType": "public.app-category.finance",
        },
    )
