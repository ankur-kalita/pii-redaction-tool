"""End-to-end redaction: discover entities, detect PII in every paragraph,
replace it with consistent fakes, replace images, write the new .docx."""
from __future__ import annotations

from dataclasses import dataclass, field

import spacy

from .catalogue import Catalogue, CatalogueDetector, discover, owned_url
from .detectors.base import Span
from .detectors.entities import KEEP_DOMAINS, address_line, continues_address, find_addresses, find_orgs
from .detectors.registry import STRUCTURED_DETECTORS
from .docx_io import DocxDocument, Replacement, apply_replacements
from .images import replace_images
from .pseudonymizer import Pseudonymizer

# When two detections overlap, the longer one wins; on equal length, the more
# specific type wins (an email beats the person name inside it).
PRIORITY = [
    "EMAIL", "URL", "CIN", "GSTIN", "PAN", "AADHAAR", "CREDIT_CARD", "SSN", "IP_ADDRESS",
    "PHONE", "REGISTRATION_ID", "DATE_OF_BIRTH", "ADDRESS", "ORGANIZATION", "LOCATION", "PERSON",
]


@dataclass
class Finding:
    paragraph: str  # paragraph uid
    span: Span
    replacement: str


@dataclass
class RedactionResult:
    findings: list[Finding] = field(default_factory=list)
    images_replaced: int = 0
    mapping: dict = field(default_factory=dict)


def resolve_overlaps(spans: list[Span]) -> list[Span]:
    ranked = sorted(spans, key=lambda s: (-(s.end - s.start), PRIORITY.index(s.label)))
    chosen: list[Span] = []
    for s in ranked:
        if all(s.end <= c.start or s.start >= c.end for c in chosen):
            chosen.append(s)
    return sorted(chosen, key=lambda s: s.start)


def is_allowed(span: Span) -> bool:
    """Policy allow-list: regulators' websites/emails are public, not PII."""
    return span.label in ("URL", "EMAIL") and bool(KEEP_DOMAINS.search(span.text.replace(" ", "")))


class Redactor:
    def __init__(self, secret: str = "evaratus-redaction", model: str = "en_core_web_lg"):
        self.secret = secret
        self.nlp = spacy.load(model, disable=["lemmatizer"])

    def detect(self, texts: list[str]):
        """Pass 1 + pass 2. Returns the catalogue and spans per paragraph."""
        cat = discover(texts, self.nlp)
        matcher = CatalogueDetector(cat)
        per_paragraph = []
        for text in texts:
            spans: list[Span] = []
            for det in STRUCTURED_DETECTORS:
                spans += det.detect(text)
            entity_spans = matcher.detect(text) + find_orgs(text, cat.lower_words)
            spans += entity_spans
            spans += find_addresses(text, [s for s in entity_spans if s.label == "ORGANIZATION"])
            spans = [s for s in spans if s.label != "URL" or owned_url(s.text, cat)]
            spans = [s for s in resolve_overlaps(spans) if not is_allowed(s)]
            per_paragraph.append(spans)
        # Addresses split over lines: the street line has no PIN of its own,
        # so it is recognised from the "City – PIN" line below it.
        for i in range(1, len(texts)):
            prev = per_paragraph[i - 1]
            if continues_address(texts[i - 1], texts[i]) and not any(s.label == "ADDRESS" for s in prev):
                orgs = [s for s in prev if s.label == "ORGANIZATION"]
                per_paragraph[i - 1] = resolve_overlaps(prev + address_line(texts[i - 1], orgs))
        return cat, per_paragraph

    def redact(self, input_path: str, output_path: str) -> RedactionResult:
        doc = DocxDocument(input_path)
        texts = [p.text for p in doc.paragraphs]
        cat, per_paragraph = self.detect(texts)

        reserved = set(cat.person_tokens) | cat.brand_tokens
        fakes = Pseudonymizer(self.secret, reserved=reserved)
        fakes.person_roles = {t: ("last" if c["last"] > c["first"] else "first") for t, c in cat.person_tokens.items()}
        fakes.common_words = cat.lower_words
        # Map every company first, so emails/websites seen earlier in the
        # document already reuse the company's fake name.
        # Mixed-case names first, so "Makalu" is styled as a word, not an acronym.
        for org in sorted(cat.orgs, key=lambda o: (o.isupper(), o)):
            fakes.organization(org)

        result = RedactionResult()
        for para, spans in zip(doc.paragraphs, per_paragraph):
            reps = []
            for s in spans:
                new = fakes.fake(s.label, s.text)
                reps.append(Replacement(s.start, s.end, new))
                result.findings.append(Finding(para.uid, s, new))
            if reps:
                apply_replacements(para, reps)

        doc.rewrite_hyperlinks(lambda target: _fake_link(target, fakes, cat))
        result.images_replaced = replace_images(doc)
        doc.save(output_path)
        result.mapping = fakes.mapping()
        return result


def _fake_link(target: str, fakes: Pseudonymizer, cat: Catalogue) -> str:
    if target.lower().startswith("mailto:"):
        return "mailto:" + fakes.email(target[7:])
    if target.lower().startswith(("http://", "https://", "www.")) and owned_url(target, cat):
        return fakes.url(target)
    return target
