"""AES-256-GCM credential encryption.

The key (32 raw bytes, base64-encoded) is read from the BROKER_SECRET_KEY env
var. Only the broker_gateway container needs it set; api should never read
plaintext credentials so it doesn't need the key.

We pin to AES-GCM (authenticated encryption) so tampered ciphertext fails
loudly on decrypt. Each row gets a fresh 12-byte nonce stored alongside the
ciphertext in trading_accounts.credentials_nonce.

Format:
  ciphertext = AES-GCM(key, nonce, json.dumps(creds).encode())
  on disk: nonce kept in credentials_nonce, ciphertext in credentials_encrypted
"""
from __future__ import annotations

import base64
import json
import os
from typing import Optional

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


_KEY_BYTES_LEN = 32   # AES-256
_NONCE_BYTES_LEN = 12


class CryptoConfigError(RuntimeError):
    pass


class CryptoIntegrityError(RuntimeError):
    pass


def _load_key() -> bytes:
    raw = os.environ.get("BROKER_SECRET_KEY", "").strip()
    if not raw:
        raise CryptoConfigError(
            "BROKER_SECRET_KEY env var not set. Generate one with: "
            "python -c \"import os, base64; print(base64.b64encode(os.urandom(32)).decode())\""
        )
    try:
        key = base64.b64decode(raw)
    except Exception as exc:
        raise CryptoConfigError("BROKER_SECRET_KEY must be base64-encoded 32-byte key") from exc
    if len(key) != _KEY_BYTES_LEN:
        raise CryptoConfigError(
            f"BROKER_SECRET_KEY must decode to {_KEY_BYTES_LEN} bytes (got {len(key)})"
        )
    return key


def encrypt_credentials(creds: dict) -> tuple[bytes, bytes]:
    """Encrypt a credentials dict. Returns (ciphertext, nonce)."""
    key = _load_key()
    nonce = os.urandom(_NONCE_BYTES_LEN)
    plain = json.dumps(creds, separators=(",", ":")).encode("utf-8")
    cipher = AESGCM(key).encrypt(nonce, plain, associated_data=None)
    return cipher, nonce


def decrypt_credentials(ciphertext: Optional[bytes], nonce: Optional[bytes]) -> dict:
    """Decrypt a credentials blob. Returns {} if either input is missing."""
    if not ciphertext or not nonce:
        return {}
    key = _load_key()
    try:
        plain = AESGCM(key).decrypt(nonce, ciphertext, associated_data=None)
    except InvalidTag as exc:
        raise CryptoIntegrityError(
            "Credentials decryption failed (wrong key or tampered ciphertext)"
        ) from exc
    return json.loads(plain.decode("utf-8"))
