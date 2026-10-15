"""Private operator commands. OAuth callback stays on loopback, never on the watch."""

import argparse
import base64
import hashlib
import json
import os
import secrets
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlencode, urlparse, parse_qs
import httpx
from .store import from_env
from .mcp import metadata, MCP, RESOURCE
from .providers import ProviderError

CALLBACK = "http://127.0.0.1:8765/callback"


def connect(vault):
    verifier = secrets.token_urlsafe(48)
    state = secrets.token_urlsafe(32)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    with httpx.Client(timeout=20, follow_redirects=False) as client:
        m = metadata(client)
        r = client.post(
            m["registration_endpoint"],
            json={
                "client_name": "Pebble Hood personal viewer",
                "redirect_uris": [CALLBACK],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "none",
            },
        )
        if r.status_code not in (200, 201):
            raise ProviderError("REGISTRATION_FAILED")
        client_id = r.json()["client_id"]
        scope = " ".join(m.get("scopes_supported", []))
        if scope != "internal":
            raise ProviderError("OAUTH_METADATA_CHANGED")
        outcome = {}

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                p = urlparse(self.path)
                q = parse_qs(p.query)
                valid = p.path == "/callback" and secrets.compare_digest(
                    q.get("state", [""])[0], state
                )
                if not valid:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"Invalid callback.")
                    return
                if q.get("iss", [RESOURCE])[0] != RESOURCE:
                    self.send_response(400)
                    self.end_headers()
                    return
                outcome.update(
                    code=q.get("code", [None])[0], error=q.get("error", [None])[0]
                )
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(
                    b"Return to the terminal. You may close this browser tab."
                )

        server = HTTPServer(("127.0.0.1", 8765), Handler)
        server.timeout = 1
        url = (
            m["authorization_endpoint"]
            + "?"
            + urlencode(
                {
                    "response_type": "code",
                    "client_id": client_id,
                    "redirect_uri": CALLBACK,
                    "scope": scope,
                    "state": state,
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                    "resource": RESOURCE,
                }
            )
        )
        print(
            "Robinhood grants the broad internal scope. This app only invokes allowlisted reads."
        )
        print(
            "Onboarding may require opening an MCP account. Review the browser consent yourself."
        )
        print("Open this URL locally (not a credential; expires in 5 minutes):\n" + url)
        webbrowser.open(url)
        deadline = time.time() + 300
        try:
            while not outcome and time.time() < deadline:
                server.handle_request()
        finally:
            server.server_close()
        if not outcome.get("code"):
            raise ProviderError("AUTH_CANCELED")
        r = client.post(
            m["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "code": outcome["code"],
                "redirect_uri": CALLBACK,
                "code_verifier": verifier,
                "resource": RESOURCE,
            },
        )
        if r.status_code != 200:
            raise ProviderError("TOKEN_EXCHANGE_FAILED")
        t = r.json()
        if not isinstance(t.get("access_token"), str):
            raise ProviderError("TOKEN_EXCHANGE_FAILED")
        t.update(
            client_id=client_id,
            expires_at=time.time() + float(t["expires_in"])
            if t.get("expires_in") is not None
            else None,
        )
        vault.put("oauth", t)
        print(
            "Tokens stored encrypted. Run inspect next. Live display remains gated on schema verification."
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=[
            "pair",
            "connect",
            "inspect",
            "disconnect",
            "read",
            "install-mapping",
            "export-inspection",
        ],
    )
    parser.add_argument(
        "--tool",
        choices=sorted(__import__("backend.mcp", fromlist=["READ_TOOLS"]).READ_TOOLS),
    )
    parser.add_argument(
        "--arguments",
        default="{}",
        help="JSON arguments matching the discovered schema",
    )
    parser.add_argument(
        "--file", help="Local mapping input or private inspection output"
    )
    args = parser.parse_args()
    vault = from_env()
    try:
        if args.command == "pair":
            print(
                "One-use phone pairing code (valid 10 minutes):\n" + vault.pair_code()
            )
        elif args.command == "connect":
            connect(vault)
        elif args.command == "export-inspection":
            if not args.file or not args.tool:
                parser.error("--file and --tool required")
            value = vault.get("inspection:" + args.tool)
            if value is None:
                raise ProviderError("NO_INSPECTION")
            fd = os.open(args.file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as f:
                json.dump(value, f, indent=2)
            print(
                "Sensitive response exported to private file. Do not commit or share it."
            )
        elif args.command == "install-mapping":
            if not args.file:
                parser.error("--file required")
            from .adapter import fingerprint

            with open(args.file) as f:
                mapping = json.load(f)
            if mapping.get("reviewed") is not True:
                raise ProviderError("SCHEMA_UNVERIFIED")
            schemas = MCP(vault).discover()
            if mapping.get("schema_sha256") != fingerprint(schemas):
                raise ProviderError("PROVIDER_SHAPE_CHANGED")
            vault.put("mapping", mapping)
            print(
                "Reviewed mapping installed. Test accounts and portfolio on the phone before relying on it."
            )
        elif args.command in ("inspect", "read"):
            m = MCP(vault)
            schemas = m.discover()
            vault.put("tool_schemas", schemas)
            if args.command == "read":
                if not args.tool:
                    parser.error("--tool required")
                vault.put(
                    "inspection:" + args.tool,
                    m.call(args.tool, json.loads(args.arguments)),
                )
                print(
                    "Response saved encrypted under inspection:"
                    + args.tool
                    + ". No account data printed."
                )
            else:
                path = os.path.join(
                    os.environ.get("HOOD_DATA_DIR", ".private"), "tool-schemas.json"
                )
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(fd, "w") as f:
                    json.dump(schemas, f, indent=2)
                from .adapter import fingerprint

                print(
                    "Read-tool schemas saved locally. Schema SHA256: "
                    + fingerprint(schemas)
                )
                print(
                    "Review actual responses and install an explicit field mapping; see docs/robinhood-access.md."
                )
        else:
            vault.clear()
            print(
                "Local OAuth tokens, devices, caches and snapshots removed. Also revoke Pebble Hood in Robinhood connected-agent settings. Metadata advertises no revocation endpoint; remote revocation was not performed."
            )
    except ProviderError as e:
        print("Connection status: " + e.code)
        raise SystemExit(1)
    except (httpx.HTTPError, ValueError, KeyError):
        print("Connection failed; no credentials or response bodies logged.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
