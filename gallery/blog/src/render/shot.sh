#!/bin/bash
# shot.sh CODE -> gallery/blog/CODE.png  (헤드리스 크롬 필요: CHROME 환경 변수로 경로 지정)
set -e
CODE=$1
HERE=$(cd "$(dirname "$0")" && pwd)
R=$(cd "$HERE/../.." && pwd)
TMP=${TMPDIR:-/tmp}/blogr; mkdir -p "$TMP"
CH=${CHROME:-"$HOME/Library/Caches/ms-playwright/chromium-1254/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"}
PROF=$TMP/prof_$CODE
MODE=split; [[ $CODE == V* ]] && MODE=full
python3 "$HERE/render.py" "$R/src/$CODE.md" "$TMP/$CODE.html" $MODE
H=$("$CH" --headless=new --disable-gpu --user-data-dir="$PROF" --window-size=390,2000 --dump-dom "file://$TMP/$CODE.html" 2>/dev/null | sed -n 's/.*<title>\([0-9]*\)<\/title>.*/\1/p')
"$CH" --headless=new --disable-gpu --hide-scrollbars --user-data-dir="$PROF" --force-device-scale-factor=2 --window-size=390,$H --screenshot="$R/$CODE.png" "file://$TMP/$CODE.html" >/dev/null 2>&1 || true
echo "$CODE $H"
