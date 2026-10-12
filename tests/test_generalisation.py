"""Rules that make the tool work beyond Indian documents: international
phones and addresses, acronyms, public-sector sites, companies without a
legal suffix, and names revealed by email addresses."""

import pytest
import spacy

from redactor.catalogue import discover
from redactor.detectors.addresses import find_addresses
from redactor.detectors.base import Span
from redactor.detectors.organizations import find_orgs
from redactor.detectors.patterns import PHONE, PHONE_LABELLED
from redactor.pipeline import is_allowed
from redactor.pseudonymizer import Pseudonymizer

NLP = spacy.blank("en")


def phones(text):
    return [s.text for d in (PHONE, PHONE_LABELLED) for s in d.detect(text)]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("call +1-780-563-6083 today", ["+1-780-563-6083"]),
        ("UK office +44(0)115 4960914", ["+44(0)115 4960914"]),
        ("reach me at (591)341-7776", ["(591)341-7776"]),
        ("or 206.269.0743", ["206.269.0743"]),
        ("Leeds desk 0113 496 0141", ["0113 496 0141"]),
        ("Callback number: 8503911770.", ["8503911770"]),
        ("Order ORD-8430815, amount $882.72, version 9.13.73", []),
        ("8503911770 shares were allotted", []),  # a bare digit run needs a phone signal
    ],
)
def test_international_phones(text, expected):
    assert phones(text) == expected


def test_phone_fake_keeps_country_code_and_format():
    p = Pseudonymizer("t")
    fake = p.phone("+44(0)115 4960914")
    assert fake.startswith("+44(0)") and fake != "+44(0)115 4960914"
    assert p.phone("+91 22 4009 4400").replace(" ", "") == p.phone("+91 22 40094400").replace(" ", "")


@pytest.mark.parametrize(
    "text, expected",
    [
        (
            "Shipping address on file: 86570 Williams Squares, Hollandburgh, NY 30246.",
            ["86570 Williams Squares, Hollandburgh, NY 30246"],
        ),
        (
            "Shipping address on file: 9 Warren Spring, McDonaldborough, W9 0TU.",
            ["9 Warren Spring, McDonaldborough, W9 0TU"],
        ),
        ("Ticket TCK-100000 | Priority P1", []),  # a code in capitals is not "City - PIN"
    ],
)
def test_us_and_uk_addresses(text, expected):
    assert [s.text for s in find_addresses(text)] == expected


def test_acronyms_are_not_names():
    doc = ["The OMB has issued guidance and NIST agrees.", "NARA NIST NPPI", "KUSHAL HEGDE", "Kushal Hegde signed."]
    cat = discover(doc, NLP)
    assert {"omb", "nist"} <= cat.acronyms  # used in capitals inside a sentence, never "Nist"
    assert "hegde" not in cat.acronyms  # also written "Hegde": a name in capitals


def test_name_revealed_by_email_is_learned():
    doc = ["Contact Person: Sachin Gawade", "Email: sachin.gawade@bank.com", "Write to investor.care@bank.com"]
    cat = discover(doc, NLP)
    assert "Sachin Gawade" in cat.people
    assert not any("Investor" in p for p in cat.people)  # no "Investor Care" in the text


def test_unknown_email_local_part_fails_safe():
    p = Pseudonymizer("t")
    p.common_words = {"report"}
    assert not p.email("ashishmp@bank.co.in").startswith("ashishmp@")  # unknown word -> masked
    assert p.email("investor.relations@kshinternational.com").startswith("investor.")  # role word kept
    assert p.email("report.desk@x.com").startswith("report.desk@")  # ordinary word kept


def test_public_sector_sites_are_kept():
    assert is_allowed(Span(0, 1, "URL", "http://www.whitehouse.gov/omb/memoranda/m03-22.html"))
    assert is_allowed(Span(0, 1, "URL", "https://www.gov.uk/guidance"))
    assert not is_allowed(Span(0, 1, "URL", "www.kshinternational.com"))


def test_companies_without_legal_suffix():
    words = {"wants", "the", "credit", "trade", "employ"}

    def found(text):
        return [s.text for s in find_orgs(text, words)]

    assert found("Customer works at Sharp, Wood and Chang now") == ["Sharp, Wood and Chang"]
    assert found("Supplier: Lopez Group") == ["Lopez Group"]
    assert found("Supplier: Murphy and Sons") == ["Murphy and Sons"]
    assert found("the Promoter Group") == []
    assert found("Tax on Professions, Trades, Callings and Employment Act, 1975") == []  # law title


@pytest.mark.parametrize(
    "text, expected",
    [
        ("you can reach me at (92) 98804-7482 or by email", ["(92) 98804-7482"]),
        ("contact me by phone at 0127 708 552.", ["0127 708 552"]),
        ("call 011-7745-5325 today", ["011-7745-5325"]),
        ("contact the registrar for 4,50,00,000 shares in 2025", []),
    ],
)
def test_phone_after_a_phone_word(text, expected):
    from redactor.detectors.patterns import PHONE_CONTEXT

    assert [s.text for s in PHONE_CONTEXT.detect(text)] == expected


def test_street_address_without_postal_code():
    assert [s.text for s in find_addresses("I live at 211 West Oak Street and work nearby.")] == ["211 West Oak Street"]
    assert [s.text for s in find_addresses("My office is at 7131 North 67th Avenue, Apt 4.")] == [
        "7131 North 67th Avenue, Apt 4"
    ]
    assert find_addresses("We sold 211 Equity Shares on the Street.") == []


def test_bare_domains_are_websites():
    from redactor.detectors.patterns import BARE_DOMAIN

    text = "see bsuzuki.edu and blog.amber_sasaki.org/contact, mail me at a.b@yahoo.com, read issuedDocs.json"
    assert [s.text for s in BARE_DOMAIN.detect(text)] == ["bsuzuki.edu", "blog.amber_sasaki.org/contact"]
