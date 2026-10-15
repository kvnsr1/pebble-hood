# Verification

Verified in the Linux workspace on 2026-10-15. The standalone demo was also installed on the user's connected physical watch through the authenticated CloudPebble cloud Developer Connection; the CLI reported **App install succeeded**. Live brokerage access, public HTTPS deployment, physical button navigation and battery life remain unverified.

## Physical installation

The official Pebble browser sign-in completed, the cloud proxy authenticated, and the phone connected. `./scripts/pebble.sh install --cloudpebble dist/pebble-hood-demo.pbw` successfully transferred the compiled demo. This verifies the direct cloud installation route, independently of the browser IDE. It does not establish live Robinhood access or physical UI behavior. Authentication files remain in ignored local SDK storage, outside source control.

## Build

Pinned pebble-tool 5.0.40 and SDK 4.33.1 compile both declared targets:

| Target | Display | App code + static RAM | Heap available | Resources |
| --- | --- | --- | --- | --- |
| Flint / Pebble 2 Duo | 144×168 monochrome | 22,695 bytes / 64KiB | 42,841 bytes | 4,260 bytes |
| Emery / Pebble Time 2 | 200×228 color | 22,739 bytes / 128KiB | 108,333 bytes | 4,309 bytes |

Both demo and configured build modes were built. The configured test artifact used a reserved `.invalid` hostname and was kept under ignored `.tools/`; it is not a usable public service. Its PBW manifest was checked for version 2, both target binaries/resources, and Internet permission restricted to that hostname. The installable artifact in `dist/` is the standalone demo, containing both platforms and no Internet permission.

The SDK's linker emits its existing RWX-segment warning. Source compilation passes; no physical memory/battery measurements are claimed. Formatting is constrained to ES5-compatible trailing commas for the SDK's older JS bundler.

## Automated checks

`./scripts/test.sh`: **38 Python tests and 23 Node tests pass**. Coverage includes:

- Exact decimal fractional arithmetic, negative/zero bases, missing values, upper-range precision and signed zero.
- Stable demo fixtures, supported-holdings sorting and full account total independent of the equities subtotal.
- Encrypted vault records, single-use pairing, bearer authentication, pagination and revocation.
- Backend cache age, stale fallback and failed-refresh cooldown.
- MCP read-operation allowlist, denied mutations, 401/403/429/500, input-schema checks, SSE discovery, token rotation and one refresh retry when lifetime is unknown.
- Explicit mapping against synthetic schemas, schema fingerprints, pointers and timestamp zones. These synthetic keys are not Robinhood field assertions.
- Bounded messages, missing/long fields, hidden balances and rejection of unapproved chart history kinds.
- Phone setup state, stale age retention, expired-auth clear, late responses after disconnect and serialized refresh requests.
- Browser-only connection privileges separate from the phone's view bearer; Secure/HttpOnly/SameSite cookies, device binding, CSRF, PKCE, issuer/state validation, replay prevention, cancellation, expiry and redacted token failures.
- Reconnect clears prior backend financial data; failed sign-in preserves it. Broker disconnect revokes all paired phones. Deployment-generated encryption secrets survive vault reopen.
- Settings preserves the Pebble nonce across OAuth and clears temporary browser storage, keeps canceled-login feedback visible, and ignores late account-list responses after a source change.
- The separate Sites diagnostic distinguishes sign-in rejection from network failure, limits watch messages, avoids a service credential in client code, and retries after returning from the normal ChatGPT sign-in webview.

`ruff check backend scripts test` and JS syntax checks pass. FastAPI's installed test client emits a dependency deprecation warning; tests still pass.

`.tools/venv/bin/python scripts/smoke-backend.py` starts a real Uvicorn process with an ephemeral encrypted vault. Loopback HTTP checks passed for health, static settings, pairing, authenticated demo retrieval and revocation. This does not establish public TLS or iPhone-webview compatibility.

## Settings browser checks

`scripts/check-settings.py` passed in actual system Chromium with Playwright 1.58.0, at a 390×844 mobile viewport. It starts a temporary local HTTPS backend and uses synthetic registration/token responses plus an intercepted authorization page. The browser completed an actual cross-origin redirect and return, retained the Secure browser cookie and Pebble return context, removed temporary session storage, showed the live-mapping gate, and handled cancellation without JavaScript errors. Horizontal overflow was checked and full-page images inspected for readability. This does not establish real Robinhood authorization or iPhone webview support.

Screenshots: [setup](screenshots/settings-setup.png), [connect](screenshots/settings-connect.png), [verification needed](screenshots/settings-verification.png), [canceled](screenshots/settings-canceled.png). Reproduction and deployment steps are in [phone-connect.md](phone-connect.md).

## Emulator checks

Actual SDK QEMU runs, with bundled PebbleKit JS and deterministic synthetic values. Main screens use native menus/action menus/scroll layers. The harness also injects synthetic AppMessage pages and status codes for deterministic failures, unusual values and interrupted transfers; these do not demonstrate real Robinhood failures or actual Bluetooth disconnection.

