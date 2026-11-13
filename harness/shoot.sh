#!/bin/sh
# Screenshot Letterpress with headless Chrome into docs/shots/, against live mode: the real routes and a scripted
# stand-in model (harness/live/), filled by harness/live/seed_notebook.py with the warming-center samples.
#   sh harness/shoot.sh            (needs network for React from esm.sh and codicons from jsdelivr)
# The fixture harness (harness/index.html without live=1) still serves the Kits screens from fixtures.json.
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/docs/shots"
PORT=${PORT:-8797}
DATA="$(mktemp -d)"
mkdir -p "$OUT"
/usr/bin/python3 "$ROOT/harness/live/server.py" "$PORT" --data "$DATA" >/dev/null 2>&1 &
SRV=$!
trap 'kill $SRV; rm -rf "$DATA"' EXIT
sleep 2
/usr/bin/python3 "$ROOT/harness/live/seed_notebook.py" "$PORT" >/dev/null
BASE="http://127.0.0.1:$PORT/harness/index.html?live=1"
shot() { "$CHROME" --headless=new --disable-gpu --hide-scrollbars --mute-audio --autoplay-policy=user-gesture-required --user-data-dir="$DATA/chrome-$1" --window-size="$3" --virtual-time-budget=20000 --screenshot="$OUT/$1.png" "$BASE&$2" 2>/dev/null; echo "$OUT/$1.png"; }
shot notebook-dark "theme=dark" 1600,1000
shot notebook-light "theme=light" 1600,1000
shot notebook-narrow-light "theme=light" 1100,1100
shot notebook-reader-light "theme=light&reader=1" 1600,1000
shot notebook-kitchooser-dark "theme=dark&open=kit" 1600,1000
shot notebook-form-deck-light "theme=light&form=deck" 1600,1000
shot viewer-deck-light "theme=light&view=deck" 1600,1200
shot viewer-deck-dark "theme=dark&view=deck" 1600,1200
shot viewer-graphic-dark "theme=dark&view=visual" 1600,1200
shot viewer-graphic-light "theme=light&view=visual" 1600,1200
shot viewer-onepager-light "theme=light&view=onepager" 1600,1200
shot viewer-audio-dark "theme=dark&view=audio" 1600,1100
shot viewer-trace-light "theme=light&view=deck&trace=2,914" 1600,1200
shot viewer-export-light "theme=light&view=visual&open=export" 1600,1000
shot notebook-accent-red-light "theme=light&accent=e5484d" 1600,1000
shot notebook-accent-green-dark "theme=dark&accent=30a46c" 1600,1000
shot kits-studio-light "theme=light&tab=kits" 1600,1300
shot kits-studio-dark "theme=dark&tab=kits" 1600,1300
shot kit-bench-light "theme=light&tab=kits&kits=bench&kit=meridian" 1600,1500
shot kit-bench-dark "theme=dark&tab=kits&kits=bench&kit=folio" 1600,1500
shot kits-import-light "theme=light&tab=kits&kits=import" 1600,900
shot storage-light "theme=light&tab=storage" 1600,900
