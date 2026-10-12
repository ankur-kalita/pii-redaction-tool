"""Pass 1 (discovery) and pass 2 (matching) for names and organisations.

Discovery runs NER and rules over the whole document and builds a catalogue of
the real people and organisations in it. Matching then finds every occurrence
of catalogued entities, in any casing and in partial forms ("Rajesh Hegde" for
"Rajesh Kushal Hegde"), so that the same entity is replaced everywhere.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .detectors.base import Span
from .detectors.entities import (
    ADDRESS_WORD_RE,
    GENERIC_ORG_WORDS,
    KEEP_ORG_RE,
    WEAK_SUFFIX_RE,
    LEGAL_WORDS,
    NON_NAME_WORDS,
    MAJOR_PLACES,
    distinctive_tokens,
    english_word,
    find_addresses,
    find_cited_names,
    find_orgs,
    is_caps,
    plausible_person,
)

EMAIL_DOMAIN_RE = re.compile(r"@([\w-]+(?:\.[\w-]+)+)")
EMAIL_LOCAL_RE = re.compile(r"\b([A-Za-z][\w.]*)@[\w-]+\.")
CAP_WORDS_RE = re.compile(r"[A-Z][A-Za-z'\-]*\.?(?:\s+[A-Z][A-Za-z'\-]*\.?)*")
# A defined-term nickname right after a company name:
# 'CARE Analytics and Advisory Private Limited (“CareEdge Research”)'.
ALIAS_RE = re.compile(r"\s*\(\s*(?:the\s+)?[“\"]([^”\"]{2,60})[”\"]")


@dataclass
class Catalogue:
    people: set[str] = field(default_factory=set)  # canonical "Rajesh Kushal Hegde"
    person_tokens: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))  # token -> {"first": n, "last": n}
    orgs: set[str] = field(default_factory=set)
    brand_tokens: set[str] = field(default_factory=set)  # lower-case distinctive org tokens
    place_tokens: set[str] = field(default_factory=set)
    standalone_ok: set[str] = field(default_factory=set)  # tokens safe to match on their own
    lower_words: set[str] = field(default_factory=set)  # words seen in lower case anywhere
    localities: set[str] = field(default_factory=set)  # rare place names (Chakan, Birdewadi)
    caps_brands: set[str] = field(default_factory=set)  # "CARE": matched only in ALL CAPS
    acronyms: set[str] = field(default_factory=set)  # "omb", "nist": never part of a name
    email_domains: set[str] = field(default_factory=set)  # "kshinternational.com"

    def add_person(self, name: str) -> None:
        canonical = " ".join(t.strip(".").title() if len(t.strip(".")) > 1 else t for t in name.split())
        self.people.add(canonical)
        toks = canonical.split()
        for i, t in enumerate(toks):
            if len(t.strip(".")) > 1:
                self.person_tokens[t.lower()]["last" if i == len(toks) - 1 else "first"] += 1

    def add_org(self, name: str) -> None:
        name = " ".join(name.split())
        if KEEP_ORG_RE.search(name):
            return
        self.orgs.add(name)
        for t in distinctive_tokens(name):
            self.brand_tokens.add(t.lower())


def discover(paragraph_texts: list[str], nlp) -> Catalogue:
    cat = Catalogue()
    for text in paragraph_texts:
        # Emails/URLs are lower case by convention, not evidence of a common word.
        plain = re.sub(r"\S+@\S+|\b(?:https?://|www\.)\S+", " ", text)
        cat.lower_words.update(re.findall(r"\b[a-z][a-z'\-]+\b", plain))
    terms = defined_terms(paragraph_texts)
    for text in paragraph_texts:
        orgs = find_orgs(text, cat.lower_words)
        for o in orgs:
            if WEAK_SUFFIX_RE.search(o.text) and _is_term(o.text, terms):
                continue  # "Self-Certified Syndicate Bank (SCSB)" is a category, not a company
            cat.add_org(o.text)
            alias = ALIAS_RE.match(text, o.end)
            if alias and _reuses_brand(alias.group(1), o.text):
                cat.add_org(alias.group(1))
        for a in find_addresses(text, orgs):
            cat.place_tokens.update(t.lower() for t in re.findall(r"[A-Za-z]+", a.text))

    # Acronyms: short ALL-CAPS words used inside ordinary sentences ("OMB has
    # issued ...") and never written in title case. A capitals-only line such
    # as "NARA NIST NPPI" is title-cased for NER below, which would otherwise
    # read "Nara Nist" as a person and spread that fake person everywhere.
    # Real names in capitals ("KUSHAL HEGDE") also appear as "Hegde".
    caps_words, title_words = set(), set()
    for text in paragraph_texts:
        if not is_caps(text):
            caps_words.update(re.findall(r"\b[A-Z]{3,6}\b", text))  # 2 letters are often initials ("DM Shetty")
        title_words.update(re.findall(r"\b[A-Z][a-z]+\b", text))
    cat.acronyms = {w.lower() for w in caps_words if w.title() not in title_words}

    def ner_text(t: str) -> str:
        letters = [c for c in t if c.isalpha()]
        caps = letters and sum(c.isupper() for c in letters) / len(letters) > 0.8
        return t.title() if caps else t  # NER is unreliable on ALL CAPS text

    for doc in nlp.pipe((ner_text(t) for t in paragraph_texts), batch_size=64):
        for ent in doc.ents:
            if ent.label_ not in ("PERSON", "ORG"):
                continue
            for part in re.split(r"\s*[/,;]\s*|\s+and\s+", ent.text):
                part = part.strip(" .'’")
                part = re.sub(r"['’]s$", "", part)
                if any(t.lower() in cat.acronyms for t in part.split()) or any(part.lower() in t for t in terms):
                    continue
                if plausible_person(part, cat.place_tokens, cat.lower_words):
                    cat.add_person(part)

    for text in paragraph_texts:
        for name in find_cited_names(text):
            if not any(t.strip(".").lower() in cat.acronyms for t in name.split()):
                cat.add_person(name)

    # People revealed by their email: "sachin.gawade@bank.com" next to the
    # text "Sachin Gawade" names a person even when NER misses the name.
    cat.email_domains = {m.group(1).lower() for t in paragraph_texts for m in EMAIL_DOMAIN_RE.finditer(t)}
    joined = "\n".join(paragraph_texts)
    for local in {m.group(1) for t in paragraph_texts for m in EMAIL_LOCAL_RE.finditer(t)}:
        parts = re.split(r"[._]", local)
        if 2 <= len(parts) <= 3 and all(p.isalpha() and len(p) > 1 for p in parts):
            name = " ".join(p.title() for p in parts)
            if re.search(r"\b" + r"\s+".join(map(re.escape, name.split())) + r"\b", joined) and plausible_person(
                    name, cat.place_tokens, cat.lower_words):
                cat.add_person(name)

    # A token may be matched on its own (e.g. "Hegde", "KSH") only when it is
    # a proper noun in this document: it never appears in lower case. Otherwise
    # "Broad Family Trust" would turn every "broad" into a fake name.
    term_words = {w for t in terms for w in re.findall(r"[a-z][a-z\-]*", t)}

    def is_english(tok: str) -> bool:
        return english_word(tok, cat.lower_words) or tok in term_words

    for tok in cat.person_tokens:
        if len(tok) >= 3 and not is_english(tok) and tok not in cat.place_tokens:
            cat.standalone_ok.add(tok)
    for tok in cat.brand_tokens:
        if len(tok) >= 3 and not is_english(tok):
            cat.standalone_ok.add(tok)
    # A distinctive word that is also an English word ("CARE" in "CARE
    # Analytics ... Limited") cannot be matched in every casing, but the
    # document writing it in ALL CAPS inside a company name shows that the
    # ALL-CAPS form is the brand. Only that exact form is matched; "care" and
    # "Care" stay untouched.
    for org in cat.orgs:
        if is_caps(org):
            continue  # an ALL-CAPS heading says nothing about the brand's casing
        for tok in distinctive_tokens(org):
            if (tok.isupper() and len(tok) >= 3 and tok.lower() not in cat.standalone_ok
                    and tok.lower() not in LEGAL_WORDS):
                cat.caps_brands.add(tok)
    # Localities: rare place names seen inside an address ("Chakan",
    # "Birdewadi"). Mentioned on their own ("Unit 2 in Chakan") they still
    # pinpoint the company's plants. Major cities/states are kept.
    for tok in cat.place_tokens:
        if (len(tok) >= 4 and not is_english(tok) and tok not in MAJOR_PLACES
                and tok not in cat.brand_tokens and tok not in cat.person_tokens
                and not ADDRESS_WORD_RE.fullmatch(tok) and not KEEP_ORG_RE.search(tok)
                and tok not in NON_NAME_WORDS and tok not in GENERIC_ORG_WORDS and tok != "embassy"):
            cat.localities.add(tok)
    return cat


ACRONYM_RE = re.compile(r"[A-Z][A-Z\-]{1,11}")
EXPANSION_RE = re.compile(r"((?:[A-Z][a-z]+[\s-]+(?:[a-z]+\s+)?){2,}[A-Z][a-z]+)\s*\(\s*[“\"]?([A-Z][A-Z\-]+)s?[”\"]?\s*\)")


def defined_terms(paragraph_texts: list[str]) -> set[str]:
    """Phrases spelled out by an acronym next to them, in a glossary row
    ("PMAY" | "Pradhan Mantri Awas Yojana") or in brackets ("... (PMAY)").
    They name schemes and bodies, not people."""
    def spells(phrase: str, acronym: str) -> bool:
        initials = "".join(w[0] for w in phrase.split() if w[0].isupper())
        letters = acronym.replace("-", "")
        return min(len(initials), len(letters)) >= 3 and (initials.startswith(letters) or letters.startswith(initials))

    terms = set()
    for prev, text in zip([""] + paragraph_texts, paragraph_texts):
        if ACRONYM_RE.fullmatch(prev.strip()) and spells(text.strip(), prev.strip()):
            terms.add(text.strip().lower())
        terms |= {m.group(1).lower() for m in EXPANSION_RE.finditer(text) if spells(m.group(1), m.group(2))}
    return terms


def _is_term(name: str, terms: set[str]) -> bool:
    words = " ".join(re.findall(r"[a-z]+", name.lower()))
    return any(" ".join(re.findall(r"[a-z]+", t)).startswith(words) for t in terms)


def _initial(tok: str) -> bool:
    return len(tok.strip(".")) == 1


def _reuses_brand(alias: str, org: str) -> bool:
    """A nickname counts only if it reuses the company's distinctive word
    ("CareEdge Research" for "CARE Analytics ..."); defined terms like
    "Practicing Company Secretary" or "Group Entities" are roles, not names."""
    brands = [t.lower() for t in distinctive_tokens(org) if len(t) >= 3]
    return any(w.lower().startswith(b) for w in alias.split() for b in brands)


def owned_url(url: str, cat: Catalogue) -> bool:
    """A website identifies its owner. It is masked when the owner is: its
    domain contains a masked company or person name, or is used for email in
    the document. Public references (a journal, github.com) are kept."""
    host = re.sub(r"(?i)^(?:https?://)?(?:www\.)?", "", url).split("/")[0].replace(" ", "").lower()
    if any(host == d or host.endswith("." + d) or d.endswith("." + host) for d in cat.email_domains):
        return True
    owners = (t for t in cat.brand_tokens | set(cat.person_tokens) if len(t) >= 3)
    return any(t in host for t in owners)


class CatalogueDetector:
    """Pass-2 detector: finds every occurrence of catalogued entities."""

    def __init__(self, cat: Catalogue):
        self.cat = cat
        orgs = sorted(cat.orgs, key=len, reverse=True)
        self.org_re = (
            re.compile(r"\b(?:" + "|".join(r"\s+".join(map(re.escape, o.split())) for o in orgs) + r")(?![A-Za-z])", re.IGNORECASE)
            if orgs else None
        )
        places = sorted(cat.localities, key=len, reverse=True)
        self.place_re = re.compile(r"\b(?:" + "|".join(map(re.escape, places)) + r")\b", re.IGNORECASE) if places else None
        brands = sorted((b for b in cat.brand_tokens if b in cat.standalone_ok), key=len, reverse=True)
        self.brand_re = re.compile(r"\b(?:" + "|".join(map(re.escape, brands)) + r")\b", re.IGNORECASE) if brands else None
        caps = sorted(cat.caps_brands, key=len, reverse=True)
        self.caps_re = re.compile(r"\b(?:" + "|".join(map(re.escape, caps)) + r")\b") if caps else None  # case-sensitive

    def detect(self, text: str) -> list[Span]:
        spans: list[Span] = []
        if self.org_re:
            spans += [Span(m.start(), m.end(), "ORGANIZATION", m.group(0)) for m in self.org_re.finditer(text)]
        if self.brand_re:
            for m in self.brand_re.finditer(text):
                word = m.group(0)
                if word[0].isupper():  # proper-noun usage only
                    spans.append(Span(m.start(), m.end(), "ORGANIZATION", word))
        # In an ALL-CAPS paragraph "CARE" may be the English word ("WE TAKE
        # CARE OF ..."), so there it is only matched in short cells ("‘CARE A-’").
        if self.caps_re and (not is_caps(text) or len(text.split()) <= 3):
            spans += [Span(m.start(), m.end(), "ORGANIZATION", m.group(0)) for m in self.caps_re.finditer(text)]
        if self.place_re:
            spans += [Span(m.start(), m.end(), "LOCATION", m.group(0)) for m in self.place_re.finditer(text) if m.group(0)[0].isupper()]
        spans += self._people(text)
        return spans

    def _name_part(self, tok: str, first: bool) -> bool:
        """A known name word, or an initial. A name may start with an initial
        only when it is dotted ("B. A. Beckwith"), so the article in "A Hegde
        family" is not taken for one."""
        if tok.strip(".").lower() in self.cat.person_tokens:
            return True
        return _initial(tok) and (not first or tok.endswith("."))

    def _people(self, text: str) -> list[Span]:
        spans = []
        for m in CAP_WORDS_RE.finditer(text):
            toks = [(t.group(0), m.start() + t.start()) for t in re.finditer(r"[A-Za-z'\-]+\.?", m.group(0))]
            i = 0
            while i < len(toks):
                j = i
                while j < len(toks) and self._name_part(toks[j][0], first=j == i):
                    j += 1
                run = toks[i:j]
                while run and _initial(run[-1][0]):  # don't end on a stray initial
                    run = run[:-1]
                named = [t.strip(".").lower() for t, _ in run if not _initial(t)]
                cited = len(named) == 1 and len(run) > 1  # "J. Li"
                if len(named) >= 2 or (named and (named[0] in self.cat.standalone_ok or cited)):
                    start = run[0][1]
                    last, pos = run[-1]
                    end = pos + len(last.rstrip("."))
                    spans.append(Span(start, end, "PERSON", text[start:end]))
                i = max(j, i + 1)
        return spans
