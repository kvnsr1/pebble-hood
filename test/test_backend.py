import json
import time
from decimal import Decimal
import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from backend.finance import holding, number, percent
from backend.store import Vault, digest
from backend.providers import DemoProvider, ProviderError
from backend.app import create_app
from backend.mcp import MCP, READ_TOOLS


@pytest.fixture
def vault(tmp_path):
    return Vault(tmp_path, Fernet.generate_key())


def test_fractional_decimal_exact():
    h = holding("X", "X", "0.3", "0.1", "0.2", "0.2")
    assert (
        h["value"] == "0.03"
        and h["unrealized"] == "-0.03"
        and h["unrealized_pct"] == "-50.00"
    )
    assert h["price_day"] == "-0.10"


def test_missing_cost_not_zero():
    h = holding("X", "X", "1.125", "10", None, None)
    assert (
        h["value"] == "11.25"
        and h["unrealized"] is None
        and h["average_cost"] is None
        and h["price_day_pct"] is None
    )


def test_invalid_and_zero():
    for bad in [0.1, "NaN", "Infinity", "1e100", "bad"]:
        with pytest.raises(ValueError):
            number(bad)
    assert percent(Decimal("2"), Decimal("0")) is None
    assert holding("X", "X", "0", "1", "0", "0")["unrealized_pct"] is None


def test_demo_is_deterministic_and_total_authoritative():
    p = DemoProvider()
    s = p.snapshot("demo-main", 12345)
    assert s == p.snapshot("demo-main", 12345)
    assert s["provider"] == "demo" and s["unsupported"] == [
        {"kind": "option", "count": 1}
    ]
    assert sum(Decimal(h["value"]) for h in s["holdings"] if h["value"]) != Decimal(
        s["total"]
    )
    assert s["holdings"][-1]["value"] is None
    assert p.snapshot("demo-empty", 12345)["holdings"] == []


def test_encryption_pairing_and_revocation(vault):
    vault.put("oauth", {"access_token": "sensitive-test-marker"})
    raw = vault.db.execute(
        "SELECT data FROM records WHERE id=?", ("oauth",)
    ).fetchone()[0]
    assert b"sensitive-test-marker" not in raw
    code = vault.pair_code()
    token = vault.exchange(code)
    assert token and vault.exchange(code) is None
    assert vault.get("device:" + digest(token))
    vault.clear()
    assert vault.get("oauth") is None


def test_http_pair_auth_cache_pages(vault):
    clock = [1000]
    client = TestClient(create_app(vault, lambda: clock[0]))
    assert client.get("/v1/portfolio").status_code == 401
    token = client.post("/v1/pair", json={"code": vault.pair_code()}).json()["token"]
    headers = {"Authorization": "Bearer " + token}
    first = client.get("/v1/portfolio", headers=headers).json()
    assert len(first["holdings"]) == 6 and first["pages"] == 2
    second = client.get("/v1/portfolio?page=1", headers=headers).json()
    assert len(second["holdings"]) == 2 and first["as_of"] == second["as_of"]
    clock[0] = 1030
    assert client.get("/v1/portfolio", headers=headers).json()["as_of"] == 1000
    assert client.get("/v1/portfolio?page=9999", headers=headers).status_code == 400
    assert (
        client.get("/v1/accounts?source=robinhood", headers=headers).json()["state"]
        == "AUTH_REQUIRED"
    )
    vault.put("oauth", {"access_token": "x"})
    assert (
        client.get("/v1/accounts?source=robinhood", headers=headers).json()["state"]
        == "SCHEMA_UNVERIFIED"
    )
    client.post("/v1/disconnect", headers=headers)
    assert client.get("/v1/portfolio", headers=headers).status_code == 401


def test_allowlist_deny_before_network(vault):
    m = MCP(vault)
    for tool in [
        "place_equity_order",
        "cancel_equity_order",
        "get_equity_orders",
        "review_equity_order",
    ]:
        with pytest.raises(ValueError):
            m.call(tool, {})
        with pytest.raises(ValueError):
            m.rpc("tools/call", {"name": tool})
    with pytest.raises(ValueError):
        m.rpc("resources/read")
    assert READ_TOOLS == {
        "get_accounts",
        "get_portfolio",
        "get_equity_positions",
        "get_equity_quotes",
    }


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "AUTH_EXPIRED"),
        (403, "AUTH_EXPIRED"),
        (429, "RATE_LIMITED"),
        (500, "PROVIDER_FAILURE"),
    ],
)
def test_mcp_failures_redacted(vault, status, code):
    vault.put("oauth", {"access_token": "SECRET", "expires_at": time.time() + 1000})
    client = httpx.Client(
        transport=httpx.MockTransport(lambda req: httpx.Response(status, text="SECRET"))
    )
    with pytest.raises(ProviderError) as e:
        MCP(vault, client).rpc("tools/list")
    assert e.value.code == code and "SECRET" not in str(e.value)


