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

Alternatively use `./scripts/pebble.sh login` followed by `install --cloudpebble PATH_TO_PBW`. Use the same Pebble account as the phone, with cloud Developer Connection enabled. Direct cloud installation of the demo to the user's connected physical watch succeeded on 2026-10-15. These current conventions also match the user's pebble-calendar project and current SDK documentation.

## Current CloudPebble: browser build and Dev Connection

You can build and install the demo without installing a local SDK.

1. Open [Import pebble-hood into CloudPebble](https://cloudpebble.repebble.com/ide/import/github/kvnsr1/pebble-hood). Sign in with the **same Pebble account** used in your Pebble phone app. Import branch `main` as **Pebble C SDK** if asked. GitHub Repo Sync is optional for importing this public repository; it is only needed to push edits back.
2. In project **Settings**, confirm **Emery / Pebble Time 2** for Time 2, or **Flint / Pebble 2 Duo** for Duo. The repository declares both. Keep `src/pkjs/settings.js` at its default `demo: true`, `backend: ""` for the first install. Do not enter Robinhood credentials here.
3. Open **Build & Run** and compile. After a successful build, under **Run On**, open **Phone** and choose **New Cloud Dev Connection**.
4. With the phone app open and the watch connected, its Devices → watch menu should say **Connected to CloudPebble**. Click **Install and Run** in CloudPebble. Launch Pebble Hood; its sample portfolio is marked **DEMO**. CloudPebble's ordinary build can retain the name Pebble Hood rather than the locally packaged Hood Demo name.

If the phone shows an IP address instead, it is using LAN mode. Turn off **Use LAN developer connection** under Settings → Phone → Connectivity, then toggle the watch's **Dev Connection** off/on. CloudPebble uses the cloud proxy and does not connect directly to that IP. With the current phone app choose **New Cloud Dev Connection**; the older **Cloud Dev Connection** and **Local Dev Connection** options use earlier sign-in systems. The computer and phone do not need to share Wi-Fi for cloud mode.

CloudPebble builds the native C app and bundles PebbleKit JS. The private Python backend runs separately, and real portfolio access still needs the browser login and field verification described in [Robinhood access](robinhood-access.md). Demo mode requires neither.

For a future configured build, edit `src/pkjs/settings.js` in CloudPebble to your HTTPS backend origin and `demo: false`; configure equivalent Internet permission in project settings if available, or download the PBW and apply `scripts/package-pbw.py` locally. The IDE generates its own manifest, so verify the resulting permissions. Do not put brokerage credentials or tokens in the CloudPebble project.

These steps follow the current [CloudPebble guide](https://developer.repebble.com/sdk/cloud/) and [Developer Connection guide](https://developer.repebble.com/guides/tools-and-resources/developer-connection/). Import/build/install in an authenticated CloudPebble account has not been exercised from this workspace; the verified local build and emulator results are in `verification.md`.

## Troubleshooting

- **Set up on phone:** configured build needs pairing/settings. Demo should not show this after startup.
- **Reconnect account:** phone token was revoked or Robinhood authentication expired. Re-pair/reconnect as appropriate; do not paste brokerage tokens into settings.
- **Live setup pending:** authentication or response mapping is not verified. Follow `robinhood-access.md`.
- **Phone disconnected:** reconnect Core; refresh. A timeout can also mean its JS bridge is unavailable.
- **No internet:** network/HTTPS request failed or timed out; this cannot distinguish DNS/TLS failure from absent connectivity.
- **Provider unavailable:** server/schema/data error. Cached data stays visibly old. Inspect local safe status codes, not credential-bearing HTTP logs.
- **Stale:** older than five minutes, reported provider failure, or clock mismatch. Long-closed markets can legitimately have old quotes; the app deliberately does not call them fresh.
