"""Browser OAuth for one private backend. No financial operations live here."""

import base64
import hashlib
import math
import secrets
from urllib.parse import urlencode, urlsplit

import httpx

from .mcp import RESOURCE, metadata
from .providers import ProviderError
from .store import digest

COOKIE = "__Host-hood_operator"
SESSION_TTL = 1800
FLOW_TTL = 300


def origin(value):
    value = value.rstrip("/")
    p = urlsplit(value)
    if (
        p.scheme != "https"
        or not p.hostname
        or p.username
        or p.password
        or p.path
        or p.query
        or p.fragment
    ):
        raise ProviderError("HTTPS_BACKEND_REQUIRED")
    return value


class BrowserOAuth:
    def __init__(self, vault, backend_url, clock, client_factory=None):
        self.vault = vault
        self.backend_url = backend_url
        self.clock = clock
        self.client_factory = client_factory or (
            lambda: httpx.Client(timeout=20, follow_redirects=False)
        )

    def session(self, cookie, device=None):
        if not cookie or len(cookie) > 100:
            return None
        key = "browser:" + digest(cookie)
        row = self.vault.get(key)
        if (
            not row
            or row["expires"] <= self.clock()
            or not self.vault.get(row["device"])
            or (device is not None and row["device"] != device)
        ):
            return None
        return key, row

    def authorize_browser(self, device):
        cookie = secrets.token_urlsafe(32)
        self.vault.put(
            "browser:" + digest(cookie),
            {
                "device": device,
                "csrf": secrets.token_urlsafe(32),
                "expires": self.clock() + SESSION_TTL,
            },
        )
        return cookie

    def require_operator(self, cookie, device, csrf):
        session = self.session(cookie, device)
        if not session or not secrets.compare_digest(session[1]["csrf"], csrf or ""):
            raise ProviderError("BROWSER_AUTH_REQUIRED")
        return session

    def start(self, cookie, device, csrf):
        key, row = self.require_operator(cookie, device, csrf)
        callback = origin(self.backend_url) + "/oauth/robinhood/callback"
        if self.clock() - row.get("attempted", -60) < 60:
            raise ProviderError("RATE_LIMITED")
        row["attempted"] = self.clock()
        self.vault.put(key, row)
        verifier = secrets.token_urlsafe(48)
        state = secrets.token_urlsafe(32)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        with self.client_factory() as client:
            m = metadata(client)
            if m.get("scopes_supported") != ["internal"]:
                raise ProviderError("OAUTH_METADATA_CHANGED")
            response = client.post(
                m["registration_endpoint"],
                json={
                    "client_name": "Pebble Hood personal viewer",
                    "redirect_uris": [callback],
                    "grant_types": ["authorization_code", "refresh_token"],
                    "response_types": ["code"],
                    "token_endpoint_auth_method": "none",
                },
            )
            if response.status_code not in (200, 201):
                raise ProviderError("REGISTRATION_FAILED")
            registration = response.json()
        if (
            not isinstance(registration.get("client_id"), str)
            or not registration["client_id"]
            or registration.get("redirect_uris") != [callback]
            or registration.get("token_endpoint_auth_method") != "none"
        ):
            raise ProviderError("REGISTRATION_FAILED")
        if row.get("flow"):
            self.vault.delete(row["flow"])
        flow_key = "oauth-flow:" + digest(state)
        self.vault.put(
            flow_key,
            {
                "browser": key,
                "device": device,
                "expires": self.clock() + FLOW_TTL,
                "verifier": verifier,
                "client_id": registration["client_id"],
                "callback": callback,
                "issuer_required": m.get(
                    "authorization_response_iss_parameter_supported"
                )
                is True,
            },
        )
        row["flow"] = flow_key
        self.vault.put(key, row)
        return (
            m["authorization_endpoint"]
            + "?"
            + urlencode(
                {
                    "response_type": "code",
                    "client_id": registration["client_id"],
                    "redirect_uri": callback,
                    "scope": "internal",
                    "state": state,
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                    "resource": RESOURCE,
                }
            )
        )

    def complete(self, cookie, state, code, issuer=None, error=None):
        session = self.session(cookie)
        if not session or not state or len(state) > 100:
            raise ProviderError("OAUTH_SESSION_LOST")
        flow_key = "oauth-flow:" + digest(state)
        flow = self.vault.get(flow_key)
        if (
            not flow
            or flow["browser"] != session[0]
            or flow["device"] != session[1]["device"]
            or session[1].get("flow") != flow_key
        ):
            raise ProviderError("OAUTH_STATE_INVALID")
        flow = self.vault.consume(flow_key)
        if not flow or flow["expires"] <= self.clock():
            raise ProviderError("OAUTH_EXPIRED")
        if (flow["issuer_required"] and issuer != RESOURCE) or (
            issuer is not None and issuer != RESOURCE
        ):
            raise ProviderError("OAUTH_ISSUER_INVALID")
        if error:
            raise ProviderError("AUTH_CANCELED")
        if not code or len(code) > 4096:
            raise ProviderError("OAUTH_CODE_MISSING")
        with self.client_factory() as client:
            m = metadata(client)
            response = client.post(
                m["token_endpoint"],
                data={
                    "grant_type": "authorization_code",
                    "client_id": flow["client_id"],
                    "code": code,
                    "redirect_uri": flow["callback"],
                    "code_verifier": flow["verifier"],
                    "resource": RESOURCE,
                },
            )
            if response.status_code != 200:
                raise ProviderError("TOKEN_EXCHANGE_FAILED")
            token = response.json()
        if (
            not isinstance(token.get("access_token"), str)
            or not token["access_token"]
            or token.get("token_type", "").lower() != "bearer"
            or (token.get("scope") is not None and token["scope"] != "internal")
        ):
            raise ProviderError("TOKEN_EXCHANGE_FAILED")
        expires = token.get("expires_in")
        if expires is not None:
            expires = float(expires)
            if not math.isfinite(expires) or expires <= 0:
                raise ProviderError("TOKEN_EXCHANGE_FAILED")
        token.update(
            client_id=flow["client_id"],
            expires_at=None if expires is None else self.clock() + expires,
        )
        # Clear the previous account's cached financial data before replacing auth.
        self.clear_broker_data()
        self.vault.put("oauth", token)

    def clear_broker_data(self):
        self.vault.delete_prefixes(
            ("snapshot:", "history:", "inspection:", "oauth-flow:")
        )
        for key in ("oauth", "tool_schemas", "accounts:robinhood"):
            self.vault.delete(key)

    def status(self, cookie, device):
        session = self.session(cookie, device)
        token = self.vault.get("oauth")
        mapping = self.vault.get("mapping", {})
        state = "AUTH_REQUIRED"
        if token:
            expired = (
                token.get("expires_at") is not None
                and token["expires_at"] <= self.clock()
                and not token.get("refresh_token")
            )
            state = (
                "AUTH_EXPIRED"
                if expired
                else (
                    "CONNECTED"
                    if mapping.get("reviewed") is True
                    else "SCHEMA_UNVERIFIED"
                )
            )
        return {
            "state": state,
            "browser_authorized": session is not None,
            "csrf": session[1]["csrf"] if session else None,
            "https_configured": bool(self.backend_url),
        }
