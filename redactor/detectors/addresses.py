"""Postal addresses, anchored on a postal code."""

from __future__ import annotations

import re

from .base import Span
from .lexicon import is_caps

ADDRESS_WORD_RE = re.compile(
    r"\b(?:road|rd\.|marg|street|st\.|lane|nagar|taluka|village|district|floor|building|complex|"
    r"tower|wing|plot|survey|s\.\s?no|sector|block|phase|park|society|chowk|peth|colony|"
    r"estate|house|centre|center|bhavan|apartment|flat|near|opposite|opp\.|behind|midc|"
    r"industrial area|cross|main|layout)\b",
    re.IGNORECASE,
)
# India "Pune – 411 045", US "Hollandburgh, NY 30246", UK "SR08 7UX".
CITY_PIN_RE = re.compile(r"\b[A-Z][A-Za-z]+(?:\s*[–—-]\s*|,\s*|\s+)[1-9]\d{2}\s?\d{3}\b")
US_STATES = (
    "AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|"
    "NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC|PR|AA|AE|AP"
)
US_ZIP_RE = re.compile(rf"\b[A-Z][A-Za-z.'\- ]*,?\s+(?:{US_STATES})\s+\d{{5}}(?:-\d{{4}})?\b")
UK_POSTCODE_RE = re.compile(r"\b(?:[A-Z]{1,2}\d[A-Z\d]?|GIR)\s?\d[ABD-HJLNP-UW-Z]{2}\b")

# A street line without a postal code: number, up to three words, a street word.
STREET_RE = re.compile(
    r"\b\d{1,6}[A-Za-z]?\s+(?:(?:[A-Z][a-z]+|\d+(?:st|nd|rd|th))\s+){1,3}"
    r"(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln|Boulevard|Blvd|Court|Ct|Way|Place|Pl|Terrace|"
    r"Parkway|Pkwy|Circle|Highway|Square|Trail|Crescent|Plaza|Close)\b\.?"
    r"(?:,?\s+(?:Apt|Apartment|Suite|Unit)\.?\s*\d+)?"
)

# Where an address starts in prose: "Registered Office at", "Office:", "address on file:".
CUE_RE = re.compile(
    r"\b(?:located at|situated at|office at|address(?:ed)? at|address(?:\s+[a-z]+){0,3}\s*:|"
    r"(?:registered |corporate )?office\s*:)\s*",
    re.IGNORECASE,
)
CUE_PROSE_RE = re.compile(CUE_RE.pattern + r"|\bat\s+(?=\S*\d)", re.IGNORECASE)
LEFTOVER_SUFFIX_RE = re.compile(r"\s*(?:Private\s+Limited|Pvt\.?\s+Ltd\.?|Limited|Ltd\.?|LLP)\b")


def find_addresses(text: str, org_spans: list[Span] = ()) -> list[Span]:
    """Addresses ending in a postal code, plus street addresses written without
    one ("I live at 211 West Oak Street")."""
    spans = _postal_addresses(text, org_spans)
    for m in STREET_RE.finditer(text):
        if not any(m.start() < s.end and s.start < m.end() for s in spans):
            spans.append(Span(m.start(), m.end(), "ADDRESS", m.group(0)))
    return sorted(spans, key=lambda s: s.start)


def _postal_addresses(text: str, org_spans: list[Span]) -> list[Span]:
    """Every postal code ends one address. It starts at a cue ("Office at"),
    after a company name on the same line, or at the start of the line. The
    state and country after the code are kept."""
    stripped = text.strip()
    if not stripped:
        return []
    anchors = postal_anchors(text)
    if not anchors:
        # without a postal code, a line must look strongly like an address
        if len(ADDRESS_WORD_RE.findall(text)) < 2 or len(stripped) > 160 or not re.search(r"\d", text):
            return []
        return address_line(text, org_spans)

    spans: list[Span] = []
    prev_end = 0
    cue_re = CUE_PROSE_RE if len(stripped) > 100 else CUE_RE
    for _, end in anchors:
        window_start = max(prev_end, end - 200)
        cues = list(cue_re.finditer(text, window_start, end))
        if cues:
            start = cues[-1].end()
        elif len(stripped) > 200:
            start = window_start
        else:
            start = _skip_orgs(text, max(prev_end, len(text) - len(text.lstrip())), org_spans)
        spans += _span(text, start, end)
        prev_end = end
    return spans


def postal_anchors(text: str) -> list[tuple[int, int]]:
    """Postal codes with their city. A capitals-only "city" inside ordinary
    text ("TCK-100000") is a code, not a city."""
    caps = is_caps(text)
    found = [m.span() for m in CITY_PIN_RE.finditer(text) if caps or not m.group(0).split()[0].rstrip(",–—-").isupper()]
    found += [m.span() for m in US_ZIP_RE.finditer(text)]
    found += [m.span() for m in UK_POSTCODE_RE.finditer(text)]
    anchors: list[tuple[int, int]] = []
    for start, end in sorted(found, key=lambda x: (x[1], x[0])):
        if not anchors or start >= anchors[-1][1]:
            anchors.append((start, end))
    return anchors


def continues_address(prev_line: str, line: str) -> bool:
    """True if `line` is only a postal code and the short line above it is the
    street part ("2401 Gen Thimmayya Road, Cantonment" / "Pune – 411 001")."""
    prev, cur = prev_line.strip(), line.strip().rstrip(",;")
    anchors = postal_anchors(cur)
    if not anchors or anchors[0][0] != 0 or anchors[-1][1] != len(cur) or not prev or len(prev) > 120:
        return False
    if re.search(r"@|:|www\.|https?://", prev):
        return False
    return bool(re.search(r"\d", prev) or ADDRESS_WORD_RE.search(prev))


def address_line(text: str, org_spans: list[Span] = ()) -> list[Span]:
    """The whole line as an address, minus a company name in front of it."""
    start = _skip_orgs(text, len(text) - len(text.lstrip()), org_spans)
    suffix = LEFTOVER_SUFFIX_RE.match(text[start:])
    if suffix and start > 0:
        start += suffix.end()  # "IndusInd Bank| Limited 2401 ..."
    return _span(text, start, len(text.rstrip(" ,;")))


def _skip_orgs(text: str, start: int, org_spans: list[Span]) -> int:
    for org in org_spans:
        if org.start <= start + 2 < org.end + 2 and org.end > start:
            start = org.end
    return start


def _span(text: str, start: int, end: int) -> list[Span]:
    while start < end and text[start] in " ,;:-–\t":
        start += 1
    value = text[start:end]
    return [Span(start, end, "ADDRESS", value)] if len(value) >= 6 else []
