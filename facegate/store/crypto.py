"""AES-256-GCM encryption for biometric data at rest.

Face templates (embeddings) and stored face crops are encrypted with a key
that lives outside the database. If the key is wrong or missing the service
refuses to start - it never silently skips records it cannot decrypt.
"""

from __future__ import annotations

import base64
import logging
import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

log = logging.getLogger("facegate.crypto")

KEY_ID_LEN = 8  # bytes of the key fingerprint stored with each record


class DataKeyError(RuntimeError):
    pass


class Cipher:
    def __init__(self, key: bytes):
        if len(key) != 32:
            raise DataKeyError("FACEGATE_DATA_KEY must decode to exactly 32 bytes")
        self._aead = AESGCM(key)
        import hashlib

        self.key_id = hashlib.sha256(key).digest()[:KEY_ID_LEN]

    def encrypt(self, plaintext: bytes, aad: bytes = b"") -> bytes:
        nonce = os.urandom(12)
        return self.key_id + nonce + self._aead.encrypt(nonce, plaintext, aad)

    def decrypt(self, blob: bytes, aad: bytes = b"") -> bytes:
        if blob[:KEY_ID_LEN] != self.key_id:
            raise DataKeyError(
                "Record was encrypted with a different data key. Restore the "
                "original FACEGATE_DATA_KEY (or run a key rotation) - refusing "
                "to continue rather than silently dropping enrolled faces."
            )
        nonce = blob[KEY_ID_LEN : KEY_ID_LEN + 12]
        return self._aead.decrypt(nonce, blob[KEY_ID_LEN + 12 :], aad)


def load_cipher(configured_key: str, data_dir: Path, environment: str) -> Cipher:
    if configured_key:
        return Cipher(base64.b64decode(configured_key))
    if environment == "production":
        raise DataKeyError("FACEGATE_DATA_KEY is required in production")
    key_file = data_dir / "dev-data-key.b64"
    if key_file.exists():
        return Cipher(base64.b64decode(key_file.read_text().strip()))
    data_dir.mkdir(parents=True, exist_ok=True)
    key = AESGCM.generate_key(bit_length=256)
    key_file.write_text(base64.b64encode(key).decode())
    log.warning("Generated a development data key at %s - set FACEGATE_DATA_KEY in production", key_file)
    return Cipher(key)
