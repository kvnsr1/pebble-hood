#!/bin/sh
set -eu
. "$(dirname "$0")/env.sh"
cd "$PROJECT_DIR"
python -m pytest -q test
node --test test/*.test.js
