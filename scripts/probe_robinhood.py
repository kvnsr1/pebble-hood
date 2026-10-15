#!/usr/bin/env python3
"""Unauthenticated protocol probe. Never prints response headers or credentials."""

import json
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


if __name__ == "__main__":
    print(json.dumps(probe(), indent=2))
