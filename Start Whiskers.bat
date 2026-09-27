@echo off
REM Run Whiskers straight from the source folder (no build needed).
REM Needs Python 3.10+ from python.org with "Add Python to PATH" ticked.
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install it from https://www.python.org/downloads/
  echo and tick "Add Python to PATH", then double-click this again.
  pause
  exit /b 1
)
if not exist ".venv" python -m venv .venv
call .venv\Scripts\activate.bat
REM Installed once, and again only if the last attempt didn't finish: a marker file
REM records success, so a failed first install is retried rather than forgotten.
if not exist ".venv\installed.ok" (
  echo Setting up, about a minute...
  python -m pip install --quiet --upgrade pip
  python -m pip install --quiet -r requirements.txt
  if errorlevel 1 (
    echo.
    echo Some extras didn't install. Whiskers will still run, with fewer of them.
    echo Copy the messages above into a chat with Claude.
    pause
  ) else (
    echo ok> ".venv\installed.ok"
  )
)
python run_whiskers.py
if errorlevel 1 pause
