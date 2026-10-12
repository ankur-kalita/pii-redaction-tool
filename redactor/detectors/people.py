"""Rules for person names (NER does the rest, see catalogue.py)."""

from __future__ import annotations

import re

from .lexicon import GENERIC_ORG_WORDS, NON_NAME_WORDS, PLACE_SUFFIXES


def name_word(tok: str) -> bool:
    """A capitalised name word in any script ("Hegde", "Barth-Jones", "O'Brien",
    "D'Souza", "Álvarez"), or an initial ("A.")."""
    core = tok.rstrip(".")
    if len(core) == 1:
        return core.isalpha() and core.isupper()
    core = re.sub(r"^[A-Z]['’]", "", core)
    return all(p[:1].isupper() and p.isalpha() and p[1:].islower() for p in core.split("-"))


# Citation-style names: "B. A. Beckwith", "K. El Emam", "D. Barth-Jones".
_CITED = r"(?:[A-Z]\.\s?){1,3}(?:(?:El|De|Van|Von|Da|Di|Le|La)\s)?[A-Z][a-z]+(?:-[A-Z][a-z]+)?"
CITED_RE = re.compile(_CITED)
# Two or more in a list, or one followed by a quoted title or "et al.".
CITED_CONTEXT_RE = re.compile(
    rf"{_CITED}(?:,\s(?:and\s)?{_CITED}|,?\sand\s{_CITED})+|{_CITED}(?=,\s*[“\"]|\s+et\s+al\b)"
)
ET_AL_RE = re.compile(r"\b([A-Z][a-z]+(?:-[A-Z][a-z]+)?)\s+et\s+al\b")


def find_cited_names(text: str) -> list[str]:
    """Names written as in a reference list. A lone "A. Smith" is not enough
    ("U.S. Code" has the same shape); a list or a citation is."""
    names = [n.group(0) for m in CITED_CONTEXT_RE.finditer(text) for n in CITED_RE.finditer(m.group(0))]
    return names + [m.group(1) for m in ET_AL_RE.finditer(text)]


def plausible_person(name: str, place_tokens: set[str], lower_words: set[str] = frozenset()) -> bool:
    """Filter for NER candidates. Real names never appear in lower case in the
    document ("Working Days" fails), and are not places ("Supa Ahilyanagar")."""
    toks = name.title().split()
    if not 2 <= len(toks) <= 5 or not all(name_word(t) for t in toks):
        return False
    lowered = [t.lower().strip(".") for t in toks]
    if any(t in NON_NAME_WORDS or t in GENERIC_ORG_WORDS - {"family"} for t in lowered):
        return False
    # a long word ending in a place suffix is a place ("Ahilyanagar"); "Kapur" is a name
    if all(t in place_tokens for t in lowered) or any(_place_compound(t) for t in lowered):
        return False
    if any(len(t) > 2 and t in lower_words for t in lowered):
        return False
    return sum(len(t) > 1 for t in lowered) >= 2


def _place_compound(word: str) -> bool:
    return any(word.endswith(suffix) and len(word) >= len(suffix) + 4 for suffix in PLACE_SUFFIXES)
