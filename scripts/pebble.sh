#!/bin/sh
set -eu
. "$(dirname "$0")/env.sh"
cd "$PROJECT_DIR"
exec pebble "$@"