def test_expired_refresh_rejected(vault):
    vault.put("oauth", {"access_token": "SECRET", "expires_at": 0})
    with pytest.raises(ProviderError) as e:
        MCP(vault).access_token()
    assert e.value.code == "AUTH_EXPIRED"


def test_sse_discovery_and_validated_call(vault):
    vault.put("oauth", {"access_token": "SECRET", "expires_at": time.time() + 1000})

    def respond(req):
        d = json.loads(req.content)
        if d["method"] == "notifications/initialized":
            return httpx.Response(202)
        result = (
            {"protocolVersion": "2025-03-26"}
            if d["method"] == "initialize"
            else {
                "tools": [
                    {
                        "name": "get_accounts",
                        "inputSchema": {
                            "type": "object",
                            "additionalProperties": False,
                        },
                    },
                    {"name": "place_equity_order"},
                ]
            }
        )
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            text="data: "
            + json.dumps({"jsonrpc": "2.0", "id": d["id"], "result": result})
            + "\n\n",
        )

    m = MCP(vault, httpx.Client(transport=httpx.MockTransport(respond)))
    assert list(m.discover()) == ["get_accounts"]

    with pytest.raises(ProviderError):
        m.call("get_accounts", {"unexpected": True})


def test_stale_backend_retry_is_throttled(vault, monkeypatch):
    now = [1000]
    calls = []
    from backend.app import DemoProvider as P

    original = P.snapshot

    def snapshot(self, account, now=None):
        calls.append(now)
        if now > 1000:
            raise ProviderError("PROVIDER_FAILURE")
        return original(self, account, now)

    monkeypatch.setattr(P, "snapshot", snapshot)
    client = TestClient(create_app(vault, lambda: now[0]))
    token = vault.exchange(vault.pair_code())
    headers = {"Authorization": "Bearer " + token}
    assert client.get("/v1/portfolio", headers=headers).json()["as_of"] == 1000
    now[0] = 1400
    s = client.get("/v1/portfolio", headers=headers).json()
    assert s["stale"] and s["state"] == "PROVIDER_FAILURE" and s["as_of"] == 1000
    now[0] = 1401
    client.get("/v1/portfolio", headers=headers)
    assert calls == [1000, 1400]


def test_chart_samples_not_returns():
    from backend.finance import chart_pixels

    assert chart_pixels([]) == []
    assert chart_pixels([{"value": "3"}, {"value": "3"}]) == [50, 50]
    assert chart_pixels([{"value": "10"}, {"value": "20"}]) == [0, 100]
    p = chart_pixels([{"value": str(x)} for x in range(100)])
    assert len(p) == 24 and p[0] == 0 and p[-1] == 100


def test_mapping_pointers_no_guessed_fields():
    from backend.adapter import pointer, substitute, timestamp

    assert pointer({"a/b": {"~x": ["12.50"]}}, "/a~1b/~0x/0") == "12.50"
    assert pointer({}, "/missing", True) is None
    with pytest.raises(ProviderError):
        pointer({}, "/missing")
    assert substitute({"a": "$account", "s": "$symbols"}, "abc", ["VTI"]) == {
        "a": "abc",
        "s": ["VTI"],
    }
    with pytest.raises(ProviderError):
        timestamp("2026-01-01T12:00:00")
    assert timestamp("1970-01-01T00:00:00Z") == 0


def test_schema_hash_gate_before_network(vault):
    from backend.adapter import MappedReader

    with pytest.raises(ProviderError) as e:
        MappedReader(vault)
    assert e.value.code == "SCHEMA_UNVERIFIED"


