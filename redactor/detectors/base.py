from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Protocol


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    label: str
    text: str


class Detector(Protocol):
    """Every PII type is one detector. To add a new PII type, implement this
    and register it in ``redactor.detectors.registry``."""

    label: str

    def detect(self, text: str) -> list[Span]: ...


class RegexDetector:
    """A detector defined by a pattern, plus an optional validator (checksum,
    range check) to reject look-alikes. ``group`` selects the part of the match
    that is the PII, so context words (e.g. "Date of birth:") can be required
    without being replaced."""

    def __init__(
        self,
        label: str,
        pattern: str,
        flags: int = 0,
        validator: Callable[[str], bool] | None = None,
        group: int | str = 0,
    ):
        self.label = label
        self.regex = re.compile(pattern, flags)
        self.validator = validator
        self.group = group

    def detect(self, text: str) -> list[Span]:
        spans = []
        for m in self.regex.finditer(text):
            value = m.group(self.group)
            if not value:
                continue
            if self.validator and not self.validator(value):
                continue
            start, end = m.span(self.group)
            spans.append(Span(start, end, self.label, value))
        return spans
