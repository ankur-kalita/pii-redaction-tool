"""Two passes for names, companies and places.

Pass 1 (`discover`) reads the whole document and builds a catalogue of the
real people, companies and localities in it. Pass 2 (`CatalogueDetector`)
finds every occurrence of them, in any casing and in partial forms, so an
entity found once is replaced everywhere.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .detectors.addresses import ADDRESS_WORD_RE, find_addresses
from .detectors.base import Span
from .detectors.lexicon import (
    GENERIC_ORG_WORDS,
    KEEP_ORG_RE,
    LEGAL_WORDS,
    MAJOR_PLACES,
    NON_NAME_WORDS,
    english_word,
    is_caps,
)
from .detectors.organizations import WEAK_SUFFIX_RE, distinctive_tokens, find_orgs
from .detectors.people import find_cited_names, plausible_person

EMAIL_DOMAIN_RE = re.compile(r"@([\w-]+(?:\.[\w-]+)+)")
EMAIL_LOCAL_RE = re.compile(r"\b([A-Za-z][\w.]*)@[\w-]+\.")
CAP_WORDS_RE = re.compile(r"[A-Z][A-Za-z'\-]*\.?(?:\s+[A-Z][A-Za-z'\-]*\.?)*")
# A nickname right after a company name: '... Limited (“CareEdge Research”)'.
ALIAS_RE = re.compile(r"\s*\(\s*(?:the\s+)?[“\"]([^”\"]{2,60})[”\"]")
ACRONYM_RE = re.compile(r"[A-Z][A-Z\-]{1,11}")
# "Pradhan Mantri Awas Yojana (PMAY)", "Self Certified Syndicate Banks (“SCSBs”)".
EXPANSION_RE = re.compile(
    r"((?:[A-Z][a-z]+[\s-]+(?:[a-z]+\s+)?){2,}[A-Z][a-z]+)\s*\(\s*[“\"]?([A-Z][A-Z\-]+)s?[”\"]?\s*\)"
)


@dataclass
class Catalogue:
    people: set[str] = field(default_factory=set)
    person_tokens: dict[str, Counter] = field(
        default_factory=lambda: defaultdict(Counter)
    )  # token -> first/last counts
    orgs: set[str] = field(default_factory=set)
    brand_tokens: set[str] = field(default_factory=set)  # distinctive company words, lower case
    place_tokens: set[str] = field(default_factory=set)  # words seen inside addresses
    localities: set[str] = field(default_factory=set)  # rare places masked on their own ("Chakan")
    standalone_ok: set[str] = field(default_factory=set)  # tokens safe to match on their own
    caps_brands: set[str] = field(default_factory=set)  # matched only in ALL CAPS ("CARE")
    lower_words: set[str] = field(default_factory=set)  # words the document uses in lower case
    acronyms: set[str] = field(default_factory=set)  # never part of a name ("omb", "nist")
    terms: set[str] = field(default_factory=set)  # glossary terms, neither people nor companies
    term_words: set[str] = field(default_factory=set)
    email_domains: set[str] = field(default_factory=set)

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
        self.brand_tokens.update(t.lower() for t in distinctive_tokens(name))


def discover(texts: list[str], nlp) -> Catalogue:
    cat = Catalogue()
    cat.lower_words = _lower_words(texts)
    cat.terms = defined_terms(texts)
    cat.term_words = {w for t in cat.terms for w in re.findall(r"[a-z][a-z\-]*", t)}
    cat.acronyms = _acronyms(texts)
    cat.email_domains = {m.group(1).lower() for t in texts for m in EMAIL_DOMAIN_RE.finditer(t)}
    _learn_orgs_and_places(cat, texts)
    _learn_people(cat, texts, nlp)
    _choose_standalone(cat)
    _learn_caps_brands(cat)
    _learn_localities(cat)
    return cat


def _lower_words(texts: list[str]) -> set[str]:
    words: set[str] = set()
    for text in texts:
        plain = re.sub(r"\S+@\S+|\b(?:https?://|www\.)\S+", " ", text)  # emails/URLs are lower case anyway
        words.update(re.findall(r"\b[a-z][a-z'\-]+\b", plain))
    return words


def defined_terms(texts: list[str]) -> set[str]:
    """Phrases spelled out by an acronym next to them: a glossary row ("PMAY" |
    "Pradhan Mantri Awas Yojana") or brackets ("... (PMAY)"). They name
    schemes and categories, not people or companies."""

    def spells(phrase: str, acronym: str) -> bool:
        initials = "".join(w[0] for w in phrase.split() if w[0].isupper())
        letters = acronym.replace("-", "")
        return min(len(initials), len(letters)) >= 3 and (initials.startswith(letters) or letters.startswith(initials))

    terms = set()
    for prev, text in zip(["", *texts[:-1]], texts, strict=True):
        if ACRONYM_RE.fullmatch(prev.strip()) and spells(text.strip(), prev.strip()):
            terms.add(text.strip().lower())
        for m in EXPANSION_RE.finditer(text):
            words = m.group(1).split()
            # the phrase may start with an ordinary word ("Our scheme Integrated ...")
            terms |= {
                " ".join(words[k:]).lower() for k in range(len(words) - 1) if spells(" ".join(words[k:]), m.group(2))
            }
    return terms


def _acronyms(texts: list[str]) -> set[str]:
    """ALL-CAPS words used inside ordinary sentences and never title-cased
    ("OMB has issued"). Names in capitals also appear title-cased ("Hegde")."""
    caps_words, title_words = set(), set()
    for text in texts:
        if not is_caps(text):
            caps_words.update(re.findall(r"\b[A-Z]{3,6}\b", text))  # 2 letters are often initials
        title_words.update(re.findall(r"\b[A-Z][a-z]+\b", text))
    return {w.lower() for w in caps_words if w.title() not in title_words}


def _learn_orgs_and_places(cat: Catalogue, texts: list[str]) -> None:
    for text in texts:
        orgs = find_orgs(text, cat.lower_words)
        for o in orgs:
            if WEAK_SUFFIX_RE.search(o.text) and _is_term(o.text, cat.terms):
                continue  # "Self-Certified Syndicate Bank" is a category
            cat.add_org(o.text)
            alias = ALIAS_RE.match(text, o.end)
            if alias and _reuses_brand(alias.group(1), o.text):
                cat.add_org(alias.group(1))
        for a in find_addresses(text, orgs):
            cat.place_tokens.update(t.lower() for t in re.findall(r"[A-Za-z]+", a.text))


def _learn_people(cat: Catalogue, texts: list[str], nlp) -> None:
    """From NER, from reference lists, and from email addresses."""

    def is_acronym(name: str) -> bool:
        return any(t.strip(".").lower() in cat.acronyms for t in name.split())

    # NER cannot read capitals, so ALL-CAPS paragraphs are title-cased first.
    for doc in nlp.pipe((t.title() if is_caps(t) else t for t in texts), batch_size=64):
        for ent in doc.ents:
            if ent.label_ not in ("PERSON", "ORG"):
                continue
            for part in re.split(r"\s*[/,;]\s*|\s+and\s+", ent.text):
                part = re.sub(r"['’]s$", "", part.strip(" .'’"))
                if is_acronym(part) or any(part.lower() in t for t in cat.terms):
                    continue
                if plausible_person(part, cat.place_tokens, cat.lower_words):
                    cat.add_person(part)

    for text in texts:
        for name in find_cited_names(text):
            if not is_acronym(name):
                cat.add_person(name)

    # "sachin.gawade@bank.com" plus the text "Sachin Gawade" names a person.
    joined = "\n".join(texts)
    for local in {m.group(1) for t in texts for m in EMAIL_LOCAL_RE.finditer(t)}:
        parts = re.split(r"[._]", local)
        if 2 <= len(parts) <= 3 and all(p.isalpha() and len(p) > 1 for p in parts):
            name = " ".join(p.title() for p in parts)
            if re.search(r"\b" + r"\s+".join(map(re.escape, name.split())) + r"\b", joined) and plausible_person(
                name, cat.place_tokens, cat.lower_words
            ):
                cat.add_person(name)


def _common(cat: Catalogue, tok: str) -> bool:
    """An ordinary word here: used in lower case, or part of a glossary term."""
    return english_word(tok, cat.lower_words) or tok in cat.term_words


def _choose_standalone(cat: Catalogue) -> None:
    """A word is matched on its own ("Hegde", "KSH") only if it is a proper noun here."""
    for tok in cat.person_tokens:
        if len(tok) >= 3 and not _common(cat, tok) and tok not in cat.place_tokens:
            cat.standalone_ok.add(tok)
    for tok in cat.brand_tokens:
        if len(tok) >= 3 and not _common(cat, tok):
            cat.standalone_ok.add(tok)


def _learn_caps_brands(cat: Catalogue) -> None:
    """A brand that is also an English word ("CARE") is matched only in the
    ALL-CAPS form the document uses inside a company name."""
    for org in cat.orgs:
        if is_caps(org):
            continue  # a heading says nothing about the brand's casing
        for tok in distinctive_tokens(org):
            if tok.isupper() and len(tok) >= 3 and tok.lower() not in cat.standalone_ok | LEGAL_WORDS:
                cat.caps_brands.add(tok)


def _learn_localities(cat: Catalogue) -> None:
    """Rare place names seen inside addresses ("Chakan"). On their own ("our
    plant in Chakan") they still pinpoint the company. Big cities are kept."""
    excluded = MAJOR_PLACES | cat.brand_tokens | set(cat.person_tokens) | NON_NAME_WORDS | GENERIC_ORG_WORDS
    for tok in cat.place_tokens:
        if (
            len(tok) >= 4
            and tok not in excluded
            and not _common(cat, tok)
            and not ADDRESS_WORD_RE.fullmatch(tok)
            and not KEEP_ORG_RE.search(tok)
        ):
            cat.localities.add(tok)


def _is_term(name: str, terms: set[str]) -> bool:
    words = " ".join(re.findall(r"[a-z]+", name.lower()))
    return any(" ".join(re.findall(r"[a-z]+", t)).startswith(words) for t in terms)


def _reuses_brand(alias: str, org: str) -> bool:
    """A nickname must reuse the company's distinctive word ("CareEdge" for
    "CARE ..."); "Practicing Company Secretary" is a role, not a nickname."""
    brands = [t.lower() for t in distinctive_tokens(org) if len(t) >= 3]
    return any(w.lower().startswith(b) for w in alias.split() for b in brands)


PERSONAL_SITE_RE = re.compile(
    r"\b(?:my|his|her|their)\s+(?:own\s+|personal\s+|professional\s+)?"
    r"(?:website|web\s*site|webpage|web\s*page|blog|site|portfolio|homepage)\b[^.]{0,40}$",
    re.IGNORECASE,
)


def owned_url(url: str, cat: Catalogue, before: str = "") -> bool:
    """A website is masked when its owner is: the text calls it someone's
    ("my website at ..."), its domain contains a masked company or person
    name, or the domain is used for email in the document."""
    if PERSONAL_SITE_RE.search(before):
        return True
    host = re.sub(r"(?i)^(?:https?://)?(?:www\.)?", "", url).split("/")[0].replace(" ", "").lower()
    if any(host == d or host.endswith("." + d) or d.endswith("." + host) for d in cat.email_domains):
        return True
    return any(t in host for t in cat.brand_tokens | set(cat.person_tokens) if len(t) >= 3)


def _initial(tok: str) -> bool:
    return len(tok.strip(".")) == 1


def _alternation(words, flags: int = 0) -> re.Pattern | None:
    words = sorted(words, key=len, reverse=True)
    return re.compile(r"\b(?:" + "|".join(words) + r")\b", flags) if words else None


class CatalogueDetector:
    """Pass 2: finds every occurrence of catalogued entities."""

    def __init__(self, cat: Catalogue):
        self.cat = cat
        orgs = [r"\s+".join(map(re.escape, o.split())) for o in cat.orgs]
        self.org_re = (
            re.compile(r"\b(?:" + "|".join(sorted(orgs, key=len, reverse=True)) + r")(?![A-Za-z])", re.IGNORECASE)
            if orgs
            else None
        )
        self.place_re = _alternation(map(re.escape, cat.localities), re.IGNORECASE)
        self.brand_re = _alternation((re.escape(b) for b in cat.brand_tokens if b in cat.standalone_ok), re.IGNORECASE)
        self.caps_re = _alternation(map(re.escape, cat.caps_brands))

    def detect(self, text: str) -> list[Span]:
        spans: list[Span] = []
        if self.org_re:
            spans += [Span(m.start(), m.end(), "ORGANIZATION", m.group(0)) for m in self.org_re.finditer(text)]
        if self.brand_re:
            spans += [
                Span(m.start(), m.end(), "ORGANIZATION", m.group(0))
                for m in self.brand_re.finditer(text)
                if m.group(0)[0].isupper()
            ]
        # in an ALL-CAPS paragraph "CARE" may be the word ("WE TAKE CARE"): short cells only
        if self.caps_re and (not is_caps(text) or len(text.split()) <= 3):
            spans += [Span(m.start(), m.end(), "ORGANIZATION", m.group(0)) for m in self.caps_re.finditer(text)]
        if self.place_re:
            spans += [
                Span(m.start(), m.end(), "LOCATION", m.group(0))
                for m in self.place_re.finditer(text)
                if m.group(0)[0].isupper()
            ]
        return spans + self._people(text)

    def _name_part(self, tok: str, first: bool) -> bool:
        """A known name word or an initial. A name starts with an initial only
        if it is dotted ("B. A. Beckwith"), so "A Hegde family" is safe."""
        if tok.strip(".").lower() in self.cat.person_tokens:
            return True
        return _initial(tok) and (not first or tok.endswith("."))

    def _people(self, text: str) -> list[Span]:
        spans = []
        for m in CAP_WORDS_RE.finditer(text):
            # "Natalia's" is matched as "Natalia"; the possessive stays outside the span
            toks = [
                (re.sub(r"'s$", "", t.group(0)), m.start() + t.start())
                for t in re.finditer(r"[A-Za-z'\-]+\.?", m.group(0))
            ]
            i = 0
            while i < len(toks):
                j = i
                while j < len(toks) and self._name_part(toks[j][0], first=j == i):
                    j += 1
                run = toks[i:j]
                while run and _initial(run[-1][0]):
                    run = run[:-1]
                named = [t.strip(".").lower() for t, _ in run if not _initial(t)]
                cited = len(named) == 1 and len(run) > 1  # "J. Li"
                if len(named) >= 2 or (named and (named[0] in self.cat.standalone_ok or cited)):
                    last, pos = run[-1]
                    start, end = run[0][1], pos + len(last.rstrip("."))
                    spans.append(Span(start, end, "PERSON", text[start:end]))
                i = max(j, i + 1)
        return spans
