#!/bin/sh
set -eu
. "$(dirname "$0")/env.sh"
cd "$PROJECT_DIR"
uv venv --allow-existing .tools/venv
uv pip install --python .tools/venv/bin/python 'pebble-tool==5.0.40' -r backend/requirements.txt 'pytest==9.1.1'
python scripts/prepare-toolchain.py
pebble sdk install 4.33.1
