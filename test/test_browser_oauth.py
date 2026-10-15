"""Offline browser-flow tests. Synthetic OAuth tokens, no brokerage login."""

import base64
import hashlib
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.mcp import META, RESOURCE
from backend.oauth import origin
from backend.providers import ProviderError
from backend.store import Vault, digest, from_env

BASE = "https://hood.example.com"
CALLBACK = BASE + "/oauth/robinhood/callback"
METADATA = json.loads(Path("docs/robinhood-probe.json").read_text())[
    "authorization_metadata"
]


@pytest.fixture
def flow(tmp_path):
    vault = Vault(tmp_path, Fernet.generate_key())
    clock = [1000]
    requests = []
    token_status = [200]
    response_token = [
        {
            "access_token": "synthetic-access-marker",
            "refresh_token": "synthetic-refresh",
            "token_type": "Bearer",
            "scope": "internal",
            "expires_in": 3600,
        }
    ]

    def respond(request):
        requests.append(request)
        if str(request.url) == META:
            return httpx.Response(200, json=METADATA)
        if str(request.url) == METADATA["registration_endpoint"]:
            body = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "client_id": "synthetic-client",
                    "redirect_uris": body["redirect_uris"],
                    "token_endpoint_auth_method": "none",
                },
            )
        if str(request.url) == METADATA["token_endpoint"]:
            return httpx.Response(token_status[0], json=response_token[0])
        raise AssertionError("Unexpected network request")

    app = create_app(
        vault,
        lambda: clock[0],
        BASE,
        lambda: httpx.Client(transport=httpx.MockTransport(respond)),
    )
    client = TestClient(app, base_url=BASE)
    pair = client.post("/v1/pair", json={"code": vault.pair_code()})
    token = pair.json()["token"]
    client.headers["Authorization"] = "Bearer " + token
    csrf = client.get("/v1/connection").json()["csrf"]
    return (
        vault,
        clock,
        client,
        token,
        csrf,
        requests,
        token_status,
        response_token,
        pair,
    )


def start(flow):
    client, csrf = flow[2], flow[4]
    response = client.post("/v1/connection/start", json={"csrf": csrf})
    assert response.status_code == 200
    return parse_qs(urlsplit(response.json()["url"]).query)


def finish(flow, query, **overrides):
    params = {"state": query["state"][0], "code": "synthetic-code", "iss": RESOURCE}
    params.update(overrides)
    return flow[2].get(
        "/oauth/robinhood/callback", params=params, follow_redirects=False
    )


def test_read_bearer_cannot_start_or_disconnect_broker(flow):
    _, _, client, token, csrf, requests, _, _, pair = flow
    cookie = pair.headers["set-cookie"]
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=lax" in cookie
    assert "Path=/" in cookie and "Domain=" not in cookie
    client.cookies.clear()
    assert client.get("/v1/accounts").status_code == 200
    assert client.get("/v1/connection").json()["csrf"] is None
    for path in ("start", "disconnect"):
        assert (
            client.post("/v1/connection/" + path, json={"csrf": csrf}).status_code
            == 403
        )
    assert requests == []


def test_csrf_and_browser_device_binding(flow):
    vault, _, client, _, csrf, requests, *_ = flow
    assert (
        client.post("/v1/connection/start", json={"csrf": "x" * 43}).status_code == 403
    )
    client.headers["Authorization"] = "Bearer " + vault.exchange(vault.pair_code())
    assert client.post("/v1/connection/start", json={"csrf": csrf}).status_code == 403
    assert requests == []


def test_success_pkce_encrypted_tokens_cache_reset_and_live_gate(flow):
    vault, _, client, _, _, requests, *_ = flow
    vault.put("accounts:robinhood", {"old": "account"})
    vault.put("snapshot:old", {"old": "balance"})
    vault.put("history:snapshot:old", ["old"])
    vault.put("inspection:get_accounts", {"old": "response"})
    query = start(flow)
    assert query["redirect_uri"] == [CALLBACK]
    assert query["scope"] == ["internal"] and query["code_challenge_method"] == ["S256"]
    assert query["resource"] == [RESOURCE]
    result = finish(flow, query)
    assert result.status_code == 303
    assert result.headers["location"] == "/configure#robinhood=CONNECTED"
    request = next(r for r in requests if str(r.url) == METADATA["token_endpoint"])
    sent = parse_qs(request.content.decode())
    challenge = (
        base64.urlsafe_b64encode(
            hashlib.sha256(sent["code_verifier"][0].encode()).digest()
        )
        .rstrip(b"=")
        .decode()
    )
    assert challenge == query["code_challenge"][0]
    assert sent["redirect_uri"] == [CALLBACK]
    assert vault.get("oauth")["expires_at"] == 4600
    encrypted = vault.db.execute(
        "SELECT data FROM records WHERE id='oauth'"
    ).fetchone()[0]
    assert b"synthetic-access-marker" not in encrypted
    for key in (
        "accounts:robinhood",
        "snapshot:old",
        "history:snapshot:old",
        "inspection:get_accounts",
    ):
        assert vault.get(key) is None
    assert client.get("/v1/connection").json()["state"] == "SCHEMA_UNVERIFIED"
    assert (
        client.get("/v1/accounts?source=robinhood").json()["state"]
        == "SCHEMA_UNVERIFIED"
    )
    assert "synthetic-access-marker" not in result.text
    assert "code=" not in result.headers["location"]
    assert finish(flow, query).headers["location"].endswith("OAUTH_STATE_INVALID")


