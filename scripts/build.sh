#!/bin/sh
set -eu
. "$(dirname "$0")/env.sh"
cd "$PROJECT_DIR"
python scripts/build-settings.py "${1:---demo}"
pebble build
python scripts/package-pbw.py "${1:---demo}"
mkdir -p dist
if [ "${1:---demo}" = '--demo' ]; then
  cp build/pebble-hood.pbw dist/pebble-hood-demo.pbw
else
  cp build/pebble-hood.pbw dist/pebble-hood.pbw
fi
