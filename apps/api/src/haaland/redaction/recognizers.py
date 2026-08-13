"""Deterministic regex recognisers — the always-on belt, run in addition to
Presidio's ML-assisted analyzer when HAALAND_REDACTION_ENGINE=presidio
(docs/05: "run both; union the results")."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from haaland.redaction.validators import iban_mod97, luhn_checksum


@dataclass(frozen=True)
class Recognizer:
    entity: str
    pattern: re.Pattern[str]
    validator: Callable[[str], bool] | None = None


RECOGNIZERS: list[Recognizer] = [
    Recognizer("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    Recognizer(
        "PHONE",
        re.compile(r"(?<!\d)(?:\+?\d{1,3}[\s-]?)?\(?\d{2,4}\)?[\s-]?\d{3,4}[\s-]?\d{3,4}(?!\d)"),
    ),
    Recognizer("PAN", re.compile(r"\b(?:\d[ -]?){13,19}\b"), luhn_checksum),
    Recognizer("IBAN", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"), iban_mod97),
    Recognizer("BANK_ACCOUNT", re.compile(r"\bACC[-_]?\d{7,12}\b")),
    Recognizer(
        "BANK_ACCOUNT",
        re.compile(r"(?i)\baccount[_\s-]?(?:no|number|id)\W{0,3}(\d{7,16})\b"),
    ),
    Recognizer(
        "CUSTOMER_ID",
        re.compile(r"(?i)\bcust[-_]?[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"),
    ),
]

# Flagged, never filtered — see redaction/prefilter.py and docs/09.
INJECTION_MARKERS: list[re.Pattern[str]] = [
    re.compile(r"(?i)ignore\s+(all\s+)?(previous|prior|above)\s+instruction"),
    re.compile(r"(?i)you\s+are\s+now\s+"),
    re.compile(r"(?i)disregard\s+.{0,20}(system|prompt|rule)"),
    re.compile(r"(?i)</?(system|instruction|admin)>"),
    re.compile(r"(?i)new\s+instructions?\s*:"),
]
