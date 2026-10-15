"""Declare Core Internet permission narrowly for the chosen backend origin."""

import json
import os
import sys
import zipfile
from pathlib import Path
from urllib.parse import urlparse

root = Path(__file__).resolve().parent.parent
pbw = root / "build/pebble-hood.pbw"
demo = sys.argv[1] == "--demo"
with zipfile.ZipFile(pbw) as z:
    entries = [(i, z.read(i.filename)) for i in z.infolist()]
info = json.loads(next(d for i, d in entries if i.filename == "appinfo.json"))
info["manifestVersion"] = 2
info["usesPermissions"] = (
    []
    if demo
    else [
        {
            "name": "Internet",
            "parameters": {
                "domains": [urlparse(os.environ["HOOD_BACKEND_URL"]).hostname]
            },
        }
    ]
)
if demo:
    info["shortName"] = info["longName"] = "Hood Demo"
tmp = pbw.with_suffix(".tmp")
with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
    for i, d in entries:
        z.writestr(i, json.dumps(info).encode() if i.filename == "appinfo.json" else d)
tmp.replace(pbw)
