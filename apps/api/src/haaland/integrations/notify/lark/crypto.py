"""Lark's payload encryption for inbound events and card callbacks.

When an "Encrypt Key" is set on the Lark application, every callback body
arrives as `{"encrypt": "<base64>"}`: AES-256-CBC, key = SHA-256 of the
encrypt key, IV = the first 16 bytes of the ciphertext, PKCS#7 padded. Lark
publishes no other framing, so this is the whole format.

Decryption lives here, next to the rest of the Lark wire format, while
*verification* lives in api/webhooks/signature.py — docs/09 wants exactly
one module to audit for "is this request authentic", and decrypting is not
authenticating."""

from __future__ import annotations

import base64
import hashlib

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

_BLOCK_SIZE = 16


class LarkDecryptionError(Exception):
    """The body could not be decrypted with the configured encrypt key."""


def decrypt_payload(encrypt_key: str, encrypted_b64: str) -> str:
    """Returns the plaintext JSON string. Raises LarkDecryptionError rather
    than leaking a partially-decrypted body into logs."""
    try:
        raw = base64.b64decode(encrypted_b64)
    except (ValueError, TypeError) as exc:
        raise LarkDecryptionError("encrypted payload is not valid base64") from exc

    if len(raw) <= _BLOCK_SIZE or len(raw) % _BLOCK_SIZE:
        raise LarkDecryptionError("encrypted payload has an invalid length")

    key = hashlib.sha256(encrypt_key.encode("utf-8")).digest()
    iv, ciphertext = raw[:_BLOCK_SIZE], raw[_BLOCK_SIZE:]
    decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()

    pad_length = padded[-1]
    if not 1 <= pad_length <= _BLOCK_SIZE or padded[-pad_length:] != bytes([pad_length]) * pad_length:
        raise LarkDecryptionError("decryption produced invalid PKCS#7 padding (wrong encrypt key?)")

    try:
        return padded[:-pad_length].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise LarkDecryptionError("decrypted payload is not valid UTF-8") from exc
