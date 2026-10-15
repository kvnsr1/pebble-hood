"""Encrypted SQLite records. Keys live outside the DB; device tokens are hashed."""

import json
import os
import sqlite3
import threading
import hashlib
import secrets
import time
import base64
from pathlib import Path
from cryptography.fernet import Fernet


class Vault:
    def __init__(self, directory, key):
        path = Path(directory)
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.fernet = Fernet(key.encode() if isinstance(key, str) else key)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path / "vault.sqlite", check_same_thread=False)
        os.chmod(path / "vault.sqlite", 0o600)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, data BLOB NOT NULL)"
        )
        self.db.commit()

    def put(self, key, value):
        with self.lock, self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO records VALUES (?,?)",
                (key, self.fernet.encrypt(json.dumps(value).encode())),
            )

    def get(self, key, default=None):
        with self.lock:
            row = self.db.execute(
                "SELECT data FROM records WHERE id=?", (key,)
            ).fetchone()
        return default if row is None else json.loads(self.fernet.decrypt(row[0]))

    def delete(self, key):
        with self.lock, self.db:
            self.db.execute("DELETE FROM records WHERE id=?", (key,))

    def clear(self):
        with self.lock, self.db:
            self.db.execute("DELETE FROM records")

    def delete_prefixes(self, prefixes):
        with self.lock, self.db:
            for prefix in prefixes:
                self.db.execute(
                    "DELETE FROM records WHERE substr(id,1,?)=?",
                    (len(prefix), prefix),
                )

    def consume(self, key):
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                row = self.db.execute(
                    "SELECT data FROM records WHERE id=?", (key,)
                ).fetchone()
                self.db.execute("DELETE FROM records WHERE id=?", (key,))
                self.db.commit()
            except Exception:
                self.db.rollback()
                raise
        return None if row is None else json.loads(self.fernet.decrypt(row[0]))

    def pair_code(self):
        code = secrets.token_urlsafe(12)
        self.put("pair:" + digest(code), {"expires": time.time() + 600})
        return code

    def exchange(self, code):
        row = self.consume("pair:" + digest(code))
        if not row or row["expires"] < time.time():
            return None
        token = secrets.token_urlsafe(32)
        self.put("device:" + digest(token), {"created": time.time()})
        return token


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def from_env():
    key = os.environ.get("HOOD_VAULT_KEY")
    if not key:
        secret = os.environ.get("HOOD_VAULT_SECRET", "")
        if len(secret) >= 32:
            # A deployment-generated random secret, not a user password.
            key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    if not key:
        raise RuntimeError(
            "Set HOOD_VAULT_KEY or a generated HOOD_VAULT_SECRET; see .env.example"
        )
    return Vault(os.environ.get("HOOD_DATA_DIR", ".private"), key)
