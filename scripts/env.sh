#!/bin/sh
PROJECT_DIR=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
export PATH="$PROJECT_DIR/.tools/venv/bin:$PATH"
export XDG_DATA_HOME="$PROJECT_DIR/.tools/share"
export UV_CACHE_DIR="$PROJECT_DIR/.tools/uv-cache"
export npm_config_cache="$PROJECT_DIR/.tools/npm-cache"
# Isolate emulator metadata too; SDK defaults to a shared /tmp/pb-emulator.json.
mkdir -p "$PROJECT_DIR/.tools/tmp"
export TMPDIR="$PROJECT_DIR/.tools/tmp"
