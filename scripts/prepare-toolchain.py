#!/usr/bin/env python3
"""Allow the CLI's temporary SDK link in a workspace where /var/tmp is read-only."""

import os
from pathlib import Path
import sysconfig

if not os.access("/var/tmp", os.W_OK):
    module = Path(sysconfig.get_paths()["purelib"]) / "pebble_tool/sdk/__init__.py"
    original = module.read_text()
    updated = original.replace(
        'tmp_link = "/var/tmp/pebble-sdk"', 'tmp_link = "/tmp/pebble-hood-sdk"'
    )
    if original != updated:
        module.write_text(updated)
        print("CLI temporary SDK link moved to /tmp for this restricted workspace.")
