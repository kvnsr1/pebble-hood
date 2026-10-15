#!/usr/bin/env python3
"""Local HTTPS browser check. All Robinhood responses are synthetic.

Optional dependency: uv pip install --python .tools/venv/bin/python playwright==1.58.0
Uses installed Chromium; no brokerage or hosting credentials are used.
"""

import ipaddress
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.parse import parse_qs, urlencode, urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def serve(directory, port):
    import httpx
    import uvicorn
    from backend.app import create_app
    from backend.mcp import META
    from backend.store import from_env

    os.umask(0o077)
    vault = from_env()
    (directory / "codes.json").write_text(
        json.dumps([vault.pair_code(), vault.pair_code()])
    )
    metadata = json.loads((ROOT / "docs/robinhood-probe.json").read_text())[
        "authorization_metadata"
    ]

    def respond(request):
        if str(request.url) == META:
            return httpx.Response(200, json=metadata)
        if str(request.url) == metadata["registration_endpoint"]:
            body = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "client_id": "synthetic-browser-check",
                    "redirect_uris": body["redirect_uris"],
                    "token_endpoint_auth_method": "none",
                },
            )
        if str(request.url) == metadata["token_endpoint"]:
            return httpx.Response(
                200,
                json={
                    "access_token": "synthetic-access",
                    "refresh_token": "synthetic-refresh",
                    "token_type": "Bearer",
                    "scope": "internal",
                    "expires_in": 3600,
                },
            )
        raise AssertionError("Unexpected provider request")

    app = create_app(
        vault,
        backend_url=f"https://127.0.0.1:{port}",
        oauth_client_factory=lambda: httpx.Client(
            transport=httpx.MockTransport(respond)
        ),
    )
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=port,
        workers=1,
        access_log=False,
        log_level="error",
        ssl_certfile=str(directory / "cert.pem"),
        ssl_keyfile=str(directory / "key.pem"),
    )


def check():
    from datetime import datetime, timedelta, timezone
    import httpx
    from cryptography import x509
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    from playwright.sync_api import sync_playwright

    os.umask(0o077)
    (ROOT / ".tools/tmp").mkdir(parents=True, exist_ok=True)
    screenshots = ROOT / "docs/screenshots"
    with tempfile.TemporaryDirectory(
        prefix="settings-check-", dir=ROOT / ".tools/tmp"
    ) as temp:
        directory = Path(temp)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = x509.Name(
            [x509.NameAttribute(NameOID.COMMON_NAME, "localhost test only")]
        )
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(timezone.utc) - timedelta(minutes=1))
            .not_valid_after(datetime.now(timezone.utc) + timedelta(hours=1))
            .add_extension(
                x509.SubjectAlternativeName(
                    [x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
                ),
                critical=False,
            )
            .sign(key, hashes.SHA256())
        )
        (directory / "cert.pem").write_bytes(
            cert.public_bytes(serialization.Encoding.PEM)
        )
        (directory / "key.pem").write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        base = f"https://127.0.0.1:{port}"
        env = dict(
            os.environ,
            HOOD_VAULT_KEY=Fernet.generate_key().decode(),
            HOOD_DATA_DIR=str(directory / "vault"),
        )
        process = subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--serve",
                str(directory),
                str(port),
            ],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            # Self-signed TLS is accepted only for this loopback test server.
            with httpx.Client(verify=False, trust_env=False, timeout=0.3) as client:
                for _ in range(100):
                    try:
                        if client.get(base + "/health").status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.1)
                else:
                    raise RuntimeError("Local settings test server did not start")
            codes = json.loads((directory / "codes.json").read_text())
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    executable_path="/usr/bin/chromium", args=["--no-sandbox"]
                )
                for canceled in (False, True):
                    context = browser.new_context(
                        viewport={"width": 390, "height": 844},
                        is_mobile=True,
                        device_scale_factor=1,
                        ignore_https_errors=True,
                    )

                    def route_request(route):
                        url = route.request.url
                        if url.startswith("https://robinhood.com/oauth?"):
                            query = parse_qs(urlsplit(url).query)
                            params = {
                                "state": query["state"][0],
                                "iss": "https://agent.robinhood.com/mcp/trading",
                            }
                            params.update(
                                {"error": "access_denied"}
                                if canceled
                                else {"code": "synthetic-code"}
                            )
                            target = query["redirect_uri"][0] + "?" + urlencode(params)
                            route.fulfill(
                                content_type="text/html",
                                body='<p>Simulated authorization — local test only</p><a id="return" href="'
                                + target.replace("&", "&amp;")
                                + '">Return to settings</a>',
                            )
                        elif url.startswith(base + "/"):
                            route.continue_()
                        else:
                            route.abort()

                    context.route("**/*", route_request)
                    page = context.new_page()
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    initial = {
                        "nonce": "test-pebble-return",
                        "source": "demo",
                        "hide": True,
                    }
                    from urllib.parse import quote

                    page.goto(base + "/configure#" + quote(json.dumps(initial)))
                    if not canceled:
                        page.screenshot(
                            path=str(screenshots / "settings-setup.png"), full_page=True
                        )
                    page.locator("#code").fill(codes[int(canceled)])
                    page.locator("#pair").click()
                    page.wait_for_function(
                        "() => !document.getElementById('connect').disabled"
                    )
                    assert not page.locator("#save").is_disabled()
                    if not canceled:
                        page.screenshot(
                            path=str(screenshots / "settings-connect.png"),
                            full_page=True,
                        )
                    page.locator("#connect").click()
                    page.locator("#return").click()
                    if canceled:
                        page.wait_for_function(
                            "() => document.getElementById('login-result').textContent.includes('canceled')"
                        )
                        page.screenshot(
                            path=str(screenshots / "settings-canceled.png"),
                            full_page=True,
                        )
                    else:
                        page.wait_for_function(
                            "() => document.getElementById('connection-status').textContent.includes('one-time verification')"
                        )
                        assert (
                            page.evaluate(
                                "() => sessionStorage.getItem('hood-config-return')"
                            )
                            is None
                        )
                        page.locator("#source").select_option("robinhood")
                        page.wait_for_function(
                            "() => document.getElementById('status').textContent.includes('one-time verification')"
                        )
                        assert page.locator("#save").is_disabled()
                        assert page.evaluate(
                            "() => document.documentElement.scrollWidth <= window.innerWidth"
                        )
                        page.screenshot(
                            path=str(screenshots / "settings-verification.png"),
                            full_page=True,
                        )
                    assert errors == [], errors
                    context.close()
                browser.close()
            print(
                "Local HTTPS browser checks passed: setup, PKCE round trip, return context, live gate, cancellation, 390px layout. All provider responses synthetic."
            )
        finally:
            process.terminate()
            process.wait(timeout=10)


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--serve":
        serve(Path(sys.argv[2]), int(sys.argv[3]))
    else:
        check()
