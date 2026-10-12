"""Read and rewrite the text of a .docx at the XML level.

Word splits a paragraph into "runs" (pieces with different formatting), so a
name can be stored as ``<w:t>Sarth</w:t><w:t>ak</w:t>``. We therefore build the
full text of each paragraph, detect PII on that text, and map every replacement
back onto the underlying ``<w:t>`` elements.

All text-bearing parts are processed: body, tables, text boxes, headers,
footers, footnotes, endnotes and comments.
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field

from lxml import etree

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"

TEXT_PART = re.compile(r"^word/(document|header\d*|footer\d*|footnotes|endnotes|comments)\.xml$")
RELS_PART = re.compile(r"^word/_rels/.*\.rels$")

# Elements that contribute a character to the paragraph text but cannot hold
# replacement text themselves.
SEPARATORS = {W + "tab": "\t", W + "br": "\n", W + "cr": "\n"}


@dataclass
class Segment:
    element: etree._Element  # a <w:t>, or a separator element
    start: int
    end: int
    editable: bool


@dataclass
class Paragraph:
    part: str
    index: int  # position within the part, used as a stable id
    text: str
    segments: list[Segment] = field(repr=False)

    @property
    def uid(self) -> str:
        return f"{self.part}#{self.index}"


@dataclass(frozen=True)
class Replacement:
    start: int
    end: int
    new_text: str


def _owner_paragraph(el: etree._Element) -> etree._Element | None:
    """Nearest enclosing <w:p>. Text boxes nest paragraphs inside paragraphs,
    so each <w:t> must only be counted for its closest paragraph."""
    node = el.getparent()
    while node is not None and node.tag != W + "p":
        node = node.getparent()
    return node


def _build_paragraph(part: str, index: int, p: etree._Element) -> Paragraph:
    segments: list[Segment] = []
    pieces: list[str] = []
    pos = 0
    for el in p.iter(W + "t", *SEPARATORS):
        if _owner_paragraph(el) is not p:
            continue
        if el.tag == W + "t":
            text = el.text or ""
            editable = True
        else:
            text = SEPARATORS[el.tag]
            editable = False
        segments.append(Segment(el, pos, pos + len(text), editable))
        pieces.append(text)
        pos += len(text)
    return Paragraph(part, index, "".join(pieces), segments)


def apply_replacements(paragraph: Paragraph, replacements: list[Replacement]) -> None:
    """Rewrite the paragraph's <w:t> elements so that each replaced span reads
    ``new_text``. Formatting of the first run touched by a span is kept.

    Replacements must not overlap. They are applied right-to-left so earlier
    offsets stay valid.
    """
    for rep in sorted(replacements, key=lambda r: r.start, reverse=True):
        touched = [s for s in paragraph.segments if s.editable and s.start < rep.end and s.end > rep.start]
        if not touched:
            continue
        first, last = touched[0], touched[-1]
        prefix = (first.element.text or "")[: max(0, rep.start - first.start)]
        if first is not last and _replace_word_aligned(paragraph.text, rep, touched):
            continue
        if first is last:
            suffix = (first.element.text or "")[rep.end - first.start :]
            _set_text(first.element, prefix + rep.new_text + suffix)
        else:
            _set_text(first.element, prefix + rep.new_text)
            for seg in touched[1:-1]:
                _set_text(seg.element, "")
            _set_text(last.element, (last.element.text or "")[rep.end - last.start :])
    # Text changed, so offsets are stale: rebuild from the (mutated) XML.
    rebuilt = _build_paragraph(paragraph.part, paragraph.index, _paragraph_element(paragraph))
    paragraph.text, paragraph.segments = rebuilt.text, rebuilt.segments


def _replace_word_aligned(text: str, rep: Replacement, touched: list[Segment]) -> bool:
    """Keep per-word formatting when a span crosses runs ("Rashi **Patil**" ->
    "Jatin **Nanda**"): if the fake has the same words-and-spaces shape as the
    original, each fake piece goes into the run its original piece started in.
    Returns False when the shapes differ (caller falls back to first-run)."""
    old_pieces = re.split(r"(\s+)", text[rep.start : rep.end])
    new_pieces = re.split(r"(\s+)", rep.new_text)
    if len(old_pieces) != len(new_pieces):
        return False
    out = {id(s): [] for s in touched}
    pos = rep.start
    for old, new in zip(old_pieces, new_pieces, strict=True):
        owner = next((s for s in touched if s.start <= pos < s.end), None)
        if owner is None:
            return False  # piece starts in a tab/break separator
        out[id(owner)].append(new)
        pos += len(old)
    for i, seg in enumerate(touched):
        original = seg.element.text or ""
        keep_before = original[: max(0, rep.start - seg.start)] if i == 0 else ""
        keep_after = original[rep.end - seg.start :] if i == len(touched) - 1 else ""
        _set_text(seg.element, keep_before + "".join(out[id(seg)]) + keep_after)
    return True


def _paragraph_element(paragraph: Paragraph) -> etree._Element:
    for seg in paragraph.segments:
        owner = _owner_paragraph(seg.element)
        if owner is not None:
            return owner
    raise ValueError(f"paragraph {paragraph.uid} has no segments")


def _set_text(t: etree._Element, text: str) -> None:
    t.text = text
    t.set(XML_SPACE, "preserve")


class DocxDocument:
    """A .docx opened as raw XML parts, with every paragraph exposed as text."""

    def __init__(self, path: str):
        self.path = path
        with zipfile.ZipFile(path) as z:
            self._entries = {info.filename: z.read(info.filename) for info in z.infolist()}
            self._order = [info.filename for info in z.infolist()]
        self._trees: dict[str, etree._Element] = {}
        self.paragraphs: list[Paragraph] = []
        for name in self._order:
            if TEXT_PART.match(name):
                root = etree.fromstring(self._entries[name])
                self._trees[name] = root
                for i, p in enumerate(root.iter(W + "p")):
                    para = _build_paragraph(name, i, p)
                    if para.segments:
                        self.paragraphs.append(para)

    # --- media -----------------------------------------------------------
    def media(self) -> dict[str, bytes]:
        return {n: b for n, b in self._entries.items() if n.startswith("word/media/")}

    def replace_media(self, name: str, data: bytes) -> None:
        if name not in self._entries:
            raise KeyError(name)
        self._entries[name] = data

    # --- relationship targets (hyperlinks like mailto:) -------------------
    def hyperlink_targets(self) -> list[tuple[str, str]]:
        out = []
        for name in self._order:
            if RELS_PART.match(name):
                for rel in etree.fromstring(self._entries[name]):
                    if rel.get("TargetMode") == "External":
                        out.append((name, rel.get("Target")))
        return out

    def rewrite_hyperlinks(self, fn) -> None:
        for name in self._order:
            if RELS_PART.match(name):
                root = etree.fromstring(self._entries[name])
                changed = False
                for rel in root:
                    if rel.get("TargetMode") == "External":
                        new = fn(rel.get("Target"))
                        if new != rel.get("Target"):
                            rel.set("Target", new)
                            changed = True
                if changed:
                    self._entries[name] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)

    def rewrite_field_links(self, fn) -> None:
        """Link targets stored as Word field codes: HYPERLINK "mailto:...". They
        are not visible text but travel with the file."""
        for root in self._trees.values():
            for el in root.iter(W + "instrText"):
                if el.text and "HYPERLINK" in el.text:
                    el.text = re.sub(
                        r'(HYPERLINK\s+")([^"]+)(")', lambda m: m.group(1) + fn(m.group(2)) + m.group(3), el.text
                    )

    def save(self, path: str) -> None:
        for name, root in self._trees.items():
            self._entries[name] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            for name in self._order:
                z.writestr(name, self._entries[name])
