"""Explicit JSON-pointer mapping for authenticated, locally reviewed MCP schemas.

No Robinhood response fields are assumed. A mapping is installed by the operator
only after inspecting actual schemas and read responses. Unknown shapes fail closed.
"""

import hashlib
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from .finance import holding, number, money, sort_holdings
from .mcp import MCP
from .providers import ProviderError

MISSING = object()


def pointer(value, path, optional=False):
    if not isinstance(path, str):
        if optional:
            return None
        raise ProviderError("SCHEMA_UNVERIFIED")
    if path == "":
        return value
    if not path.startswith("/"):
        raise ProviderError("MAPPING_INVALID")
    try:
        for token in path[1:].split("/"):
            key = token.replace("~1", "/").replace("~0", "~")
            value = value[int(key)] if isinstance(value, list) else value[key]
        return value
    except (KeyError, IndexError, TypeError, ValueError):
        if optional:
            return None
        raise ProviderError("PROVIDER_SHAPE_CHANGED") from None


def fingerprint(schemas):
    return hashlib.sha256(
        json.dumps(schemas, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def timestamp(value):
    if type(value) is int:
        return value
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                raise ValueError()
            return int(dt.timestamp())
        except ValueError:
            pass
    raise ProviderError("PROVIDER_SHAPE_CHANGED")


def substitute(obj, account=None, symbols=None, cursor=None):
    if isinstance(obj, dict):
        return {k: substitute(v, account, symbols, cursor) for k, v in obj.items()}
    if isinstance(obj, list):
        return [substitute(v, account, symbols, cursor) for v in obj]
    return (
        {"$account": account, "$symbols": symbols, "$cursor": cursor}.get(obj, obj)
        if isinstance(obj, str)
        else obj
    )


def payload(result):
    if "structuredContent" in result:
        return result["structuredContent"]
    content = result.get("content", [])
    if len(content) == 1 and content[0].get("type") == "text":
        try:
            return json.loads(content[0]["text"])
        except ValueError:
            pass
    raise ProviderError("PROVIDER_SHAPE_CHANGED")


def field(row, fields, name, optional=False):
    return pointer(row, fields.get(name), optional)


def text(value, max_length):
    if not isinstance(value, str) or not value or len(value) > max_length:
        raise ProviderError("PROVIDER_SHAPE_CHANGED")
    return value


class MappedReader:
    def __init__(self, vault):
        self.mapping = vault.get("mapping")
        if not self.mapping or self.mapping.get("reviewed") is not True:
            raise ProviderError("SCHEMA_UNVERIFIED")
        self.mcp = MCP(vault)
        try:
            schemas = self.mcp.discover()
            if self.mapping.get("schema_sha256") != fingerprint(schemas):
                raise ProviderError("PROVIDER_SHAPE_CHANGED")
        except Exception:
            self.mcp.close()
            raise

    def close(self):
        self.mcp.close()

    def read(self, operation, account=None, symbols=None):
        spec = self.mapping[operation]
        expected = {
            "accounts": "get_accounts",
            "portfolio": "get_portfolio",
            "positions": "get_equity_positions",
            "quotes": "get_equity_quotes",
        }
        if spec.get("tool") != expected[operation]:
            raise ProviderError("MAPPING_INVALID")
        cursor = None
        seen = set()
        items = []
        for _ in range(50):
            args = substitute(spec.get("arguments", {}), account, symbols, cursor)
            try:
                result = payload(self.mcp.call(spec["tool"], args))
            except (ValueError, KeyError, TypeError):
                raise ProviderError("PROVIDER_SHAPE_CHANGED") from None
            if operation == "portfolio":
                return pointer(result, spec.get("object", ""))
            rows = pointer(result, spec.get("items"))
            if not isinstance(rows, list):
                raise ProviderError("PROVIDER_SHAPE_CHANGED")
            items.extend(rows)
            if len(items) > 1000:
                raise ProviderError("PORTFOLIO_TOO_LARGE")
            cursor = pointer(result, spec.get("next_cursor"), True)
            if cursor in (None, ""):
                return items
            encoded = json.dumps(cursor, sort_keys=True)
            if encoded in seen or "$cursor" not in json.dumps(
                spec.get("arguments", {})
            ):
                raise ProviderError("PAGINATION_LIMIT")
            seen.add(encoded)
        raise ProviderError("PAGINATION_LIMIT")

    def accounts(self):
        f = self.mapping["accounts"]["fields"]
        return [
            {"id": text(field(r, f, "id"), 96), "name": text(field(r, f, "name"), 80)}
            for r in self.read("accounts")
        ]

    def snapshot(self, account, now):
        accounts = self.accounts()
        selected = next((a for a in accounts if a["id"] == account), None)
        if not selected:
            raise ProviderError("ACCOUNT_NOT_FOUND")
        p = self.read("portfolio", account)
        pf = self.mapping["portfolio"]["fields"]
        # Mapping must explicitly attest to full account coverage, including cash,
        # options, crypto and liabilities where applicable. Never sum equities.
        if field(p, pf, "currency") != "USD":
            raise ProviderError("CURRENCY_UNSUPPORTED")
        total = field(p, pf, "total")
        total = (
            money(number(total))
            if self.mapping.get("total_includes_all_assets") is True
            else None
        )
        as_of = timestamp(field(p, pf, "as_of"))
        if as_of > now + 60 or as_of < 0:
            raise ProviderError("PROVIDER_TIME_INVALID")
        unsupported = field(p, pf, "unsupported")
        if not isinstance(unsupported, list):
            raise ProviderError("PROVIDER_SHAPE_CHANGED")
        uf = self.mapping["portfolio"].get("unsupported_fields", {})
        unsupported = [
            {"kind": text(field(r, uf, "kind"), 40), "count": field(r, uf, "count")}
            for r in unsupported
        ]
        if any(type(r["count"]) is not int or r["count"] < 0 for r in unsupported):
            raise ProviderError("PROVIDER_SHAPE_CHANGED")
        rows = self.read("positions", account)
        f = self.mapping["positions"]["fields"]
        symbols = [text(field(r, f, "ticker"), 32) for r in rows]
        if len(set(symbols)) != len(symbols):
            raise ProviderError("DUPLICATE_POSITION")
        quotes = {}
        qf = self.mapping["quotes"]["fields"]
        for start in range(0, len(symbols), 20):
            for q in self.read("quotes", account, symbols[start : start + 20]):
                ticker = text(field(q, qf, "ticker"), 32)
                if ticker in quotes:
                    raise ProviderError("DUPLICATE_QUOTE")
                quotes[ticker] = q
        result = []
        quote_stale = False
        for row, ticker in zip(rows, symbols):
            q = quotes.get(ticker)
            price = prev = None
            if q:
                quote_time = timestamp(field(q, qf, "as_of"))
                if quote_time > now + 60 or quote_time < 0:
                    raise ProviderError("PROVIDER_TIME_INVALID")
                quote_stale = quote_stale or now - quote_time > 300
                price = field(q, qf, "price", True)
                prev = field(q, qf, "previous_close", True)
            kind = field(row, f, "asset_class")
            kind = self.mapping["positions"].get("asset_class_values", {}).get(kind)
            if kind not in ("equity", "etf"):
                raise ProviderError("UNSUPPORTED_POSITION_TYPE")
            result.append(
                holding(
                    ticker,
                    text(field(row, f, "name"), 96),
                    field(row, f, "quantity"),
                    price,
                    field(row, f, "average_cost", True),
                    prev,
                    kind,
                )
            )
        # Daily portfolio return remains unavailable unless its provider-defined
        # methodology is reviewed. Balance samples are never substituted for it.
        today = None
        if self.mapping.get("today_is_authoritative") is True:
            amount = field(p, pf, "today_amount", True)
            pct = field(p, pf, "today_percent", True)
            session = field(p, pf, "session")
            current_date = (
                datetime.fromtimestamp(now, ZoneInfo("America/New_York"))
                .date()
                .isoformat()
            )
            if amount is not None and pct is not None and session == current_date:
                today = {
                    "amount": money(number(amount)),
                    "percent": money(number(pct)),
                    "session": text(field(p, pf, "session"), 96),
                }
        return {
            "version": 1,
            "provider": "robinhood",
            "account": selected,
            "as_of": as_of,
            "currency": "USD",
            "state": "OK",
            "stale": now - as_of > 300 or quote_stale,
            "total": total,
            "total_source": "provider_account_total"
            if total is not None
            else "unavailable",
            "today": today,
            "holdings": sort_holdings(result),
            "unsupported": unsupported,
            "history": {
                "kind": "balance_snapshots",
                "label": "Observed balances",
                "points": [],
            },
            "note": ("Includes unsupported assets. " if unsupported else "")
            + "Stock day uses provider prior close. Balance samples include cash flows; not investment performance.",
        }
