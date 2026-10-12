"""Company and institution names."""

from __future__ import annotations

import re

from .base import Span
from .lexicon import (
    GENERIC_ORG_WORDS,
    KEEP_ORG_RE,
    MAJOR_PLACES,
    NON_NAME_WORDS,
    ORG_LEADING_JUNK,
    english_word,
    is_caps,
)

LEGAL_SUFFIX = (
    r"(?:Private\s+Limited|Pvt\.?\s+Ltd\.?|Limited|Ltd\.?|LLP|L\.L\.P\.|Family\s+Trust|Trust|"
    r"Bank|Inc\.?|Corporation|LLC|GmbH|PLC|&\s+Associates|Associates|&\s+Co\.?|Group|(?:&|and)\s+Sons)"
)
_ORG_WORD = r"(?:[A-Z][A-Za-z0-9'.\-]*|&|of|and|\(India\))"
SUFFIX_RE = re.compile(rf"\b(?:{_ORG_WORD}\s+){{0,6}}?{LEGAL_SUFFIX}(?![A-Za-z])")
SUFFIX_RE_CAPS = re.compile(SUFFIX_RE.pattern, re.IGNORECASE)
# Suffixes that also end generic phrases ("Refund Bank"): the name needs a proper noun.
WEAK_SUFFIX_RE = re.compile(r"(?:Bank|Trust|Associates|Corporation|Group)$", re.IGNORECASE)

TRAILING_NOISE = MAJOR_PLACES | {"and", "&"}  # "College of Engineering Pune"

# Names recognised by their shape rather than a legal suffix.
BANK_OF_RE = re.compile(r"\b(?:[A-Z][A-Za-z\-]+\s+){0,3}Bank\s+of\s+[A-Z][a-z]+\b")
INSTITUTION_RE = re.compile(
    r"\b(?:[A-Z][\w'’\-]*\s+){1,4}(?:College|University|Institute|School|Academy)"
    r"(?:\s+of(?:\s+(?:[A-Z][a-z]+|&|and)){1,3})?\b"
)
PARTNERSHIP_RE = re.compile(
    r"\b[A-Z][a-z]+(?:-[A-Z][a-z]+)?, [A-Z][a-z]+(?:-[A-Z][a-z]+)? (?:and|&) [A-Z][a-z]+(?:-[A-Z][a-z]+)?\b"
)


def find_orgs(text: str, lower_words: set[str] = frozenset()) -> list[Span]:
    """Names with a legal suffix ("... Private Limited"), banks ("State Bank
    of India"), institutions ("Capri College") and partnerships ("Sharp, Wood
    and Chang")."""
    rules = [
        ("suffix", SUFFIX_RE_CAPS if is_caps(text) else SUFFIX_RE),
        ("bank", BANK_OF_RE),
        ("institution", INSTITUTION_RE),
        ("partnership", PARTNERSHIP_RE),
    ]
    spans: list[Span] = []
    for rule, regex in rules:
        for m in regex.finditer(text):
            span = _org_span(text, m.start(), m.end(), rule, lower_words)
            if span and not any(span.start < s.end and s.start < span.end for s in spans):
                spans.append(span)
    return sorted(spans, key=lambda s: s.start)


def _org_span(text: str, start: int, end: int, rule: str, lower_words: set[str]) -> Span | None:
    skip = ORG_LEADING_JUNK | (GENERIC_ORG_WORDS | NON_NAME_WORDS if rule == "institution" else set())
    while (word := re.match(r"\S+\s+", text[start:end])) and _leading_noise(word.group(0), rule, skip, lower_words):
        start += word.end()
    if rule == "institution":
        while (tail := re.search(r"\s+(\S+)$", text[start:end])) and tail.group(1).lower() in TRAILING_NOISE:
            end -= len(tail.group(0))
    value = text[start:end]
    distinct = distinctive_tokens(value)
    if not distinct or KEEP_ORG_RE.search(value):
        return None
    if rule == "suffix" and WEAK_SUFFIX_RE.search(value) and all(t.lower() in lower_words for t in distinct):
        return None  # "Refund Bank"
    if rule == "institution" and all(english_word(t, lower_words) for t in distinct):
        return None  # "Business School"
    if rule == "partnership":
        words = [w.lower() for w in re.findall(r"[A-Za-z]+", value) if w != "and"]
        if (
            not lower_words
            or re.match(r"\s+(?:Act|Rules|Regulations)\b", text[end:])
            or any(
                english_word(w, lower_words) or w in MAJOR_PLACES | GENERIC_ORG_WORDS | NON_NAME_WORDS for w in words
            )
        ):
            return None  # law titles, lists of places
    return Span(start, end, "ORGANIZATION", value)


def _leading_noise(word: str, rule: str, skip: set[str], lower_words: set[str]) -> bool:
    word = word.strip().lower().strip(",.:;()")
    return word in skip or (rule == "institution" and english_word(word, lower_words))


def distinctive_tokens(org_name: str) -> list[str]:
    """The identifying words of a company name: "KSH International Limited" -> ["KSH"]."""
    toks = re.findall(r"[A-Za-z][A-Za-z0-9'\-]*", org_name)
    return [t for t in toks if len(t) > 1 and t.lower() not in GENERIC_ORG_WORDS and t.lower() not in ORG_LEADING_JUNK]
