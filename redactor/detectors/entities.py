"""Unstructured PII: person names, organisations and postal addresses.

These have no fixed shape, so detection is two-step (see ``catalogue.py``):
  1. *Discovery*: NER + rules find entities wherever they are recognisable.
  2. *Matching*: every discovered entity is then matched everywhere in the
     document, so a name found once is replaced in every occurrence, including
     places where NER would have missed it (ALL-CAPS headings, tables).
"""
from __future__ import annotations

import re

from .base import Span

# Words that never belong to a person's name in this kind of document. Used to
# reject NER false positives such as "Supa Facility" or "Rajesh Branch".
NON_NAME_WORDS = {
    "email", "e-mail", "fiscal", "fiscals", "facility", "price", "branch", "account", "slip",
    "circular", "schedule", "offer", "bid", "equity", "share", "shares", "fund", "funds",
    "limited", "ltd", "llp", "trust", "bank", "company", "india", "private", "group",
    "upi", "asba", "id", "pin", "act", "rules", "regulations", "board", "committee",
    "investor", "investors", "portion", "capital", "management", "securities", "finance",
    "road", "marg", "nagar", "taluka", "village", "district", "street", "lane", "floor",
    "building", "complex", "tower", "park", "society", "station", "chowk", "peth", "colony",
    "estate", "industrial", "area", "sector", "plot", "wing", "house", "centre", "center",
    "east", "west", "north", "south", "highway", "corporate", "office", "registered",
    "plant", "unit", "warehouse", "director", "officer", "secretary", "chairman", "partner",
    "auditor", "auditors", "accountants", "chartered", "associates", "ebit", "ebitda", "pat",
    "bill", "cap", "floor", "red", "herring", "prospectus", "annexure", "section", "clause",
    "llc", "ab", "huf", "hospital", "pradhan", "mantri", "yojana", "awas", "kisan", "mission",
    "scheme", "portal", "sebi", "icdr", "rta", "cdp", "scsb", "ind", "states", "dollars",
    "department", "foundation", "cell", "chemistry", "analytics", "transformation", "urban",
    "leasing", "suraksha", "urja", "advanced", "united",
}
# Capitalised English words that must never be matched on their own, even
# though they are part of a company name here ("Georgia Transformer Corporation").
NOT_STANDALONE = {
    "federal", "georgia", "virginia", "emirates", "united", "advanced", "cell", "chemistry",
    "urban", "analytics", "link", "foundation", "integrated", "precision", "care", "broad",
    "everest", "states", "dollars", "transformation", "union", "self-certified", "rod", "llc",
    "fig-ops", "kumar", "ram", "rai", "shah", "deen", "dayal", "bharat", "malabar",
}
PLACE_SUFFIXES = ("nagar", "wadi", "pur", "abad", "gaon", "pada", "khed", "marg")

# Generic words inside company names: not identifying on their own, so they
# are kept (only the distinctive part of a company name is replaced).
GENERIC_ORG_WORDS = {
    "international", "india", "indian", "industries", "industrial", "engineering", "engineers",
    "wealth", "management", "securities", "capital", "finance", "financial", "services",
    "solutions", "technologies", "technology", "holdings", "investments", "investment",
    "ventures", "venture", "enterprises", "group", "global", "family", "trust", "bank",
    "limited", "ltd", "private", "pvt", "llp", "and", "&", "of", "the", "co", "company",
    "corporation", "associates", "partners", "consultants", "advisors", "advisory",
    "insurance", "life", "general", "fund", "funds", "asset", "assets", "park", "products",
    "manufacturing", "automotive", "auto", "components", "electricals", "electrical",
    "power", "energy", "systems", "infra", "infrastructure", "realty", "estates", "trading",
    "exports", "imports", "logistics", "pharma", "chemicals", "plastics", "metals", "steel",
    "agro", "foods", "textiles", "motors", "electronics", "intime", "broking", "markets",
    "market", "institutional", "equities", "research", "legal", "law", "chambers",
    "chartered", "accountants", "formerly", "i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix",
    "x", "a", "b", "c", "1", "2", "3",
}
# Weak suffixes ("Refund Bank", "Long Term Bank") are often generic phrases, so
# an organisation ending in one needs at least one rare (proper-noun) word.
WEAK_SUFFIX_RE = re.compile(r"(?:Bank|Trust|Associates|Corporation)$", re.IGNORECASE)

# Public institutions present in every Indian prospectus: they do not identify
# the issuer or any individual, and the document's structure depends on them.
KEEP_ORG_PATTERNS = [
    r"securities and exchange board", r"\bsebi\b", r"\bbse\b", r"national stock exchange",
    r"reserve bank", r"\brbi\b", r"national securities depository", r"\bnsdl\b",
    r"central depository services", r"\bcdsl\b", r"registrar of companies", r"government of",
    r"ministry of", r"income tax", r"unique identification authority", r"stock exchange",
    r"national company law", r"\bnclt\b", r"\bicai\b", r"institute of chartered accountants",
    r"insurance regulatory", r"\birdai\b", r"pension fund regulatory", r"\bmca\b",
    r"high court", r"supreme court", r"life insurance companies", r"provident fund",
    r"national payments corporation", r"solar energy corporation", r"export-import bank",
]
KEEP_ORG_RE = re.compile("|".join(KEEP_ORG_PATTERNS), re.IGNORECASE)

