#!/usr/bin/env python3
"""Check a private Site's access boundary using synthetic data only."""

import argparse
import getpass
import json
import sys
from urllib.parse import urlsplit

import httpx


def probe(url, service_token=None):
    p = urlsplit(url)
    if (
        p.scheme != "https"
        or not p.hostname
        or p.username
        or p.password
        or p.path
        or p.query
        or p.fragment
    ):
        raise ValueError(
            "Use the exact Site HTTPS origin without credentials or a path"
        )
    checks = [
        ("anonymous", {}),
        (
            "phone_view_token_only",
            {"Authorization": "Bearer synthetic-pebble-view-token"},
        ),
    ]
    if service_token:
        checks.append(
            (
                "supported_service_access",
                {"OAI-Sites-Authorization": "Bearer " + service_token},
            )
        )
    result = {"url": url, "brokerage_data_used": False, "checks": []}
    with httpx.Client(timeout=25, follow_redirects=False) as client:
        for name, headers in checks:
            response = client.get(url + "/probe.json", headers=headers)
            try:
                payload = response.json()
            except ValueError:
                payload = {}
            if not isinstance(payload, dict):
                payload = {}
            result["checks"].append(
                {
                    "case": name,
                    "status": response.status_code,
                    "content_type": response.headers.get("content-type"),
                    "synthetic_marker_received": payload.get("kind")
                    == "pebble-hood-sites-probe",
                }
            )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Exact Site origin returned by Sites")
    parser.add_argument(
        "--service-token-stdin",
        action="store_true",
        help="Read an existing Site service credential from hidden input/stdin; never use an argument",
    )
    args = parser.parse_args()
    token = None
    if args.service_token_stdin:
        token = (
            getpass.getpass("Existing Site service token (hidden): ")
            if sys.stdin.isatty()
            else sys.stdin.readline().strip()
        )
    try:
        print(json.dumps(probe(args.url.rstrip("/"), token), indent=2))
    except (httpx.HTTPError, ValueError):
        raise SystemExit(
            "Site access check failed; no headers, cookies, tokens or response bodies were logged."
        ) from None
