# Build, install and run

## Quick demo on iPhone

1. Install the current [Pebble mobile app](https://repebble.com/app) and pair your Time 2 or Pebble 2 Duo.
2. Download `dist/pebble-hood-demo.pbw` from this repository. AirDrop it to iPhone, or open it from Files/the share sheet in Pebble Core. If Core does not appear, use Developer Connection below.
3. Launch **Hood Demo**. Every value is synthetic and marked DEMO. No server, credentials or brokerage account is required.
4. Select → Holdings; select a ticker for details; Back returns. Select → Refresh is always available. Next account switches to the empty demo account. Up/Down on the overview switches between summary and status. Hide/show works locally, including offline.

The demo and configured builds share an app UUID: installing one replaces the other. A cached demo summary remains labeled DEMO until a fresh configured snapshot arrives. Demo preferences can persist across reinstalls; use Next account to return from the empty fixture.

## Reproducible SDK build

Python 3.12+, Node.js, `uv`, and the platform dependencies from [the current SDK install guide](https://developer.repebble.com/sdk/) are required. On Mac start with `brew install uv python@3.13 node`. On Linux install the documented compiler/emulator libraries for your distribution.

```sh
git clone https://github.com/kvnsr1/pebble-hood.git
cd pebble-hood
./scripts/setup.sh
./scripts/test.sh
./scripts/build.sh --demo
./scripts/pebble.sh install --emulator emery --vnc dist/pebble-hood-demo.pbw
# Or use --emulator flint
```

Pins: pebble-tool **5.0.40**, SDK **4.33.1**. Both declared targets build together. `.tools/` contains the isolated Python environment, Linux SDK and caches. On macOS the CLI may use its ordinary Application Support SDK directory. The temporary SDK-link workaround is only used when `/var/tmp` is read-only, following the existing pebble-calendar convention. It changes the isolated CLI, not firmware.

The bundled icon is already rendered. Regenerating it additionally requires CairoSVG/Pillow (`uv pip install --python .tools/venv/bin/python cairosvg==2.9.1 pillow==12.3.0`), then `.tools/venv/bin/python scripts/render-icon.py`.

The final packaging step adds Core manifest-version 2 and narrowly scoped Internet permission for your configured backend hostname. Demo needs no Internet permission. Use `scripts/build.sh`, not just `pebble build`, for the distributable package.

## Backend and HTTPS

This is a single-user server. Use **one** Uvicorn worker; SQLite and refresh serialization are intentionally simple. No database service, LLM or task queue is needed.

```sh
. .tools/venv/bin/activate
cp .env.example .env
chmod 600 .env
python scripts/init-key.py
# Edit HOOD_BACKEND_URL in .env to your own HTTPS origin.
set -a
. ./.env
set +a
uvicorn backend.app:create_app --factory --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
```

`init-key.py` fills an empty `HOOD_VAULT_KEY` in `.env` without printing it. Keep the key in your deployment's secret store, separate from encrypted backups of `.private/vault.sqlite`. Losing it requires reconnecting and pairing again. File permissions and full-disk encryption still matter; encryption cannot protect a compromised running server that has its key.

For a private VPS, point your hostname's DNS at it and put Caddy in front of the loopback server. `deploy/Caddyfile.example` terminates TLS and forwards to port 8000. Use a service supervisor (example in `deploy/pebble-hood.service.example`) with the repository as its working directory and `.env` as its environment file. Set correct absolute paths/user. Do not expose port 8000 publicly, enable access/body/debug logging, or place `.env`/`.private` under a static web root. The only unauthenticated endpoints serve static configuration, health and one-use pairing. Pairing is rate limited.

For local iPhone testing you still need a trusted HTTPS origin that forwards to this server. Use your existing trusted tunnel/reverse proxy; a phone cannot reach your computer through `localhost`. No hosted deployment or DNS was created during implementation.

Check `/health` through your HTTPS origin, then build with it:

```sh
set -a
. ./.env
set +a
./scripts/build.sh --live
```

This writes `dist/pebble-hood.pbw`. It contains your backend hostname, **no tokens**. A ready-made configured PBW cannot be supplied until that hostname exists. The checked-in installable artifact is the standalone demo.

## Pair the phone and select data

1. Install the configured PBW on your watch.
2. On the server: `python -m backend.manage pair` (same environment/key as the server).
3. In the Pebble phone app, open Pebble Hood's settings. Enter the generated ten-minute one-use **backend pairing code**. This is not a Robinhood credential.
4. Choose **Demo**, choose an account, optionally hide balances, then Save to watch. This configured mode exercises authenticated HTTPS to the backend using synthetic data.
5. For your actual brokerage data, complete [the supported Robinhood login and schema verification](robinhood-access.md), then choose **Robinhood** and your account in those settings. Until verified, the page reports the setup gate explicitly.

Configuration passes the device token through URL fragments (not query strings), removes it from the webview URL immediately, and returns it only to PebbleKit JS. The watch receives no token. The phone token can only use the view endpoints and revoke itself; it cannot initiate broker OAuth or MCP calls directly. The phone stores this token and one cached page in the Pebble app's storage. iOS/Pebble permissions may require approving the declared backend domain; physical Core behavior remains untested here.

## Developer Connection installation

In current Core, enable **Use LAN developer connection** under Phone → Connectivity, then **Dev Connection** for the watch in Devices. Use the address shown by the phone on your trusted LAN:

```sh
./scripts/pebble.sh install --phone PHONE_IP dist/pebble-hood-demo.pbw
# configured build:
./scripts/pebble.sh install --phone PHONE_IP dist/pebble-hood.pbw
```

Alternatively use `./scripts/pebble.sh login` followed by `install --cloudpebble PATH_TO_PBW`. These current conventions come from the user's pebble-calendar project and current SDK documentation; iPhone/physical-watch installation was not exercised in this workspace.

## Current CloudPebble

Use [cloudpebble.repebble.com](https://cloudpebble.repebble.com/), not the retired historical service. Import the GitHub repository as **Pebble C SDK** and select Flint/Emery. Plain compile runs the demo defaults. For a configured build, edit `src/pkjs/settings.js` to your HTTPS origin and `demo: false`; configure equivalent Internet permission in project settings if available, or download the PBW and apply `scripts/package-pbw.py` locally. The CloudPebble IDE generates its own manifest, so verify the resulting PBW's permissions. CloudPebble import/build was documented from current sources but not tested in an authenticated browser. The local scripted build is the verified workflow.

## Troubleshooting

- **Set up on phone:** configured build needs pairing/settings. Demo should not show this after startup.
- **Reconnect account:** phone token was revoked or Robinhood authentication expired. Re-pair/reconnect as appropriate; do not paste brokerage tokens into settings.
- **Live setup pending:** authentication or response mapping is not verified. Follow `robinhood-access.md`.
- **Phone disconnected:** reconnect Core; refresh. A timeout can also mean its JS bridge is unavailable.
- **No internet:** network/HTTPS request failed or timed out; this cannot distinguish DNS/TLS failure from absent connectivity.
- **Provider unavailable:** server/schema/data error. Cached data stays visibly old. Inspect local safe status codes, not credential-bearing HTTP logs.
- **Stale:** older than five minutes, reported provider failure, or clock mismatch. Long-closed markets can legitimately have old quotes; the app deliberately does not call them fresh.