@pytest.mark.parametrize(
    "case,expected",
    [
        ("state", "OAUTH_STATE_INVALID"),
        ("issuer", "OAUTH_ISSUER_INVALID"),
        ("no-issuer", "OAUTH_ISSUER_INVALID"),
        ("cancel", "AUTH_CANCELED"),
        ("expired", "OAUTH_EXPIRED"),
        ("cookie", "OAUTH_SESSION_LOST"),
        ("revoked", "OAUTH_SESSION_LOST"),
        ("duplicate", "OAUTH_STATE_INVALID"),
    ],
)
def test_callback_rejects_invalid_or_missing_context(flow, case, expected):
    vault, clock, client, token, _, requests, *_ = flow
    query = start(flow)
    overrides = {}
    if case == "state":
        overrides["state"] = "wrong"
    if case == "issuer":
        overrides["iss"] = "https://attacker.example"
    if case == "no-issuer":
        overrides["iss"] = None
    if case == "cancel":
        overrides["error"] = "access_denied"
    if case == "expired":
        clock[0] += 301
    if case == "cookie":
        client.cookies.clear()
    if case == "revoked":
        vault.delete("device:" + digest(token))
    if case == "duplicate":
        overrides["state"] = [query["state"][0], "wrong"]
    if case == "no-issuer":
        response = client.get(
            "/oauth/robinhood/callback",
            params={"state": query["state"][0], "code": "synthetic"},
            follow_redirects=False,
        )
    else:
        response = finish(flow, query, **overrides)
    assert response.headers["location"].endswith(expected)
    assert vault.get("oauth") is None
    assert not any(str(r.url) == METADATA["token_endpoint"] for r in requests)


@pytest.mark.parametrize(
    "token_status,token_body",
    [
        (400, {"access_token": "must-not-be-shown"}),
        (200, {"access_token": "must-not-be-shown", "token_type": "bad"}),
        (
            200,
            {
                "access_token": "must-not-be-shown",
                "token_type": "Bearer",
                "expires_in": "NaN",
            },
        ),
    ],
)
def test_token_failures_redacted_and_old_connection_preserved(
    flow, token_status, token_body
):
    vault, _, _, _, _, _, status, body, _ = flow
    vault.put("oauth", {"access_token": "synthetic-old"})
    vault.put("snapshot:old", {"value": "123"})
    query = start(flow)
    status[0], body[0] = token_status, token_body
    result = finish(flow, query)
    assert result.headers["location"].endswith("TOKEN_EXCHANGE_FAILED")
    assert "must-not-be-shown" not in result.text
    assert vault.get("oauth")["access_token"] == "synthetic-old"
    assert vault.get("snapshot:old") == {"value": "123"}


def test_start_rate_limit_browser_expiry_and_replaced_flow(flow):
    _, clock, client, _, csrf, *_ = flow
    first = start(flow)
    assert (
        client.post("/v1/connection/start", json={"csrf": csrf}).json()["state"]
        == "RATE_LIMITED"
    )
    clock[0] += 61
    second = start(flow)
    assert finish(flow, first).headers["location"].endswith("OAUTH_STATE_INVALID")
    assert finish(flow, second).headers["location"].endswith("CONNECTED")
    clock[0] += 1800
    assert client.post("/v1/connection/start", json={"csrf": csrf}).status_code == 403


def test_broker_disconnect_clears_all_phone_and_broker_data(flow):
    vault, _, client, token, csrf, *_ = flow
    vault.put("oauth", {"access_token": "synthetic"})
    vault.put("snapshot:old", {"value": "123"})
    extra = vault.exchange(vault.pair_code())
    response = client.post("/v1/connection/disconnect", json={"csrf": csrf})
    assert response.json() == {"disconnected": True, "remote_revocation": False}
    assert vault.get("oauth") is None and vault.get("snapshot:old") is None
    assert vault.get("device:" + digest(token)) is None
    assert vault.get("device:" + digest(extra)) is None
    assert client.get("/v1/accounts").status_code == 401


def test_random_deployment_secret_persists_and_invalid_origins_fail(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("HOOD_VAULT_KEY", raising=False)
    monkeypatch.setenv(
        "HOOD_VAULT_SECRET", "deterministic-synthetic-high-entropy-secret" * 2
    )
    monkeypatch.setenv("HOOD_DATA_DIR", str(tmp_path))
    from_env().put("marker", {"ok": True})
    assert from_env().get("marker") == {"ok": True}
    for bad in (
        "http://hood.example.com",
        "https://user:password@hood.example.com",
        "https://hood.example.com/path",
        "https://hood.example.com/?query=1",
    ):
        with pytest.raises(ProviderError):
            origin(bad)