The native-size PNGs were visually inspected for readable text, contrast, wrapping and expected navigation. The holdings age is fixed above its scrolling menu. Main totals compact large values and the exact total remains in Info. Ticker/company/detail fields wrap. Local hide survives reconnect, and error footers retain data age.

An incomplete page with a different proposed portfolio value is compared against the previous rendered summary before commit. Both platforms preserve the previous view. The harness checks the native frame size and that expected portfolio screens still show the app header, preventing accidental launcher screenshots from counting as success.

| Case | Monochrome | Color |
| --- | --- | --- |
| Overview | [Flint](screenshots/flint-overview.png) | [Emery](screenshots/emery-overview.png) |
| Options | [Flint](screenshots/flint-options.png) | [Emery](screenshots/emery-options.png) |
| Holdings | [Flint](screenshots/flint-holdings.png) | [Emery](screenshots/emery-holdings.png) |
| Detail | [Flint](screenshots/flint-detail.png) | [Emery](screenshots/emery-detail.png) |
| Cost / investment return | [Flint](screenshots/flint-detail-return.png) | [Emery](screenshots/emery-detail-return.png) |
| Hidden balances | [Flint](screenshots/flint-hidden.png) | [Emery](screenshots/emery-hidden.png) |
| Empty account | [Flint](screenshots/flint-empty.png) | [Emery](screenshots/emery-empty.png) |
| First setup | [Flint](screenshots/flint-setup.png) | [Emery](screenshots/emery-setup.png) |
| Expired auth | [Flint](screenshots/flint-auth-expired.png) | [Emery](screenshots/emery-auth-expired.png) |
| Live mapping pending | [Flint](screenshots/flint-live-pending.png) | [Emery](screenshots/emery-live-pending.png) |
| Phone offline | [Flint](screenshots/flint-phone-offline.png) | [Emery](screenshots/emery-phone-offline.png) |
| No internet | [Flint](screenshots/flint-no-internet.png) | [Emery](screenshots/emery-no-internet.png) |
| Provider error | [Flint](screenshots/flint-provider-error.png) | [Emery](screenshots/emery-provider-error.png) |
| Stale values | [Flint](screenshots/flint-stale.png) | [Emery](screenshots/emery-stale.png) |
| Offline cache | [Flint](screenshots/flint-offline-cached.png) | [Emery](screenshots/emery-offline-cached.png) |
| Large negative balance | [Flint](screenshots/flint-large-negative.png) | [Emery](screenshots/emery-large-negative.png) |
| Long ticker | [Flint](screenshots/flint-long-ticker.png) | [Emery](screenshots/emery-long-ticker.png) |
| Missing quote / cost | [Flint](screenshots/flint-missing-detail.png) | [Emery](screenshots/emery-missing-detail.png) |

Reproduce after building:

```sh
./scripts/reset-emulator.sh
.tools/venv/bin/python scripts/capture-emulator.py flint
./scripts/reset-emulator.sh
.tools/venv/bin/python scripts/capture-emulator.py emery
```

The script uses one persistent SDK connection, an SDK overview screenshot, and QEMU's native framebuffer capture for subsequent screens, the same monitor path used by the SDK's fast capture support. Some idle color frames show QEMU's simulated dim backlight; the SDK overview captures the app's undimmed colors. The phone relay's repeated screenshot transfers occasionally timed out during initial testing, so image capture is kept off that channel. `reset-emulator.sh` stops only project-recorded emulator processes and clears their PID metadata, preserving emulated flash. No other project is changed.

Navigation regression fixes were verified: ActionMenu opens the native result window; Back returns detail → holdings → overview; clearing/auth loss keeps the root window alive. Real iPhone pairing, real network failures, physical button feel, battery life and real account comparisons remain required before treating this as a validated live portfolio viewer.

## Robinhood connection evidence

The unauthenticated official MCP POST returns a real 401 challenge. Protected-resource and authorization metadata were fetched; public-client registration returned 200 for both loopback and HTTPS callbacks. The HTTPS test used the reserved example URL `https://hood.example.com/oauth/robinhood/callback` and the response echoed it. No user authenticated, no real callback or brokerage response was obtained, and refresh success was tested only with mocked protocol responses. See [Robinhood access](robinhood-access.md) for precisely what remains unknown and the supported browser-login steps.

## ChatGPT Sites compatibility

The owner-private test Site was actually published and tested over HTTPS with synthetic data. Anonymous and ordinary backend-style authorization requests returned 401; the existing Sites service credential returned 200 and the expected JSON marker. A separate diagnostic PBW built for Flint and Emery. The diagnostic installed successfully on the user’s watch through the cloud connection. Actual iPhone baseline requests both logged `NETWORK_OR_PERMISSION` with status 0 and no JSON marker; their precise cause is unknown. After the user successfully signed into ChatGPT through Pebble settings and returned, both actual phone requests logged `SIGN_IN_REQUIRED`, HTTP 401, with no JSON marker. The user's screenshot shows the Site Internet permission enabled. Browser sign-in therefore did not establish background access on this phone. No service credential is in the PBW, no Site audience was widened, and no Robinhood data was used. See [Sites test](sites-test.md) and its recorded JSON for details. The probe is static; production server code, durable storage/encryption and hosted Robinhood OAuth have not been migrated or verified on Sites.
