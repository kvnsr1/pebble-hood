# Official Robinhood access and remaining verification

**Live portfolio access has not been verified.** The working demo, OAuth utility, MCP transport and explicit mapping engine are implemented. A browser login and verification of actual response fields are still required before live display. There is no unofficial API, scraping, password collection or LLM in the data path.

## Evidence from 2026-10-15

[Onboarding an external agent](https://robinhood.com/us/en/support/articles/agentic-trading-overview/) documents localhost clients and read access to all Robinhood accounts, positions and transactions. It also describes onboarding that prompts creation of an MCP account. Whether viewing alone can skip that onboarding was not established; do not open/fund an account automatically.

[Trading with your agent](https://robinhood.com/us/en/support/articles/trading-with-your-agent/) lists `get_accounts`, `get_portfolio`, `get_equity_positions` and `get_equity_quotes`. Quotes are documented for up to 20 symbols. These names are the entire financial-operation allowlist. Review/order/cancel/transfer/watchlist-mutation tools are denied in code, even if the server offers them.

Actual unauthenticated HTTP findings, reproducible with `python scripts/probe_robinhood.py`:

| Question | Observed result |
| --- | --- |
| MCP initialize | HTTP 401 with protected-resource metadata challenge. GET endpoint returns 405; POST is required. |
| Personal custom client | Discovery works; public-client dynamic registration using loopback callback returned HTTP 200 with client ID/name/redirect URIs/auth method. This proves registration, not account authorization. |
| Browser authorization | Metadata advertises `https://robinhood.com/oauth`, authorization code, PKCE S256, public client (`none`). |
| Refresh | `refresh_token` grant advertised. Issuance, token lifetime, rotation and successful refresh have not been tested with an account. Code retains rotated tokens encrypted. |
| Scopes | Only `internal` advertised by resource and authorization metadata. No read-only OAuth scope found. Local read allowlisting does **not** reduce the token's server-side privileges. |
| Account coverage | Documentation says all accounts are readable; not verified against your accounts. Agent trading is limited to its special account. |
| Schemas and fields | `tools/list` requires authentication. No authenticated schemas or account fields were available. Explicit mapping is required; nothing is guessed. |
| Rate limits | No numerical server quota verified. Local cache/cooldown is 60 seconds; quotes batched by 20; 429 becomes `RATE_LIMITED`. |
| Portfolio history | No authoritative historical portfolio series verified. Equity OHLC bars are not portfolio history and are not requested. |
| Revocation | No revocation endpoint advertised in observed metadata. Disconnect deletes local tokens; revoke the connected agent in Robinhood too. |

The non-secret protocol response is in [robinhood-probe.json](robinhood-probe.json). The one-off registration probe did not authenticate an account or retain a token. It did not open an MCP account.

## Connect on your computer

After [backend setup](setup.md), run from the repository with its environment loaded:

```sh
. .tools/venv/bin/activate
set -a
. ./.env
set +a
python -m backend.manage connect
```

The command starts a five-minute callback listener at `http://127.0.0.1:8765/callback`, registers a public client, and opens the actual Robinhood browser authorization URL. Sign in there and review any MCP-account onboarding and consent. Do not paste a password, authorization code or token into chat or the Pebble settings page. The callback validates state and issuer, exchanges the code with PKCE, and stores tokens encrypted. If deploying remotely, use `ssh -L 8765:127.0.0.1:8765 YOUR_SERVER` and open the printed authorization URL on the computer running that tunnel. This tunneled redirect has not been tested with Robinhood.

Then:

```sh
python -m backend.manage inspect
```

This initializes MCP and lists only allowlisted read tool schemas into `.private/tool-schemas.json`. It prints a schema fingerprint, never account data. It does not execute a trade or call other tools. Inspect the schemas locally to determine required arguments. For each needed read, pass arguments that actually match its discovered input schema:

```sh
python -m backend.manage read --tool get_accounts --arguments '{}'
python -m backend.manage export-inspection --tool get_accounts --file .private/accounts-inspection.json
```

`{}` is valid only if the discovered schema allows it; the utility validates first. Repeat for portfolio, positions and quotes using account identifiers obtained locally. `read` stores responses encrypted; `export-inspection` is an explicit private, mode-0600 local export for inspecting field structure. These exports contain financial data: keep them in ignored `.private/`, delete when finished. No need to send them to an LLM.

## Explicit field mapping

Copy `backend/mapping.template.json` to `.private/mapping.json`. Null paths intentionally make the template unusable; they are **not** guesses at Robinhood's format. Fill in JSON Pointers based on the actual responses, relative to MCP `structuredContent` (or the decoded single JSON text content). Fields under `fields` are relative to each item/object. Optional missing quote/cost/return fields can remain null. Required account, position, coverage and timestamp fields must be verified.

- `arguments` must match the actual tool's input schema. Values `$account`, `$symbols`, `$cursor` are replaced with the selected account, ≤20 symbols or cursor. There is no expression evaluation.
- `items` points to an array; `object` selects the portfolio object. `next_cursor` is null for a verified unpaginated response. If pagination exists, map it and include `$cursor` in the arguments; adapters fail on loops/overflow. If the provider rejects a null first cursor, its contract needs an explicit adapter change before enabling it.
- `asset_class_values` maps observed provider values to `equity`/`etf`. Unexpected position types fail closed. Unsupported non-equities must be identified in the portfolio's mapped `unsupported` list with kind/count. If the provider represents this differently, adapt that mapping first; do not substitute an empty list.
- `currency` must be USD. Financial values must be decimal **strings**; floats are rejected. Timestamps must be epoch seconds or ISO-8601 with a zone. For authoritative Today metrics, `session` must map to the provider's verified `YYYY-MM-DD` session date; a date other than the current America/New_York date makes Today unavailable. Quote time must reflect the provider observation, not fetch time.
- Set `total_includes_all_assets` only after checking the provider total includes cash and unsupported classes/liabilities as appropriate. Otherwise total displays unavailable.
- Keep `today_is_authoritative` false unless the provider field semantics, time window, currency, deposits/withdrawals and corporate-action treatment are verified. Never derive it from balance changes or current holdings at old prices.
- Set `reviewed: true` and the exact printed `schema_sha256` only after that review. Full tool-schema hash changes disable the mapping.

```sh
python -m backend.manage install-mapping --file .private/mapping.json
```

In Pebble settings select **Robinhood**, choose an account, save, and compare the values/times against Robinhood before relying on it. Mapping logic is tested with deliberately synthetic schemas; **there is no validated Robinhood mapping shipped**. If the actual supported interface cannot expose the required coverage, keep using Demo and ask Robinhood support about supported read access. A manual export/import provider is a possible alternative; unofficial APIs would require a separate decision.

## Disconnect

Phone settings → **Disconnect this phone** revokes its backend bearer token and clears phone/watch data when the phone can deliver the clear message. To remove the brokerage connection and all paired phones:

```sh
python -m backend.manage disconnect
```

Also remove/revoke Pebble Hood under Robinhood's connected-agent settings. No remote revocation endpoint is invented. Delete any deliberate local inspection exports. An offline watch cannot be remotely erased; reconnect it or uninstall the app to remove its saved summary. Its local hide-balances setting works without a phone and survives reconnection.
