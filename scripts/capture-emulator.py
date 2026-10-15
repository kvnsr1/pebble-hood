#!/usr/bin/env python3
"""Exercise real QEMU UI. Synthetic fixture injection also tests atomic messages."""

import json
import subprocess
import sys
import time
from pathlib import Path
from PIL import Image, ImageChops

from uuid import UUID
from libpebble2.communication import PebbleConnection
from libpebble2.communication.transports.websocket import WebsocketTransport
from libpebble2.services.appmessage import AppMessageService, ByteArray, CString, Uint32
from libpebble2.services.screenshot import Screenshot
from pebble_tool.commands.screenshot import ScreenshotCommand
from pebble_tool.commands.emucontrol import send_data_to_qemu, QemuButton


root = Path(__file__).resolve().parent.parent
platform = sys.argv[1] if len(sys.argv) > 1 else "flint"
if platform not in ("flint", "emery"):
    raise SystemExit("Use flint or emery")
keys = json.loads((root / "package.json").read_text())["pebble"]["messageKeys"]
out = root / "docs/screenshots"
out.mkdir(exist_ok=True)


def cli(*args):
    r = subprocess.run(
        [str(root / "scripts/pebble.sh"), *args, "--emulator", platform, "--vnc"],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if r.returncode:
        raise RuntimeError(r.stdout[-2500:])


def button(name, n=1):
    for _ in range(n):
        send_data_to_qemu(connection.transport, QemuButton(state=BUTTONS[name]))
        time.sleep(0.1)
        send_data_to_qemu(connection.transport, QemuButton(state=0))
        time.sleep(0.4)


def shot(name):
    time.sleep(0.35)
    frame = out / (platform + "-" + name + ".png")
    if name == "overview":
        rows = Screenshot(connection).grab_image()
        im = Image.frombytes(
            "RGB", (len(rows[0]) // 3, len(rows)), b"".join(bytes(row) for row in rows)
        )
    else:
        temp_dir = root / ".tools/tmp"
        (temp_dir / "frame_0000.ppm").unlink(missing_ok=True)
        im = ScreenshotCommand._grab_qemu_monitor_image_fast(
            metadata["qemu"]["monitor"], str(temp_dir), 0
        )
    assert im.size == ((144, 168) if platform == "flint" else (200, 228))
    if name in {
        "overview",
        "hidden",
        "empty",
        "stale",
        "incomplete-transfer",
        "offline-cached",
        "large-negative",
    }:
        assert im.getpixel((0, 32))[:3] == (0, 0, 0), (
            "Expected portfolio header; app may have exited"
        )
    im.save(frame)
    print(platform, name, flush=True)


def send(message):
    dictionary = {
        keys[k]: ByteArray(bytes(v))
        if isinstance(v, list)
        else CString(v)
        if isinstance(v, str)
        else Uint32(v)
        for k, v in message.items()
    }
    messages.send_message(app_uuid, dictionary)
    time.sleep(0.15)


def fixture():
    js = "const d=require('./src/pkjs/demo'),w=require('./src/pkjs/wire');process.stdout.write(JSON.stringify(w.packets(d.snapshot('demo-main',0,Math.floor(Date.now()/1000)-600),99,false)))"
    return json.loads(subprocess.check_output(["node", "-e", js], cwd=root))


cli("install", str(root / "dist/pebble-hood-demo.pbw"))
time.sleep(2)
# Keep one SDK connection throughout. Repeated short-lived CLI connections can
# leave the current pypkjs relay unresponsive during long scripted runs.
metadata = json.loads((root / ".tools/tmp/pb-emulator.json").read_text())[platform][
    "4.33.1"
]
connection = PebbleConnection(
    WebsocketTransport("ws://127.0.0.1:%d/" % metadata["pypkjs"]["port"])
)
connection.connect()
connection.run_async()
messages = AppMessageService(connection)
messages._current_txid = 100
app_uuid = UUID(json.loads((root / "package.json").read_text())["pebble"]["uuid"])
BUTTONS = {
    "back": QemuButton.Button.Back,
    "up": QemuButton.Button.Up,
    "select": QemuButton.Button.Select,
    "down": QemuButton.Button.Down,
}
# Reset deterministic page explicitly; UI actions below still exercise PKJS.
for message in fixture():
    if message["TYPE"] == 1:
        message["UPDATED"] = int(time.time())
    send(message)
shot("overview")
button("select")
shot("options")
button("select")
shot("holdings")
button("select")
shot("detail")
button("down", 5)
shot("detail-return")
button("back", 2)
# All menu actions use the actual phone bridge.
button("select")
button("down", 3)
button("select")
time.sleep(0.5)
shot("hidden")
button("select")
button("down", 3)
button("select")
time.sleep(0.5)
button("select")
button("down", 2)
button("select")
time.sleep(0.5)
# Empty state from explicit deterministic provider fixture, independent of stored account.
js = "const d=require('./src/pkjs/demo'),w=require('./src/pkjs/wire');process.stdout.write(JSON.stringify(w.packets(d.snapshot('demo-empty',0,Math.floor(Date.now()/1000)),98,false)))"
for m in json.loads(subprocess.check_output(["node", "-e", js], cwd=root)):
    send(m)
shot("empty")
button("select")
button("select")
shot("empty-holdings")
button("back")
send({"TYPE": 5})
for state, name in [
    ("SETUP", "setup"),
    ("AUTH_EXPIRED", "auth-expired"),
    ("SCHEMA_UNVERIFIED", "live-pending"),
    ("PHONE_OFFLINE", "phone-offline"),
    ("NO_INTERNET", "no-internet"),
    ("PROVIDER_FAILURE", "provider-error"),
]:
    send({"TYPE": 4, "ERROR": state})
    shot(name)
for message in fixture():
    send(message)
shot("stale")
# Incomplete page must not replace the current overview.
p = fixture()[0]
p["GEN"] = 100
p["VALUE"] = "$999.00"
send(p)
shot("incomplete-transfer")
a = Image.open(out / (platform + "-stale.png")).crop((0, 16, 130, 120))
b = Image.open(out / (platform + "-incomplete-transfer.png")).crop((0, 16, 130, 120))
assert ImageChops.difference(a, b).getbbox() is None, (
    "Incomplete transfer replaced the visible snapshot"
)
send({"TYPE": 4, "ERROR": "NO_INTERNET"})
shot("offline-cached")
# Large negative amount / long ticker / missing-data rendering uses synthetic data.
js = "const d=require('./src/pkjs/demo'),w=require('./src/pkjs/wire');let s=d.snapshot('demo-main',1,Math.floor(Date.now()/1000));s.total='-1234567890123.45';s.today=null;process.stdout.write(JSON.stringify(w.packets(s,101,false)))"
for m in json.loads(subprocess.check_output(["node", "-e", js], cwd=root)):
    send(m)
shot("large-negative")
button("select")
button("select")
shot("long-ticker")
button("select")
shot("fractional-detail")
button("back")
button("down")
button("select")
shot("missing-detail")
print("Atomic transfer check passed.", flush=True)

messages.shutdown()
connection.transport.ws.close()
