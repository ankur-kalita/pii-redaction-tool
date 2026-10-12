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
    "llc", "ab", "huf", "hospital", "mission",
    "scheme", "portal", "sebi", "icdr", "rta", "cdp", "scsb", "ind", "states", "dollars",
    "department", "foundation", "cell", "chemistry", "analytics", "transformation", "urban",
    "leasing", "advanced", "united",
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
    # institutions: never a place name, never the identifying part of a name
    "institute", "institution", "laboratory", "laboratories", "university", "college", "school",
    "academy", "division", "department", "bureau", "agency", "council", "centre", "center",
}
# Weak suffixes ("Refund Bank", "Long Term Bank") are often generic phrases, so
# an organisation ending in one needs at least one rare (proper-noun) word.
WEAK_SUFFIX_RE = re.compile(r"(?:Bank|Trust|Associates|Corporation|Group)$", re.IGNORECASE)

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
    r"cdslindia\.com|incometax|uidai\.gov\.in|npci\.org\.in|gov\.in|\.gov\b|\.gov\.[a-z]{2}\b|\.mil\b|\.int\b)",
    re.IGNORECASE,
)

LEGAL_SUFFIX = (
    r"(?:Private\s+Limited|Pvt\.?\s+Ltd\.?|Limited|Ltd\.?|LLP|L\.L\.P\.|Family\s+Trust|Trust|"
    r"Bank|Inc\.?|Corporation|LLC|GmbH|PLC|&\s+Associates|Associates|&\s+Co\.?|Group|(?:&|and)\s+Sons)"
)
_ORG_WORD = r"(?:[A-Z][A-Za-z0-9'.\-]*|&|of|and|\(India\))"
ORG_RE = re.compile(
    rf"\b(?:{_ORG_WORD}\s+){{0,6}}?{LEGAL_SUFFIX}(?![A-Za-z])",
)
ORG_RE_CAPS = re.compile(rf"\b(?:{_ORG_WORD}\s+){{0,6}}?{LEGAL_SUFFIX}(?![A-Za-z])", re.IGNORECASE)
# Names recognised by their shape rather than a legal suffix:
#   "State Bank of India": "Bank of <Place>" names a bank even in common words
#   "Capri College", "Rajarshi Shahu College of Engineering"
#   "Sharp, Wood and Chang": a partnership of surnames (PII either way)
BANK_OF_RE = re.compile(r"\b(?:[A-Z][A-Za-z\-]+\s+){0,3}Bank\s+of\s+[A-Z][a-z]+\b")
INSTITUTION_RE = re.compile(
    r"\b(?:[A-Z][\w'’\-]*\s+){1,4}(?:College|University|Institute|School|Academy)"
    r"(?:\s+of(?:\s+(?:[A-Z][a-z]+|&|and)){1,3})?\b"
)
PARTNERSHIP_RE = re.compile(r"\b[A-Z][a-z]+(?:-[A-Z][a-z]+)?, [A-Z][a-z]+(?:-[A-Z][a-z]+)? (?:and|&) [A-Z][a-z]+(?:-[A-Z][a-z]+)?\b")
# Legal-form words: part of a company name, but never its distinctive part.
LEGAL_WORDS = {"llc", "llp", "plc", "ltd", "inc", "pvt", "huf", "gmbh"}

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


