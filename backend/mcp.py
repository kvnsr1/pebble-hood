"""Official MCP transport, strictly limited to portfolio reads and discovery."""

import json
import time
import httpx
from .providers import ProviderError

RESOURCE = "https://agent.robinhood.com/mcp/trading"
READ_TOOLS = frozenset(
    {"get_accounts", "get_portfolio", "get_equity_positions", "get_equity_quotes"}
)
META = "https://agent.robinhood.com/.well-known/oauth-authorization-server/mcp/trading"
PROTECTED = (
    "https://agent.robinhood.com/.well-known/oauth-protected-resource/mcp/trading"
)


def metadata(client):
    r = client.get(META)
    r.raise_for_status()
    m = r.json()
    # Pin discovered origins and issuer. Never follow arbitrary metadata URLs.
    expected = {
        "issuer": RESOURCE,
        "authorization_endpoint": "https://robinhood.com/oauth",
        "token_endpoint": "https://api.robinhood.com/oauth2/token/",
        "registration_endpoint": "https://agent.robinhood.com/oauth/trading/register",
    }
    if any(m.get(k) != v for k, v in expected.items()) or "S256" not in m.get(
        "code_challenge_methods_supported", []
    ):
        raise ProviderError("OAUTH_METADATA_CHANGED")
    return m


class MCP:
    def __init__(self, vault, client=None):
        self.vault = vault
        self.client = client or httpx.Client(timeout=20, follow_redirects=False)
        self.session = None
        self.seq = 0
        self.schemas = {}
        self.version = "2025-03-26"

    def close(self):
        self.client.close()

    def access_token(self):
        t = self.vault.get("oauth")
        if not t:
            raise ProviderError("AUTH_REQUIRED")
        if t.get("expires_at") is None or t["expires_at"] > time.time() + 60:
            return t["access_token"]
        if not t.get("refresh_token"):
            raise ProviderError("AUTH_EXPIRED")
        m = metadata(self.client)
        r = self.client.post(
            m["token_endpoint"],
            data={
                "grant_type": "refresh_token",
                "refresh_token": t["refresh_token"],
                "client_id": t["client_id"],
                "resource": RESOURCE,
            },
        )
        if r.status_code in (400, 401, 403):
            raise ProviderError("AUTH_EXPIRED")
        if r.status_code == 429:
            raise ProviderError("RATE_LIMITED")
        if r.status_code != 200:
            raise ProviderError("PROVIDER_FAILURE")
        n = r.json()
        if not isinstance(n.get("access_token"), str):
            raise ProviderError("PROVIDER_FAILURE")
        t.update(n)
        t["expires_at"] = (
            time.time() + float(n["expires_in"])
            if n.get("expires_in") is not None
            else None
        )
        self.vault.put("oauth", t)
        return t["access_token"]

    def rpc(self, method, params=None, notification=False, _retry_auth=True):
        if method not in (
            "initialize",
            "notifications/initialized",
            "tools/list",
            "tools/call",
        ):
            raise ValueError("Method denied")
        if method == "tools/call" and (params or {}).get("name") not in READ_TOOLS:
            raise ValueError("Tool denied")
        self.seq += 1
        body = {"jsonrpc": "2.0", "method": method}
        if not notification:
            body["id"] = self.seq
        if params is not None:
            body["params"] = params
        headers = {
            "Authorization": "Bearer " + self.access_token(),
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": self.version,
        }
        if self.session:
            headers["Mcp-Session-Id"] = self.session
        with self.client.stream("POST", RESOURCE, headers=headers, json=body) as r:
            if r.status_code == 401 and _retry_auth:
                token = self.vault.get("oauth")
                if token and token.get("refresh_token"):
                    token["expires_at"] = 0
                    self.vault.put("oauth", token)
                    return self.rpc(method, params, notification, _retry_auth=False)
            if r.status_code in (401, 403):
                raise ProviderError("AUTH_EXPIRED")
            if r.status_code == 429:
                raise ProviderError("RATE_LIMITED")
            if r.status_code not in (200, 202):
                raise ProviderError("PROVIDER_FAILURE")
            if r.headers.get("Mcp-Session-Id"):
                self.session = r.headers["Mcp-Session-Id"]
            if notification:
                return {}
            data = None
            size = 0
            if "text/event-stream" in r.headers.get("content-type", ""):
                lines = []
                for line in r.iter_lines():
                    size += len(line)
                    if size > 1048576:
                        raise ProviderError("RESPONSE_TOO_LARGE")
                    if line.startswith("data:"):
                        lines.append(line[5:].lstrip())
                    elif not line and lines:
                        candidate = json.loads("\n".join(lines))
                        lines = []
                        if candidate.get("id") == self.seq:
                            data = candidate
                            break
            else:
                chunks = []
                for chunk in r.iter_bytes():
                    size += len(chunk)
                    if size > 1048576:
                        raise ProviderError("RESPONSE_TOO_LARGE")
                    chunks.append(chunk)
                data = json.loads(b"".join(chunks))
        if not data or data.get("id") != self.seq or "error" in data:
            raise ProviderError("PROVIDER_FAILURE")
        result = data.get("result", {})
        if result.get("isError"):
            raise ProviderError("PROVIDER_FAILURE")
        return result

    def discover(self):
        result = self.rpc(
            "initialize",
            {
                "protocolVersion": self.version,
                "capabilities": {},
                "clientInfo": {"name": "pebble-hood", "version": "0.1.0"},
            },
        )
        self.version = result.get("protocolVersion", self.version)
        if self.version not in ("2025-03-26", "2025-06-18", "2025-11-25"):
            raise ProviderError("PROTOCOL_UNSUPPORTED")
        self.rpc("notifications/initialized", notification=True)
        cursor = None
        seen = set()
        for _ in range(20):
            result = self.rpc("tools/list", {"cursor": cursor} if cursor else {})
            for tool in result.get("tools", []):
                if tool.get("name") in READ_TOOLS:
                    self.schemas[tool["name"]] = tool
            cursor = result.get("nextCursor")
            if not cursor:
                return self.schemas
            if cursor in seen:
                break
            seen.add(cursor)
        raise ProviderError("PAGINATION_LIMIT")

    def call(self, name, arguments):
        if name not in READ_TOOLS:
            raise ValueError("Tool denied")
        if name not in self.schemas:
            raise ProviderError("SCHEMA_UNVERIFIED")
        import jsonschema

        try:
            jsonschema.validate(arguments, self.schemas[name]["inputSchema"])
            result = self.rpc("tools/call", {"name": name, "arguments": arguments})
            if self.schemas[name].get("outputSchema"):
                jsonschema.validate(
                    result.get("structuredContent"), self.schemas[name]["outputSchema"]
                )
            return result
        except jsonschema.ValidationError:
            raise ProviderError("PROVIDER_SHAPE_CHANGED") from None
