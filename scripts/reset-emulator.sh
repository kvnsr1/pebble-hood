#!/bin/sh
# Stop only emulators recorded in this project's isolated temporary directory.
set -eu
. "$(dirname "$0")/env.sh"
cd "$PROJECT_DIR"
pebble kill --force
python - <<'PY'
from pathlib import Path
Path('.tools/tmp/pb-emulator.json').unlink(missing_ok=True)
PY