def test_mapped_provider_with_synthetic_schema(vault, monkeypatch):
    """These invented fixture keys are deliberately NOT Robinhood field claims."""
    import backend.adapter as adapter

    schemas = {"get_accounts": {"inputSchema": {"type": "object"}}}
    mapping = json.load(open("backend/mapping.template.json"))
    mapping.update(
        reviewed=True,
        schema_sha256=adapter.fingerprint(schemas),
        total_includes_all_assets=True,
    )
    mapping["accounts"].update(items="/rows", fields={"id": "/key", "name": "/label"})
    mapping["portfolio"]["fields"] = {
        "total": "/balance",
        "as_of": "/time",
        "currency": "/currency",
        "unsupported": "/other",
    }
    mapping["portfolio"]["unsupported_fields"] = {"kind": "/asset", "count": "/n"}
    mapping["positions"].update(
        items="/rows",
        fields={
            "ticker": "/symbol",
            "name": "/label",
            "quantity": "/units",
            "average_cost": "/basis",
            "asset_class": "/class",
        },
        asset_class_values={"stock": "equity"},
    )
    mapping["quotes"].update(
        items="/rows",
        arguments={"symbols": "$symbols"},
        fields={
            "ticker": "/symbol",
            "price": "/mark",
            "previous_close": "/prior",
            "as_of": "/time",
        },
    )
    results = {
        "get_accounts": {"rows": [{"key": "abc", "label": "Fixture account"}]},
        "get_portfolio": {
            "balance": "10000.00",
            "time": 1000,
            "currency": "USD",
            "other": [{"asset": "option", "n": 1}],
        },
        "get_equity_positions": {
            "rows": [
                {
                    "symbol": "X",
                    "label": "Fixture equity",
                    "units": "0.3",
                    "basis": "90",
                    "class": "stock",
                }
            ]
        },
        "get_equity_quotes": {
            "rows": [{"symbol": "X", "mark": "100", "prior": "101", "time": 1000}]
        },
    }

    class FakeMCP:
        def close(self):
            pass

        def __init__(self, vault):
            pass

        def discover(self):
            return schemas

        def call(self, name, args):
            return {"structuredContent": results[name]}

    monkeypatch.setattr(adapter, "MCP", FakeMCP)
    vault.put("mapping", mapping)
    reader = adapter.MappedReader(vault)
    s = reader.snapshot("abc", 1000)
    assert s["total"] == "10000.00" and s["holdings"][0]["value"] == "30.00"
    assert (
        s["holdings"][0]["unrealized"] == "3.00"
        and s["holdings"][0]["price_day"] == "-1.00"
    )
    assert s["unsupported"] == [{"kind": "option", "count": 1}] and s["today"] is None
    assert s["history"]["points"] == []
    mapping["total_includes_all_assets"] = False
    vault.put("mapping", mapping)
    assert adapter.MappedReader(vault).snapshot("abc", 1000)["total"] is None
    mapping["schema_sha256"] = "changed"
    vault.put("mapping", mapping)
    with pytest.raises(ProviderError):
        adapter.MappedReader(vault)


def test_refresh_rotation_preserves_client_id(vault):
    from backend.mcp import META

    meta = json.load(open("docs/robinhood-probe.json"))["authorization_metadata"]
    vault.put(
        "oauth",
        {
            "access_token": "old",
            "refresh_token": "old-refresh",
            "client_id": "public-client",
            "expires_at": 0,
        },
    )

    def respond(req):
        if str(req.url) == META:
            return httpx.Response(200, json=meta)
        assert (
            b"grant_type=refresh_token" in req.content and b"old-refresh" in req.content
        )
        return httpx.Response(
            200,
            json={
                "access_token": "new",
                "refresh_token": "new-refresh",
                "expires_in": 3600,
            },
        )

    m = MCP(vault, httpx.Client(transport=httpx.MockTransport(respond)))
    assert m.access_token() == "new"
    assert vault.get("oauth")["refresh_token"] == "new-refresh"
    assert vault.get("oauth")["client_id"] == "public-client"


def test_unknown_token_lifetime_refreshes_once_on_401(vault):
    from backend.mcp import META

    meta = json.load(open("docs/robinhood-probe.json"))["authorization_metadata"]
    vault.put(
        "oauth",
        {
            "access_token": "old",
            "refresh_token": "refresh",
            "client_id": "public",
            "expires_at": None,
        },
    )
    calls = []

    def respond(req):
        if str(req.url) == META:
            return httpx.Response(200, json=meta)
        if str(req.url) == meta["token_endpoint"]:
            return httpx.Response(200, json={"access_token": "new", "expires_in": 3600})
        d = json.loads(req.content)
        calls.append(d["method"])
        if len(calls) == 1:
            return httpx.Response(401)
        return httpx.Response(
            200, json={"jsonrpc": "2.0", "id": d["id"], "result": {"tools": []}}
        )

    m = MCP(vault, httpx.Client(transport=httpx.MockTransport(respond)))
    assert m.rpc("tools/list") == {"tools": []}
    assert calls == ["tools/list", "tools/list"]
    assert vault.get("oauth")["access_token"] == "new"


def test_negative_zero_and_precision():
    from backend.finance import money

    assert money(Decimal("-0.0001")) == "0.00"
    h = holding(
        "X", "Fixture", "0.123456789123456789", "1000000000000000000", "100", None
    )
    assert h["value"] == "123456789123456789.00"
    assert h["unrealized"] == "123456789123456776.65"
