"""Structured PII: things with a fixed shape, found by regex + validation."""
from __future__ import annotations

import ipaddress
import re

from .base import RegexDetector

# --- validators -------------------------------------------------------------

_VERHOEFF_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6], [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8], [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4], [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]
_VERHOEFF_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2], [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0], [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]
_VERHOEFF_INV = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]


def digits(s: str) -> str:
    return re.sub(r"\D", "", s)


def verhoeff_valid(number: str) -> bool:
    c = 0
    for i, ch in enumerate(reversed(digits(number))):
        c = _VERHOEFF_D[c][_VERHOEFF_P[i % 8][int(ch)]]
    return c == 0


def verhoeff_check_digit(number: str) -> str:
    c = 0
    for i, ch in enumerate(reversed(digits(number))):
        c = _VERHOEFF_D[c][_VERHOEFF_P[(i + 1) % 8][int(ch)]]
    return str(_VERHOEFF_INV[c])


def luhn_valid(number: str) -> bool:
    ds = [int(c) for c in digits(number)]
    total = 0
    for i, d in enumerate(reversed(ds)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0 and len(set(ds)) > 1


def _valid_ip(s: str) -> bool:
    try:
        ipaddress.ip_address(s)
        return True
    except ValueError:
        return False


def _valid_phone(s: str) -> bool:
    return 10 <= len(digits(s)) <= 13


# --- detectors --------------------------------------------------------------

EMAIL = RegexDetector("EMAIL", r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")

# Websites: "www.x.com", "https://x.in", and the document's broken "www.x. com".
URL = RegexDetector(
    "URL",
    r"\b(?:https?://|www\.)[\w-]+(?:\.[a-z]{2,}(?![\w@])|\.\s(?:com|in|org|net)\b)+(?:/[\w./?=&%-]*[\w/])?",
    re.IGNORECASE,
)

# Indian phone numbers. A bare digit run is only accepted when it carries a
# phone signal: a +91 prefix, an STD code joined by a hyphen/parentheses
# (022-68052182), or a phone keyword just before it. This keeps share counts,
# amounts and registration numbers out.
PHONE = RegexDetector(
    "PHONE",
    r"(?:"
    r"\+\s?91[\s-]?\(?\d{2,5}\)?(?:[\s-]?\d{2,5}){1,3}"  # +91 ...
    r"|\(?0\d{2,4}\)?-\d{6,8}"  # 022-68052182 / (022)-...
    r"|(?<=Tel: )\d[\d\s-]{8,14}\d"
    r"|(?<=Tel\.: )\d[\d\s-]{8,14}\d"
    r"|(?<=Telephone: )\d[\d\s-]{8,14}\d"
    r"|(?<=Phone: )\d[\d\s-]{8,14}\d"
    r"|(?<=Mobile: )\d[\d\s-]{8,14}\d"
    r"|(?<=Fax: )\d[\d\s-]{8,14}\d"
    r")",
    validator=_valid_phone,
)

# PAN: 5 letters, 4 digits, 1 letter; the 4th letter is the holder type.
PAN = RegexDetector("PAN", r"\b[A-Z]{3}[ABCFGHLJPTK][A-Z]\d{4}[A-Z]\b")

# Aadhaar: 12 digits, never starting with 0/1, Verhoeff checksum.
AADHAAR = RegexDetector("AADHAAR", r"\b[2-9]\d{3}[\s-]?\d{4}[\s-]?\d{4}\b", validator=verhoeff_valid)

SSN = RegexDetector("SSN", r"\b(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b")

CREDIT_CARD = RegexDetector("CREDIT_CARD", r"\b\d(?:[ -]?\d){12,18}\b", validator=luhn_valid)

IP_ADDRESS = RegexDetector(
    "IP_ADDRESS",
    r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b"
    r"|\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b",
    validator=_valid_ip,
)

_DATE = (
    r"\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}"
    r"|\d{1,2}(?:st|nd|rd|th)?\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*,?\s+\d{4}"
    r"|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}"
)
# Only dates explicitly introduced as a birth date; other dates are not PII.
DOB = RegexDetector(
    "DATE_OF_BIRTH",
    rf"(?:date\s+of\s+birth|\bD\.?O\.?B\.?|born\s+on)\s*[:\-]?\s*(?P<d>{_DATE})",
    re.IGNORECASE,
    group="d",
)

# Corporate Identity Number (identifies the company on the MCA registry).
CIN = RegexDetector(
    "CIN",
    r"\b[LU]\d{5}[A-Z]{2}\d{4}(?:PLC|PTC|FLC|FTC|GOI|NPL|SGC|ULL|ULT|GAP|OPC)\d{6}\b",
)

GSTIN = RegexDetector("GSTIN", r"\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b")

# SEBI registration numbers of intermediaries (INM = merchant banker, INR = registrar, ...).
SEBI_REG = RegexDetector("REGISTRATION_ID", r"\bIN[A-Z]\d{9}\b")

# Other identifying numbers, recognised by the label in front of them:
# company/firm registration, peer-review and membership numbers, DIN.
REG_NUMBER = RegexDetector(
    "REGISTRATION_ID",
    r"(?:registration\s+(?:number|no\.?)|peer\s+review(?:\s+certificate)?\s+(?:number|no\.?)"
    r"|membership\s+(?:number|no\.?)|\bDIN)\s*(?:of\s+[\w ]{1,30}?\s*)?[:\-]?\s*"
    r"(?P<id>[A-Z]{0,3}-?\d{4,}(?:/[A-Z0-9]+)*)",
    re.IGNORECASE,
    group="id",
)

