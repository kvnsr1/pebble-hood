"""Fill an empty .env key without putting the secret in terminal output/history."""

from pathlib import Path
import os
from cryptography.fernet import Fernet

path = Path(".env")
s = path.read_text()
if "HOOD_VAULT_KEY=\n" not in s:
    raise SystemExit("No empty key entry; existing key left unchanged.")
s = s.replace(
    "HOOD_VAULT_KEY=\n", "HOOD_VAULT_KEY=" + Fernet.generate_key().decode() + "\n", 1
)
fd = os.open(path, os.O_WRONLY | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w") as f:
    f.write(s)
os.chmod(path, 0o600)
print("Vault key initialized in .env. Back it up securely; do not commit it.")
