"""Checksum validators so redaction doesn't eat trace_ids and other long
numbers that merely look like PII. Over-redaction is a real failure mode
(docs/05) — a random 16-digit trace ID must not become <ACCOUNT_1>."""

from __future__ import annotations


def luhn_checksum(digits: str) -> bool:
    digits = digits.replace(" ", "").replace("-", "")
    if not digits.isdigit() or len(digits) < 12:
        return False
    total = 0
    parity = len(digits) % 2
    for i, ch in enumerate(digits):
        d = int(ch)
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


_IBAN_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def iban_mod97(iban: str) -> bool:
    iban = iban.replace(" ", "").upper()
    if len(iban) < 15 or len(iban) > 34:
        return False
    rearranged = iban[4:] + iban[:4]
    numeric = "".join(str(_IBAN_ALPHABET.index(c)) for c in rearranged if c in _IBAN_ALPHABET)
    if not numeric:
        return False
    return int(numeric) % 97 == 1
