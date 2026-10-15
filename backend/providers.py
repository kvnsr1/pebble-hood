"""Provider interface. Robinhood deliberately fails closed until fields are verified."""

import time
import httpx
from .finance import holding, sort_holdings


class ProviderError(Exception):
    def __init__(self, code):
        self.code = code


class DemoProvider:
    name = "demo"

    def accounts(self):
        return [
            {"id": "demo-main", "name": "Demo brokerage"},
            {"id": "demo-empty", "name": "Demo empty"},
        ]

    def snapshot(self, account, now=None):
        now = int(time.time()) if now is None else now
        if account not in [a["id"] for a in self.accounts()]:
            raise ProviderError("ACCOUNT_NOT_FOUND")
        empty = account == "demo-empty"
        rows = (
            []
            if empty
            else [
                holding(
                    "VTI",
                    "Vanguard Total Stock Market ETF",
                    "32.125",
                    "280.40",
                    "231.25",
                    "278.75",
                    "etf",
                ),
                holding("AAPL", "Apple Inc.", "12.375", "232.15", "184.20", "234.10"),
                holding(
                    "MSFT", "Microsoft Corporation", "4.5", "428.50", "398.10", "423.75"
                ),
                holding(
                    "BRK.B",
                    "Berkshire Hathaway Inc. Class B",
                    "2.125",
                    "465.10",
                    None,
                    "462.50",
                ),
                holding(
                    "NVDA", "NVIDIA Corporation", "5.75", "138.20", "92.30", "137.00"
                ),
                holding(
                    "SCHD",
                    "Schwab US Dividend Equity ETF",
                    "18.125",
                    "28.50",
                    "26.10",
                    "28.60",
                    "etf",
                ),
                holding(
                    "LONGTICKER.X",
                    "Long company name rendering example",
                    "0.000125",
                    "153.50",
                    "160.00",
                    None,
                ),
                holding("PRIVATE", "Unquoted equity example", "2", None, None, None),
            ]
        )
        return {
            "version": 1,
            "provider": "demo",
            "account": self.accounts()[1 if empty else 0],
            "as_of": now,
            "currency": "USD",
            "state": "OK",
            "stale": False,
            "total": "0.00" if empty else "18432.17",
            "total_source": "synthetic_account_total",
            "today": None
            if empty
            else {"amount": "85.16", "percent": "0.46", "session": "Synthetic session"},
            "holdings": sort_holdings(rows),
            "unsupported": [] if empty else [{"kind": "option", "count": 1}],
            "history": {
                "kind": "synthetic",
                "label": "DEMO value samples",
                "points": []
                if empty
                else [
                    {"at": now - (11 - i) * 300, "value": v}
                    for i, v in enumerate(
                        [
                            "18310.00",
                            "18355.00",
                            "18340.00",
                            "18362.00",
                            "18315.00",
                            "18388.00",
                            "18401.00",
                            "18392.00",
                            "18422.00",
                            "18405.00",
                            "18419.00",
                            "18432.17",
                        ]
                    )
                ],
            },
            "note": "Synthetic data. Total includes cash and an unsupported option.",
        }


class RobinhoodProvider:
    name = "robinhood"

    def __init__(self, vault):
        self.vault = vault

    def reader(self):
        if not self.vault.get("oauth"):
            raise ProviderError("AUTH_REQUIRED")
        from .adapter import MappedReader

        return MappedReader(self.vault)

    def accounts(self):
        reader = None
        try:
            reader = self.reader()
            return reader.accounts()
        except (ValueError, KeyError, TypeError, httpx.HTTPError):
            raise ProviderError("PROVIDER_FAILURE") from None
        finally:
            if reader is not None:
                reader.close()

    def snapshot(self, account, now=None):
        reader = None
        try:
            reader = self.reader()
            return reader.snapshot(account, int(time.time()) if now is None else now)
        except (ValueError, KeyError, TypeError, httpx.HTTPError):
            raise ProviderError("PROVIDER_FAILURE") from None
        finally:
            if reader is not None:
                reader.close()
