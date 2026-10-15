#!/usr/bin/env python3
"""Unauthenticated protocol probe. Never prints response headers or credentials."""

import json
import argparse
from urllib.parse import urlsplit
import urllib.request
import urllib.error

RESOURCE = "https://agent.robinhood.com/mcp/trading"


def request(url, payload=None):
    body = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        },
    )
    try:
        response = urllib.request.urlopen(req, timeout=20)
    except urllib.error.HTTPError as error:
        response = error
    raw = response.read(262144)
    try:
        data = json.loads(raw)
    except ValueError:
        data = None
    return response.status, response.headers, data


def probe():
    status, headers, _ = request(
        RESOURCE,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "pebble-hood", "version": "0.1.0"},
            },
        },
    )
    resource_status, _, resource = request(
        "https://agent.robinhood.com/.well-known/oauth-protected-resource/mcp/trading"
    )
    server_status, _, server = request(
        "https://agent.robinhood.com/.well-known/oauth-authorization-server/mcp/trading"
    )
    return {
        "initialize_status": status,
        "challenge_present": bool(headers.get("WWW-Authenticate")),
        "protected_resource_status": resource_status,
        "protected_resource": resource,
        "authorization_metadata_status": server_status,
        "authorization_metadata": server,
        "authenticated": False,
        "tools_and_account_fields_verified": False,
    }


def probe_https_callback(callback):
    p = urlsplit(callback)
    if (
        p.scheme != "https"
        or not p.hostname
        or p.username
        or p.password
        or p.query
        or p.fragment
    ):
        raise ValueError(
            "Provide an HTTPS callback URL without credentials, query or fragment"
        )
    status, _, data = request(
        "https://agent.robinhood.com/oauth/trading/register",
        {
            "client_name": "Pebble Hood HTTPS callback compatibility check",
            "redirect_uris": [callback],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        },
    )
    data = data or {}
    return {
        "registration_status": status,
        "callback": callback,
        "registered_redirect_uris": data.get("redirect_uris"),
        "public_client": data.get("token_endpoint_auth_method") == "none",
        "account_authenticated": False,
        "callback_received": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--https-callback",
        help="Also test registration with this HTTPS redirect (no login)",
    )
    args = parser.parse_args()
    result = probe()
    if args.https_callback:
        result["https_callback_registration"] = probe_https_callback(
            args.https_callback
        )
    print(json.dumps(result, indent=2))
