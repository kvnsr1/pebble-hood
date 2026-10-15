# ChatGPT Sites hosting compatibility test

On 2026-10-15, a private test Site was successfully published:

https://pebble-hood-connection-test.kvnsr1.chatgpt.site

It contains only an explanatory page and the synthetic `/probe.json` response. Its access policy has exactly the owner and no groups/external visitors. It contains no brokerage credentials or data. This test checks the Sites access boundary; a production backend port, hosted database/encryption checks and Robinhood login remain outstanding.

## Observed results

Actual HTTPS requests from the project workspace, with no browser cookies and redirects disabled:

| Request | Response | Demo JSON received |
| --- | --- | --- |
| No authorization | 401, HTML sign-in page | No |
| Ordinary backend-style `Authorization: Bearer` with a synthetic view token | 401, HTML sign-in page | No |
| Supported `OAI-Sites-Authorization` using the existing Site service credential | 200, JSON | Yes |

The service credential was obtained through native Sites metadata and kept only in session memory. It was sent only to this exact Site origin. No credential was created or rotated just to perform the test. It was not embedded in the phone/watch code, written to a file, printed, or committed. The safe results are in [sites-access-probe.json](sites-access-probe.json).

These results establish that the private Site supports authenticated requests without browser identity when using its service credential. The current Pebble Hood phone adapter sends its own backend view token, which does not satisfy the additional Sites sign-in boundary. A secure, supported phone authentication path still needs verification before adopting Sites for live portfolio data. Signing into a Site in Safari does not by itself establish PebbleKit JS background access.

## Physical-phone diagnostic

[pebble-sites-test.pbw](../dist/pebble-sites-test.pbw) is a separate diagnostic app with UUID `784cc80b-6710-4f06-9988-7c8b0bcd3150`. It was compiled for Flint and Emery. Its manifest grants Internet permission only to the test Site hostname. It contains no Sites service credential, live backend token, or brokerage token. It has no trading operations. Back closes it; Select retries.

The cloud installation succeeded after the phone connected. The actual iPhone baseline logged `NETWORK_OR_PERMISSION`, status 0 and no JSON marker for both requests. This does not distinguish permission denial, CORS, DNS/TLS failure or another network issue; it is not an observed HTTP 401 from the phone. The earlier 401 results above are from the workspace HTTP client. See the JSON result for the latest observed status. Both diagnostic binaries built; native rendering and physical button behavior remain unchecked.

When the Pebble phone app is open with cloud Dev Connection enabled:

```sh
./scripts/build-sites-probe.sh
./scripts/pebble.sh install --cloudpebble dist/pebble-sites-test.pbw
```

The first run tests a request without an extra authorization header and a request with a synthetic backend view token. Both request normal cookie handling, and the app distinguishes HTTP 401 from network/permission failure and timeout. It sends only short result labels to the watch and logs only safe states, status numbers and a boolean JSON-marker result.

To test whether Pebble can reuse normal ChatGPT browser authentication:

1. In the Pebble iPhone app, open **Sites Test → Settings**.
2. Sign in with your ChatGPT account if prompted. No Robinhood sign-in is involved.
3. Tap **Return to Pebble and test access** on the test page.
4. The diagnostic retries the requests and labels its safe phone log result `after_chatgpt_signin`. HTTP 200 plus the correct marker would establish cookie-based access for that phone session. HTTP 401 would show that the browser session is not available to the phone's background requests; zero indicates a network/permission failure instead. Ongoing session renewal would still need testing even after an initial success.

The private Site is unchanged in audience. No service credential needs to be copied into chat or the watch. This cookie-sharing check remains unverified until a real phone completes it.

## Repeat the server-side check

With the existing project Python dependencies:

```sh
.tools/venv/bin/python scripts/probe_sites.py https://pebble-hood-connection-test.kvnsr1.chatgpt.site
```

An existing Site service credential can optionally be supplied locally via hidden input/stdin using `--service-token-stdin`. Send it only to its matching Site; never place it in a command argument, source, chat, or PBW. No raw response body, authorization header, cookie or redirect query is printed.

No separate Render or Cloudflare account/service was created. This test does not establish Sites billing or usage limits. The watch portfolio demo and the Python backend remain available independently.