KEEP_DOMAINS = re.compile(
    r"(?:sebi\.gov\.in|bseindia\.com|nseindia\.com|rbi\.org\.in|mca\.gov\.in|nsdl\.co\.in|"
    r"cdslindia\.com|incometax|uidai\.gov\.in|npci\.org\.in|gov\.in|fbil\.org\.in|oanda\.com|"
    r"citibank\.com)",
    re.IGNORECASE,
)

LEGAL_SUFFIX = (
    r"(?:Private\s+Limited|Pvt\.?\s+Ltd\.?|Limited|Ltd\.?|LLP|L\.L\.P\.|Family\s+Trust|Trust|"
    r"Bank|Inc\.?|Corporation|LLC|GmbH|PLC|&\s+Associates|Associates|&\s+Co\.?)"
)
_ORG_WORD = r"(?:[A-Z][A-Za-z0-9'.\-]*|&|of|and|\(India\))"
ORG_RE = re.compile(
    rf"\b(?:{_ORG_WORD}\s+){{0,6}}?{LEGAL_SUFFIX}(?![A-Za-z])",
)
ORG_RE_CAPS = re.compile(rf"\b(?:{_ORG_WORD}\s+){{0,6}}?{LEGAL_SUFFIX}(?![A-Za-z])", re.IGNORECASE)

# Leading words that the suffix regex can sweep up but are not part of a name.
ORG_LEADING_JUNK = {
    "the", "our", "of", "and", "&", "by", "for", "to", "in", "at", "with", "from", "on", "as",
    "such", "this", "that", "any", "each", "all", "its", "their", "which", "said", "also",
    "name", "book", "running", "lead", "manager", "managers", "registrar", "offer", "banker",
    "bankers", "sponsor", "statutory", "auditor", "auditors", "legal", "counsel", "promoter",
    "promoters", "company", "issuer", "contact", "person", "between", "namely", "being",
    "dated", "email", "telephone", "website", "is", "are", "was", "were", "an", "a",
    "selling", "shareholder", "shareholders", "members", "member", "subsidiary", "subsidiaries",
    "group", "entity", "entities", "see", "refer", "pursuant", "under", "agreement", "note",
}


