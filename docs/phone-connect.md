# Connect from Pebble iPhone settings

The browser connection flow is implemented and tested with synthetic responses. Robinhood's real registration endpoint accepted an HTTPS callback on 2026-10-15. Actual Robinhood login, its callback, iPhone webview compatibility, account responses and refresh remain unverified. No brokerage account has been connected.

## Deploy one backend

The prepared [Render Blueprint](../render.yaml) uses one Python service, one persistent disk and a generated secret. It needs no custom domain: Render supplies HTTPS. This is a **paid Starter service plus a 1 GB disk**; review Render's current price before creating it. No service or charge was created during development.

1. Open [Deploy pebble-hood on Render](https://render.com/deploy?repo=https://github.com/kvnsr1/pebble-hood). Sign in and review the service and storage charges before deploying. The Blueprint pins Python 3.12.14 and installs pinned backend dependencies. Automatic deployment of future Git commits is disabled.
2. Wait for `/health` at your assigned `https://…onrender.com` URL to return `{"ok":true}`. The backend uses Render's `RENDER_EXTERNAL_URL` for its callback. For a custom domain, set `HOOD_BACKEND_URL` to that HTTPS origin and redeploy before connecting.
3. Keep `HOOD_VAULT_SECRET` unchanged across deploys and back it up privately, separately from the disk. Render generates a random 256-bit value. The backend derives its Fernet key from that random secret with SHA-256. This is not a password-based scheme; do not substitute a human password. Existing non-Render deployments can keep using `HOOD_VAULT_KEY` instead.
4. The disk at `/var/data/hood` holds the encrypted SQLite vault, cached values and observed balances. Keep one instance and one Uvicorn worker. Do not switch to a free ephemeral service: it would lose authorization/history on restart.
5. In the service's private Shell, run `python -m backend.manage pair`. The resulting ten-minute, single-use setup code authorizes a phone and grants that browser session connection controls for 30 minutes. Enter it only in your own backend's Pebble settings page, never in chat or source control. A remote Render shell does not require installing tools locally.

The application disables access logging and never logs OAuth bodies or tokens. Keep proxy, tracing and hosting request logs from recording callback query strings, headers or bodies. OAuth necessarily returns a short-lived code in the callback query; verify the host's logging controls before real sign-in. The app immediately redirects to a clean URL and sends no-referrer/no-store headers. Render's [logging reference](https://render.com/docs/logging#http-request-logs) says HTTP request logs are generated for Pro workspaces and higher and include the requested URL. A paid Starter service does not require a Pro workspace. Do not enable request logging/tracing for this flow without verified query/header redaction. Render infrastructure behavior has not been tested from an authenticated account.

An existing server with Caddy is equally suitable; see [setup.md](setup.md#backend-and-https). Reviewed Render references: [Blueprint specification](https://render.com/docs/blueprint-spec), [default environment variables](https://render.com/docs/environment-variables), [persistent disks](https://render.com/docs/disks). HTTPS callback acceptance at registration does not prove the complete login flow works.

## Configure and install the watch build once

The installed **Hood Demo** is standalone; its configuration page cannot reach a backend. After deployment, build a configured package with your actual public URL:

```sh
export HOOD_BACKEND_URL=https://YOUR-SERVICE.onrender.com
./scripts/build.sh --live
./scripts/pebble.sh install --cloudpebble dist/pebble-hood.pbw
```

The hostname is public configuration, not a credential. The packaged build grants Internet permission only to that hostname. Existing Pebble cloud login can be reused while valid; keep the phone app open with cloud Dev Connection enabled. This install replaces Hood Demo because both use the same app UUID. These commands can be run in the project workspace; no local SDK is needed on your iPhone.

## Connect on iPhone

1. Open **Pebble Hood → Settings** in the Pebble iPhone app.
2. Enter the one-use setup code and tap **Authorize this phone**. This pairs the view token and creates a separate Secure, HttpOnly browser cookie. The phone's ordinary view token cannot start or disconnect Robinhood authorization by itself.
3. Tap **Connect Robinhood**. The app opens the discovered official Robinhood authorization page with PKCE and a five-minute, single-use state. Sign in only there. Review its broad `internal` authorization and any request to open an MCP account. This app restricts itself to four read tools, but the underlying token's scope is broader.
4. On return, settings reports that authorization is saved. Until the actual tool schemas and response mapping are reviewed, it explicitly says live data needs one-time verification and prevents saving an unavailable live account. Follow [the inspection/mapping steps](robinhood-access.md#explicit-field-mapping) on the server; this remains an operator step because no actual Robinhood response has been observed.
5. After verification, choose **Robinhood**, select an account, set balance privacy, and tap **Save to watch**. Compare values and observation times against Robinhood. You can choose **Demo** and save at any point without claiming live access.

OAuth stays in the same webview and uses session-only browser storage to preserve the Pebble return nonce and backend view token. This storage is cleared on return; brokerage tokens never enter it. Real Robinhood may refuse an embedded browser or move sign-in into Safari/the Robinhood app. If that loses the session, settings reports it instead of accepting an unbound callback. Reopen Pebble settings and use a fresh setup code. The [computer/loopback flow](robinhood-access.md#connect-on-your-computer) remains the fallback; do not copy authorization codes or tokens into chat.

## Reconnect and disconnect

Normal viewing uses the paired phone token; the browser connection-control session expires after 30 minutes. To reconnect later, tap **Enter setup code for connection controls**, obtain a new setup code, then reconnect. Re-pairing issues a new phone token: save settings afterward. No repeated browser login is required while refresh remains supported and successful; real refresh has not yet been verified.

Under **Disconnect**, **Disconnect this phone only** revokes its viewing token. **Disconnect Robinhood and paired phones** requires browser authorization plus CSRF, removes local brokerage tokens/cached financial data and revokes every paired phone. A reviewed field mapping is retained. It does not remotely revoke Robinhood's grant: also remove the connected agent in Robinhood. The current settings window returns a clear instruction to the watch. Other offline watches retain their cached summary until reconnect/uninstall.

Successful new authorization clears previous backend financial caches and observed balance history, so they are not reused for a different connection. Failed/canceled authorization preserves the previous connection. No financial mutation tools are exposed.

## Reproduce the browser checks

```sh
uv pip install --python .tools/venv/bin/python playwright==1.58.0
.tools/venv/bin/python scripts/check-settings.py
```

Requires installed `/usr/bin/chromium`. It starts an ephemeral loopback HTTPS server with a self-signed certificate accepted only by this local test, mocks official registration/token responses, intercepts the Robinhood browser page, and checks return context, cancellation, the live-data gate and 390-pixel layout. It uses no actual Robinhood or hosting credentials. Screenshots: [setup](screenshots/settings-setup.png), [connect](screenshots/settings-connect.png), [verification required](screenshots/settings-verification.png), [canceled](screenshots/settings-canceled.png). These are Chromium browser checks, not iPhone or physical-watch verification.
