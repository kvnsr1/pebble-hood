#!/usr/bin/env python3
"""Real loopback HTTP smoke test with an ephemeral vault and no broker account."""

import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
import httpx
from cryptography.fernet import Fernet

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
from backend.store import Vault  # noqa: E402 (project root added above)

with tempfile.TemporaryDirectory(dir=root / ".tools", prefix="smoke-") as directory:
    key = Fernet.generate_key().decode()
    vault = Vault(directory, key)
    code = vault.pair_code()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = dict(os.environ, HOOD_DATA_DIR=directory, HOOD_VAULT_KEY=key)
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.app:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--no-access-log",
        ],
        cwd=root,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=2) as client:
            for _ in range(50):
                try:
                    if client.get("/health").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.1)
            else:
                raise RuntimeError("Backend did not become ready")
            assert client.get("/v1/portfolio").status_code == 401
            assert client.get("/configure").status_code == 200
            assert client.get("/config.js").status_code == 200
            token = client.post("/v1/pair", json={"code": code}).json()["token"]
            headers = {"Authorization": "Bearer " + token}
            accounts = client.get("/v1/accounts", headers=headers).json()["accounts"]
            page = client.get("/v1/portfolio", headers=headers).json()
            assert (
                len(accounts) == 2
                and len(page["holdings"]) == 6
                and page["provider"] == "demo"
            )
            assert client.post("/v1/disconnect", headers=headers).status_code == 200
            assert client.get("/v1/portfolio", headers=headers).status_code == 401
            print(
                "HTTP smoke passed: health, static settings, pairing, authenticated demo, revocation."
            )
    finally:
        proc.terminate()
        proc.wait(timeout=5)
        vault.db.close()