def _is_caps(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return bool(letters) and sum(c.isupper() for c in letters) / len(letters) > 0.8


def find_orgs(text: str, lower_words: set[str] = frozenset()) -> list[Span]:
    """Company names ending in a legal suffix ("... Private Limited", "... LLP",
    "... Family Trust"), with leading non-name words trimmed off."""
    regex = ORG_RE_CAPS if _is_caps(text) else ORG_RE
    spans = []
    for m in regex.finditer(text):
        start, value = m.start(), m.group(0)
        words = value.split()
        while words and words[0].lower().strip(",.:;()") in ORG_LEADING_JUNK:
            start += text[start:].index(words[0]) + len(words[0])
            while start < len(text) and text[start].isspace():
                start += 1
            words = words[1:]
        value = text[start : m.end()]
        distinct = distinctive_tokens(value)
        if not distinct:
            continue  # e.g. "Stock Exchanges Limited", "the Bank"
        if WEAK_SUFFIX_RE.search(value) and not any(t.lower() not in lower_words for t in distinct):
            continue  # "Refund Bank", "Escrow Collection Bank"
        if KEEP_ORG_RE.search(value):
            continue
        spans.append(Span(start, m.end(), "ORGANIZATION", value))
    return spans


def distinctive_tokens(org_name: str) -> list[str]:
    """The identifying part of a company name: "KSH International Limited" ->
    ["KSH"]. Generic business words and legal suffixes are not identifying."""
    toks = re.findall(r"[A-Za-z][A-Za-z0-9'\-]*", org_name)
    return [t for t in toks if t.lower() not in GENERIC_ORG_WORDS and t.lower() not in ORG_LEADING_JUNK]


# --- addresses ----------------------------------------------------------------

ADDRESS_WORDS = (
    r"road|rd\.|marg|street|st\.|lane|nagar|taluka|village|district|floor|building|complex|"
    r"tower|wing|plot|survey|s\.\s?no|sector|block|phase|park|society|chowk|peth|colony|"
    r"estate|house|centre|center|bhavan|apartment|flat|near|opposite|opp\.|behind|midc|"
    r"industrial area|cross|main|layout|gymkhana|reclamation|kurla|bandra|parel"
)
ADDRESS_WORD_RE = re.compile(rf"\b(?:{ADDRESS_WORDS})\b", re.IGNORECASE)
# City name, an optional dash, and a 6-digit Indian PIN code ("Pune – 411 045").
PIN_RE = re.compile(r"(?<![\d₹.,])\b[1-9]\d{2}\s?\d{3}\b(?![\d%.,]\d)")
CITY_PIN_RE = re.compile(r"\b[A-Z][A-Za-z]+(?:\s*[–—-]\s*|,\s*|\s+)[1-9]\d{2}\s?\d{3}\b")
ADDRESS_LABEL_RE = re.compile(
    r"^(?:.*?\b(?:address|registered office|corporate office|office|located at|situated at|at)\b\s*[:\-]?\s*)",
    re.IGNORECASE,
)


MAJOR_PLACES = {
    "india", "maharashtra", "gujarat", "karnataka", "delhi", "new", "mumbai", "pune", "bengaluru",
    "bangalore", "chennai", "kolkata", "hyderabad", "ahmedabad", "tamil", "nadu", "west", "bengal",
    "uttar", "pradesh", "telangana", "rajasthan", "haryana", "kerala", "goa", "noida", "gurugram",
}

_CUE = re.compile(
    r"\b(?:located at|situated at|office at|address(?:ed)? at|address\s*:|registered office\s*:|"
    r"corporate office\s*:)\s*",
    re.IGNORECASE,
)
_CUE_PROSE = re.compile(_CUE.pattern + r"|\bat\s+(?=\S*\d)", re.IGNORECASE)


def find_addresses(text: str, org_spans: list[Span] = ()) -> list[Span]:
    """Postal addresses. Two shapes occur in this document:
      * an address on its own line / table cell, often split over several
        lines, usually ending in "City – PIN";
      * addresses embedded in prose ("... Registered Office at <address>,
        Pune – 410 501, Maharashtra, India and its Corporate Office at ...").
    Every "City – PIN" in a paragraph ends one address. The State/Country tail
    ("Maharashtra, India") is kept: it is not identifying and keeps the
    sentence readable."""
    stripped = text.strip()
    if not stripped:
        return []
    pins = list(CITY_PIN_RE.finditer(text))
    if not pins:
        # An address line without a PIN must look strongly like one.
        if len(ADDRESS_WORD_RE.findall(text)) < 2 or len(stripped) > 160 or not re.search(r"\d", text):
            return []
        start = _skip_orgs(text, len(text) - len(text.lstrip()), org_spans)
        end = len(text.rstrip(" ,;"))
        return _span(text, start, end)

    spans: list[Span] = []
    prev_end = 0
    cue_re = _CUE_PROSE if len(stripped) > 100 else _CUE
    for pin in pins:
        end = pin.end()
        window_start = max(prev_end, end - 200)
        cue = None
        for cue in cue_re.finditer(text, window_start, end):
            pass
        if cue:
            start = cue.end()
        elif len(stripped) > 200:
            start = window_start  # long prose without a cue: bounded window
        else:
            start = _skip_orgs(text, max(prev_end, len(text) - len(text.lstrip())), org_spans)
        spans += _span(text, start, end)
        prev_end = end
    return spans


def _skip_orgs(text: str, start: int, org_spans: list[Span]) -> int:
    """Skip a company name written in front of the address on the same line."""
    for org in org_spans:
        if org.start <= start + 2 < org.end + 2 and org.end > start:
            start = org.end
    return start


def _span(text: str, start: int, end: int) -> list[Span]:
    while start < end and text[start] in " ,;:-–\t":
        start += 1
    value = text[start:end]
    if len(value) < 6:
        return []
    return [Span(start, end, "ADDRESS", value)]


# --- people -------------------------------------------------------------------

NAME_TOKEN_RE = re.compile(r"^[A-Z][a-z]+(?:-[A-Z][a-z]+)?$|^[A-Z]\.?$")


def plausible_person(name: str, place_tokens: set[str], lower_words: set[str] = frozenset()) -> bool:
    """Filter for NER PERSON (and person-shaped ORG) candidates."""
    toks = name.title().split()
    if not 2 <= len(toks) <= 5:
        return False
    if not all(NAME_TOKEN_RE.match(t) for t in toks):
        return False
    lowered = [t.lower().strip(".") for t in toks]
    if any(t in NON_NAME_WORDS or t in GENERIC_ORG_WORDS - {"family"} for t in lowered):
        return False
    if all(t in place_tokens for t in lowered):
        return False  # "Birdewadi Chakan" is a place, not a person
    if any(t.endswith(PLACE_SUFFIXES) for t in lowered):
        return False  # "Supa Ahilyanagar"
    if any(len(t) > 2 and t in lower_words for t in lowered):
        return False  # "Working Days": real names never appear in lower case
    return sum(len(t) > 1 for t in lowered) >= 2
