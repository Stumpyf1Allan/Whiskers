@echo off
REM ===================================================================
REM  Build Whiskers for Windows. Double-click this file.
REM
REM  You need Python 3.10 or newer from python.org, with "Add Python to
REM  PATH" ticked during install.
REM
REM  It makes dist\Whiskers\Whiskers.exe. Keep that whole folder
REM  together. Nothing is installed system-wide, and your portfolio
REM  data lives elsewhere, so rebuilding never touches it.
REM ===================================================================
setlocal
cd /d "%~dp0\.."

REM A build inside OneDrive can fail with file-lock errors, because the sync
REM client grabs files while PyInstaller is still writing them.
echo %CD% | findstr /i "OneDrive Dropbox GoogleDrive" >nul
if not errorlevel 1 (
  echo   Note: this folder is inside OneDrive or another syncing folder.
  echo   If the build fails with "permission denied" or "file in use",
  echo   copy the Whiskers folder to your Desktop and build it there.
  echo.
)

echo.
echo   Whiskers - building the Windows app
echo   -----------------------------------
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo   Python was not found on this PC.
  echo   Install it from https://www.python.org/downloads/ and tick
  echo   "Add Python to PATH" on the first screen, then run this again.
  echo.
  pause
  exit /b 1
)

echo   [1/4] Making a private Python environment...
if not exist ".venv" python -m venv .venv
call .venv\Scripts\activate.bat

echo   [2/4] Installing what Whiskers needs...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements-dev.txt
if errorlevel 1 (
  echo.
  echo   Couldn't install what's needed. Usually that means no internet, or a
  echo   work laptop blocking pip. Check the connection and run this again.
  pause
  exit /b 1
)

echo   [3/4] Checking everything still works...
REM -X warn_default_encoding flags any text read that relies on Windows' own
REM encoding, the difference that stopped a Mittens and Pence build.
python -X warn_default_encoding -m pytest tests -q
if errorlevel 1 (
  echo.
  echo   Some checks failed, so the build stops here rather than make
  echo   something broken. Copy the messages above into a chat with Claude.
  pause
  exit /b 1
)

echo   [4/4] Building the app, about two minutes...
set WHISKERS_ONEFILE=
REM PyInstaller's scratch files go to the temp folder, not into this project. Left in
REM build\whiskers they included a Whiskers.exe that cannot run on its own, one folder
REM away from the real one, and that was the one that got double-clicked.
if exist "build\whiskers" rmdir /s /q "build\whiskers"
REM `python -m PyInstaller` uses this environment's Python whether or not its
REM Scripts folder made it onto PATH.
python -m PyInstaller build\whiskers.spec --noconfirm --clean --workpath "%TEMP%\whiskers-build" --distpath dist
if errorlevel 1 (
  echo   The build failed - see the messages above.
  pause
  exit /b 1
)

REM A desktop shortcut to the one Whiskers.exe that runs.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s = (New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop') + '\Whiskers.lnk'); $s.TargetPath = '%CD%\dist\Whiskers\Whiskers.exe'; $s.WorkingDirectory = '%CD%\dist\Whiskers'; $s.Save()" >nul 2>nul
if errorlevel 1 (
  echo.
  echo   Built, but a desktop shortcut couldn't be made. Open the app from
  echo   dist\Whiskers\Whiskers.exe and keep that whole folder together.
) else (
  echo.
  echo   Done. Open Whiskers from the new Whiskers shortcut on your desktop.
)
echo.
echo   Your data is in %LOCALAPPDATA%\Whiskers, so rebuilding or deleting this
echo   folder never touches it.
echo.
pause
