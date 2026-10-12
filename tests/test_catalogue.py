"""Catalogue rules for company names that are also English words ("CARE"),
defined-term nicknames, and addresses split over several lines."""
import spacy

from redactor.catalogue import CatalogueDetector, discover
from redactor.detectors.base import Span
from redactor.detectors.entities import address_line, continues_address, find_orgs
from redactor.pseudonymizer import Pseudonymizer

NLP = spacy.blank("en")  # no NER: these rules must work from text alone

DOC = [
    "The report was prepared by CARE Analytics and Advisory Private Limited (“CareEdge Research”).",
    "Our credit ratings are from CARE Ratings Limited.",
    "The CARE Report is the source of industry data.",
    "Handle with care and due diligence. Care is advised.",
    "WE TAKE CARE OF OUR EMPLOYEES",
    "‘CARE A-’",
    "The secretary is Kanj and Co LLP (“Practicing Company Secretary”).",
]


def orgs_in(text, doc=DOC):
    return [s.text for s in CatalogueDetector(discover(doc, NLP)).detect(text) if s.label == "ORGANIZATION"]


def test_all_caps_brand_that_is_an_english_word_is_matched():
    assert orgs_in("derived from the CARE Report.") == ["CARE"]
    assert orgs_in("‘CARE A-’") == ["CARE"]  # short all-caps cell (a rating)


def test_ordinary_word_care_is_never_matched():
    assert orgs_in("Handle with care. Care is advised.") == []
    assert orgs_in("WE TAKE CARE OF OUR EMPLOYEES") == []  # all-caps sentence: ambiguous, kept


def test_acronym_rule_needs_all_caps_evidence_inside_a_company_name():
    doc = ["Prepared by Care Analytics Private Limited.", "The CARE Report."]
    assert orgs_in("The CARE Report.", doc) == []


def test_defined_term_nickname_that_reuses_the_brand_is_an_alias():
    assert "CareEdge Research" in orgs_in("Industry Data Provider/ CareEdge Research")
    assert orgs_in("as certified by the Practicing Company Secretary") == []  # role, not a nickname


def test_nickname_fake_is_linked_to_the_company_fake():
    p = Pseudonymizer("test")
    company = p.organization("CARE Analytics and Advisory Private Limited")
    nickname = p.organization("CareEdge Research")
    assert nickname.split()[0].lower().startswith(company.split()[0].lower())
    assert "care" not in nickname.lower()


def test_bank_of_place_is_a_bank_name_but_regulators_are_kept():
    assert [s.text for s in find_orgs("State Bank of India, Industrial Finance Branch", {"state"})] == ["State Bank of India"]
    assert find_orgs("regulated by the Reserve Bank of India", {"reserve"}) == []
    assert find_orgs("Export-Import Bank of India", {"export"}) == []


def test_address_split_over_lines():
    assert continues_address("IndusInd Bank Limited 2401 Gen Thimmayya Road, Cantonment", "Pune – 411 001")
    assert continues_address("Tara Chambers, Mumbai-Pune Road, Wakdewadi", "Pune – 411 003")
    assert not continues_address("Telephone: +91 20 2640 3100", "Pune – 411 001")
    assert not continues_address("Registered Office", "Pune – 411 001")
    assert not continues_address("2401 Gen Thimmayya Road", "Pune is a city with PIN 411 001")


def test_address_line_skips_company_and_its_legal_suffix():
    line = "IndusInd Bank Limited 2401 Gen Thimmayya Road, Cantonment"
    org = Span(0, 13, "ORGANIZATION", "IndusInd Bank")
    assert [a.text for a in address_line(line, [org])] == ["2401 Gen Thimmayya Road, Cantonment"]
