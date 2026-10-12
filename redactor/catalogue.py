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
    KEEP_ORG_RE,
    NOT_STANDALONE,
    distinctive_tokens,
    find_addresses,
    find_orgs,
    plausible_person,
)

CAP_WORDS_RE = re.compile(r"[A-Z][A-Za-z'\-]*\.?(?:\s+[A-Z][A-Za-z'\-]*\.?)*")


@dataclass
class Catalogue:
    people: set[str] = field(default_factory=set)  # canonical "Rajesh Kushal Hegde"
    person_tokens: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))  # token -> {"first": n, "last": n}
    orgs: set[str] = field(default_factory=set)
    brand_tokens: set[str] = field(default_factory=set)  # lower-case distinctive org tokens
    place_tokens: set[str] = field(default_factory=set)
    standalone_ok: set[str] = field(default_factory=set)  # tokens safe to match on their own
    lower_words: set[str] = field(default_factory=set)  # words seen in lower case anywhere

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
    for text in paragraph_texts:
        orgs = find_orgs(text, cat.lower_words)
        for o in orgs:
            cat.add_org(o.text)
        for a in find_addresses(text, orgs):
            cat.place_tokens.update(t.lower() for t in re.findall(r"[A-Za-z]+", a.text))

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
                if plausible_person(part, cat.place_tokens, cat.lower_words):
                    cat.add_person(part)

    # A token may be matched on its own (e.g. "Hegde", "KSH") only when it is
    # a proper noun in this document: it never appears in lower case. Otherwise
    # "Broad Family Trust" would turn every "broad" into a fake name.
    def is_english(tok: str) -> bool:
        forms = {tok, tok + "s", tok + "es", tok.rstrip("s"), tok[:-2] if tok.endswith("es") else tok}
        return bool(forms & cat.lower_words) or tok in NOT_STANDALONE

    for tok in list(cat.person_tokens) + list(cat.brand_tokens):
        if len(tok) >= 3 and not is_english(tok) and tok not in cat.place_tokens:
            cat.standalone_ok.add(tok)
    return cat


class CatalogueDetector:
    """Pass-2 detector: finds every occurrence of catalogued entities."""

    def __init__(self, cat: Catalogue):
        self.cat = cat
        orgs = sorted(cat.orgs, key=len, reverse=True)
        self.org_re = (
            re.compile(r"\b(?:" + "|".join(r"\s+".join(map(re.escape, o.split())) for o in orgs) + r")(?![A-Za-z])", re.IGNORECASE)
            if orgs else None
        )
        brands = sorted((b for b in cat.brand_tokens if b in cat.standalone_ok), key=len, reverse=True)
        self.brand_re = re.compile(r"\b(?:" + "|".join(map(re.escape, brands)) + r")\b", re.IGNORECASE) if brands else None

    def detect(self, text: str) -> list[Span]:
        spans: list[Span] = []
        if self.org_re:
            spans += [Span(m.start(), m.end(), "ORGANIZATION", m.group(0)) for m in self.org_re.finditer(text)]
        if self.brand_re:
            for m in self.brand_re.finditer(text):
                word = m.group(0)
                if word[0].isupper():  # proper-noun usage only
                    spans.append(Span(m.start(), m.end(), "ORGANIZATION", word))
        spans += self._people(text)
        return spans

    def _people(self, text: str) -> list[Span]:
        known = self.cat.person_tokens
        spans = []
        for m in CAP_WORDS_RE.finditer(text):
            toks = [(t.group(0), m.start() + t.start()) for t in re.finditer(r"[A-Za-z'\-]+\.?", m.group(0))]
            i = 0
            while i < len(toks):
                j = i
                while j < len(toks) and (toks[j][0].strip(".").lower() in known or (len(toks[j][0].strip(".")) == 1 and j > i)):
                    j += 1
                run = toks[i:j]
                while run and len(run[-1][0].strip(".")) == 1:  # don't end on a stray initial
                    run = run[:-1]
                named = [t for t, _ in run if len(t.strip(".")) > 1]
                single_ok = len(named) == 1 and named[0].strip(".").lower() in self.cat.standalone_ok
                if len(named) >= 2 or single_ok:
                    start = run[0][1]
                    last, pos = run[-1]
                    end = pos + len(last.rstrip("."))
                    spans.append(Span(start, end, "PERSON", text[start:end]))
                i = max(j, i + 1)
        return spans
