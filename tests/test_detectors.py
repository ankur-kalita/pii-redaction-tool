"""Detector tests. The prospectus has no PAN/Aadhaar/SSN/card/IP/DOB in its text,
so these types are covered here with synthetic examples."""
import pytest

from redactor.detectors.entities import find_addresses, find_orgs
from redactor.detectors.patterns import (
    AADHAAR, CIN, CREDIT_CARD, DOB, EMAIL, IP_ADDRESS, PAN, PHONE, REG_NUMBER, SSN, URL,
)


def found(detector, text):
    return [s.text for s in detector.detect(text)]


@pytest.mark.parametrize("text, expected", [
    ("Email: cs.connect@kshinternational.com", ["cs.connect@kshinternational.com"]),
    ("no email here @ all", []),
])
def test_email(text, expected):
    assert found(EMAIL, text) == expected


@pytest.mark.parametrize("text, expected", [
    ("Telephone: + 91 20 4505 3237;", ["+ 91 20 4505 3237"]),
    ("Tel: +91 22 40094400", ["+91 22 40094400"]),
    ("Telephone: 022-68052182 Email", ["022-68052182"]),
    ("Telephone: +91-20-26234000", ["+91-20-26234000"]),
    ("allotted 4,50,00,000 Equity Shares worth 2025 2026", []),  # amounts/years are not phones
])
def test_phone(text, expected):
    assert found(PHONE, text) == expected


def test_url_handles_broken_spacing_and_stops_at_prose():
    assert found(URL, "www.kshinternational. com") == ["www.kshinternational. com"]
    assert found(URL, "see www.fbil.org.in. and others") == ["www.fbil.org.in"]


def test_pan_requires_valid_holder_type():
    assert found(PAN, "PAN NBWPS1951N") == ["NBWPS1951N"]
    assert found(PAN, "code ABCDE1234F") == []  # 4th letter 'D' is not a PAN holder type


def test_aadhaar_requires_verhoeff_checksum():
    assert found(AADHAAR, "Aadhaar 2943 6593 3461") == ["2943 6593 3461"]
    assert found(AADHAAR, "Aadhaar 2943 6593 3462") == []


def test_credit_card_requires_luhn():
    assert found(CREDIT_CARD, "card 4111 1111 1111 1111") == ["4111 1111 1111 1111"]
    assert found(CREDIT_CARD, "card 4111 1111 1111 1112") == []


def test_ssn_ip_dob():
    assert found(SSN, "SSN 123-45-6789") == ["123-45-6789"]
    assert found(SSN, "SSN 000-45-6789") == []
    assert found(IP_ADDRESS, "server 10.20.30.40 up") == ["10.20.30.40"]
    assert found(IP_ADDRESS, "version 300.1.1.1") == []
    assert found(DOB, "Date of Birth: 06/05/2000") == ["06/05/2000"]
    assert found(DOB, "dated December 10, 2025") == []  # ordinary dates are not PII


def test_cin_and_registration_numbers():
    assert found(CIN, "CIN: U28129PN1979PLC141032") == ["U28129PN1979PLC141032"]
    assert found(REG_NUMBER, "Registration number: 141032") == ["141032"]
    assert found(REG_NUMBER, "Peer review number: 014680") == ["014680"]


def test_org_suffix_and_generic_phrases():
    names = [s.text for s in find_orgs("appointed MUFG Intime India Private Limited as registrar")]
    assert names == ["MUFG Intime India Private Limited"]
    assert find_orgs("BSE Limited and National Stock Exchange of India Limited") == []  # kept by policy
    assert find_orgs("money in the Refund Bank", lower_words={"refund"}) == []  # generic phrase


def test_addresses_in_prose_and_lines():
    text = ("having its Registered Office at 11/3, Village Birdewadi, Chakan Taluka - Khed, Pune – 410 501, "
            "Maharashtra, India and its Corporate Office at 201, Tower 2, Baner, Pune – 411 045, Maharashtra, India")
    spans = [s.text for s in find_addresses(text)]
    assert spans == ["11/3, Village Birdewadi, Chakan Taluka - Khed, Pune – 410 501", "201, Tower 2, Baner, Pune – 411 045"]
    assert find_addresses("CORPORATE IDENTITY NUMBER: U28129PN1979PLC141032") == []
