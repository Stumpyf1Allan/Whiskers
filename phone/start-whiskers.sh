#!/data/data/com.termux/files/usr/bin/bash
# Start Whiskers on an Android phone, inside Termux. The first run sets up Python and
# takes a few minutes; after that it opens in a couple of seconds. Running it again
# while Whiskers is already going simply brings it back up in the browser.
set -e
cd "$(dirname "$(readlink -f "$0")")/.."
if [ ! -f .phone-ready ]; then
  echo "First run: installing Python and what Whiskers needs..."
  pkg install -y python python-cryptography
  touch .phone-ready
fi
termux-wake-lock 2>/dev/null || true
exec python run_whiskers.py --phone