def is_caps(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return bool(letters) and sum(c.isupper() for c in letters) / len(letters) > 0.8


def find_orgs(text: str, lower_words: set[str] = frozenset()) -> list[Span]:
    """Company and institution names: a legal suffix ("... Private Limited"),
    a bank or institution shape, or a partnership of surnames."""
    rules = [("suffix", ORG_RE_CAPS if is_caps(text) else ORG_RE), ("bank", BANK_OF_RE),
             ("institution", INSTITUTION_RE), ("partnership", PARTNERSHIP_RE)]
    spans: list[Span] = []
    for rule, regex in rules:
        for m in regex.finditer(text):
            span = _org_span(text, m.start(), m.end(), rule, lower_words)
            if span and not any(span.start < s.end and s.start < span.end for s in spans):
                spans.append(span)
    return sorted(spans, key=lambda s: s.start)


def _org_span(text: str, start: int, end: int, rule: str, lower_words: set[str]) -> Span | None:
    skip = ORG_LEADING_JUNK | (GENERIC_ORG_WORDS | NON_NAME_WORDS if rule == "institution" else set())
    while (word := re.match(r"\S+\s+", text[start:end])) and word.group(0).strip().lower().strip(",.:;()") in skip:
        start += word.end()
    if rule == "institution":
        while (tail := re.search(r"\s+(\S+)$", text[start:end])) and tail.group(1).lower() in MAJOR_PLACES | {"and", "&"}:
            end -= len(tail.group(0))
    value = text[start:end]
    distinct = distinctive_tokens(value)
    if not distinct or KEEP_ORG_RE.search(value):
        return None  # "Stock Exchanges Limited", "the Bank", regulators
    if rule == "suffix" and WEAK_SUFFIX_RE.search(value) and all(t.lower() in lower_words for t in distinct):
        return None  # "Refund Bank", "Escrow Collection Bank"
    if rule == "institution" and all(english_word(t, lower_words) for t in distinct):
        return None  # "Business School"
    if rule == "partnership":
        words = [w.lower() for w in re.findall(r"[A-Za-z]+", value) if w != "and"]
        if (not lower_words or re.match(r"\s+(?:Act|Rules|Regulations)\b", text[end:])
                or any(english_word(w, lower_words) or w in MAJOR_PLACES | GENERIC_ORG_WORDS | NON_NAME_WORDS
                       for w in words)):
            return None  # law titles ("Trades, Callings and Employment Act"), lists of places
    return Span(start, end, "ORGANIZATION", value)


WORD_ENDINGS = ("s", "es", "d", "ed", "ing", "ings", "ly", "er", "ion", "ions", "ation", "ment", "ments", "al")


def english_word(word: str, lower_words: set[str]) -> bool:
    """The document uses this word, or a form of it, in lower case
    ("Employment" -> "employ", "Integrated" -> "integration", "Broad" ->
    "broadly"), so it is a common word rather than a name."""
    word = word.lower()
    if "-" in word:
        return all(english_word(part, lower_words) for part in word.split("-") if part)
    stems = {word} | {word[: -len(e)] for e in WORD_ENDINGS if word.endswith(e) and len(word) - len(e) >= 3}
    return any(stem in lower_words or any(stem + e in lower_words for e in WORD_ENDINGS) for stem in stems)


def distinctive_tokens(org_name: str) -> list[str]:
    """The identifying part of a company name: "KSH International Limited" ->
    ["KSH"]. Generic business words and legal suffixes are not identifying."""
    toks = re.findall(r"[A-Za-z][A-Za-z0-9'\-]*", org_name)
    return [t for t in toks if len(t) > 1 and t.lower() not in GENERIC_ORG_WORDS and t.lower() not in ORG_LEADING_JUNK]


# --- addresses ----------------------------------------------------------------

ADDRESS_WORDS = (
    r"road|rd\.|marg|street|st\.|lane|nagar|taluka|village|district|floor|building|complex|"
    r"tower|wing|plot|survey|s\.\s?no|sector|block|phase|park|society|chowk|peth|colony|"
    r"estate|house|centre|center|bhavan|apartment|flat|near|opposite|opp\.|behind|midc|"
    r"industrial area|cross|main|layout"
)
ADDRESS_WORD_RE = re.compile(rf"\b(?:{ADDRESS_WORDS})\b", re.IGNORECASE)
# City name, an optional dash, and a 6-digit Indian PIN code ("Pune – 411 045").
PIN_RE = re.compile(r"(?<![\d₹.,])\b[1-9]\d{2}\s?\d{3}\b(?![\d%.,]\d)")
CITY_PIN_RE = re.compile(r"\b[A-Z][A-Za-z]+(?:\s*[–—-]\s*|,\s*|\s+)[1-9]\d{2}\s?\d{3}\b")
# US "Hollandburgh, NY 30246" (also military "DPO AP 70602") and UK postcodes
# ("SR08 7UX"): the same role as "City – PIN" for addresses abroad.
US_STATES = (
    "AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|"
    "NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC|PR|AA|AE|AP"
)
US_ZIP_RE = re.compile(rf"\b[A-Z][A-Za-z.'\- ]*,?\s+(?:{US_STATES})\s+\d{{5}}(?:-\d{{4}})?\b")
UK_POSTCODE_RE = re.compile(r"\b(?:[A-Z]{1,2}\d[A-Z\d]?|GIR)\s?\d[ABD-HJLNP-UW-Z]{2}\b")
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
    r"\b(?:located at|situated at|office at|address(?:ed)? at|address(?:\s+[a-z]+){0,3}\s*:|(?:registered |corporate )?office\s*:|"
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
    pins = _postal_anchors(text)
    if not pins:
        # An address line without a PIN must look strongly like one.
        if len(ADDRESS_WORD_RE.findall(text)) < 2 or len(stripped) > 160 or not re.search(r"\d", text):
            return []
        return address_line(text, org_spans)

    spans: list[Span] = []
    prev_end = 0
    cue_re = _CUE_PROSE if len(stripped) > 100 else _CUE
    for pin in pins:
        end = pin[1]
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


def _postal_anchors(text: str) -> list[tuple[int, int]]:
    """Every "City – PIN" (India), "City, ST 12345" (US) or UK postcode. A
    city written in capitals inside ordinary text ("Ticket TCK-100000") is a
    code, not a city."""
    caps = is_caps(text)
    spans = [m.span() for m in CITY_PIN_RE.finditer(text) if caps or not m.group(0).split()[0].rstrip(",–—-").isupper()]
    spans += [m.span() for m in US_ZIP_RE.finditer(text)]
    spans += [m.span() for m in UK_POSTCODE_RE.finditer(text)]
    out = []
    for s, e in sorted(spans, key=lambda x: (x[1], x[0])):
        if out and s < out[-1][1]:
            continue  # overlapping anchors end the same address
        out.append((s, e))
    return out


def continues_address(prev_line: str, line: str) -> bool:
    """An address split over lines: a line that is only "City – PIN" ends an
    address whose street part is on the line above ("2401 Gen Thimmayya Road,
    Cantonment" / "Pune – 411 001"). The line above must look like a street
    line: short, a number or an address word, and not a "Telephone:" style
    label or an email."""
    prev, cur = prev_line.strip(), line.strip().rstrip(",;")
    anchors = _postal_anchors(cur)
    if not anchors or anchors[0][0] != 0 or anchors[-1][1] != len(cur) or not prev or len(prev) > 120:
        return False
    if re.search(r"@|:|www\.|https?://", prev):
        return False
    return bool(re.search(r"\d", prev) or ADDRESS_WORD_RE.search(prev))


def address_line(text: str, org_spans: list[Span] = ()) -> list[Span]:
    """The whole line as one address, minus a company name written in front."""
    start = _skip_orgs(text, len(text) - len(text.lstrip()), org_spans)
    # "IndusInd Bank| Limited 2401 ...": a legal suffix left after the name
    suffix = re.match(r"\s*(?:Private\s+Limited|Pvt\.?\s+Ltd\.?|Limited|Ltd\.?|LLP)\b", text[start:])
    if suffix and start > 0:
        start += suffix.end()
    return _span(text, start, len(text.rstrip(" ,;")))


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

# Citation-style names: "B. A. Beckwith", "K. El Emam", "D. Barth-Jones".
_CITED = r"(?:[A-Z]\.\s?){1,3}(?:(?:El|De|Van|Von|Da|Di|Le|La)\s)?[A-Z][a-z]+(?:-[A-Z][a-z]+)?"
CITED_RE = re.compile(_CITED)
# Two or more in a list, or one followed by a quoted title or "et al."
CITED_CONTEXT_RE = re.compile(
    rf"{_CITED}(?:,\s(?:and\s)?{_CITED}|,?\sand\s{_CITED})+|{_CITED}(?=,\s*[“\"]|\s+et\s+al\b)"
)
ET_AL_RE = re.compile(r"\b([A-Z][a-z]+(?:-[A-Z][a-z]+)?)\s+et\s+al\b")


def find_cited_names(text: str) -> list[str]:
    """Names written as in a reference list. A lone "A. Smith" in prose is not
    enough ("U.S. Code" has the same shape); a list or a citation is."""
    names = [n.group(0) for m in CITED_CONTEXT_RE.finditer(text) for n in CITED_RE.finditer(m.group(0))]
    return names + [m.group(1) for m in ET_AL_RE.finditer(text)]


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
