"""The list of structured detectors run on every paragraph.

Adding a new PII type:
  1. write a detector (usually one ``RegexDetector(...)`` line in patterns.py,
     or a class with ``label`` and ``detect(text)``),
  2. add it to ``STRUCTURED_DETECTORS`` below,
  3. add a fake generator for its label in ``Pseudonymizer.fake``.
Names, organisations and addresses are handled by the catalogue (two-pass)
because they have no fixed shape.
"""
from .patterns import (
    AADHAAR,
    CIN,
    CREDIT_CARD,
    DOB,
    EMAIL,
    GSTIN,
    IP_ADDRESS,
    PAN,
    PHONE,
    PHONE_LABELLED,
    REG_NUMBER,
    SEBI_REG,
    SSN,
    URL,
)

STRUCTURED_DETECTORS = [EMAIL, URL, PHONE, PHONE_LABELLED, PAN, AADHAAR, SSN, CREDIT_CARD, IP_ADDRESS, DOB, CIN, GSTIN, SEBI_REG, REG_NUMBER]
