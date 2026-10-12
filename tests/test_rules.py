"""Rules that keep detection general: citation names, institutions, glossary
terms, word forms and website ownership."""

import spacy

from redactor.catalogue import Catalogue, CatalogueDetector, defined_terms, discover, owned_url
from redactor.detectors.lexicon import english_word
from redactor.detectors.organizations import distinctive_tokens, find_orgs
from redactor.detectors.people import find_cited_names

NLP = spacy.blank("en")


def test_cited_names_need_a_list_or_a_citation():
    refs = "B. A. Beckwith, R. Mahaadevan, and F. Kuo, “Development of a tool,” 2006. G. Nelson, “Practical,” 2015."
    assert find_cited_names(refs) == ["B. A. Beckwith", "R. Mahaadevan", "F. Kuo", "G. Nelson"]
    assert find_cited_names("Kaur et al. proposed a layered approach") == ["Kaur"]
    assert find_cited_names("see the U.S. Code for details") == []  # same shape, no citation


def test_cited_names_are_matched_with_initials():
    cat = discover(["Refs: J. Li, X. Li and K. El Emam, “A method,” 2009."], NLP)
    spans = [s.text for s in CatalogueDetector(cat).detect("as shown by J. Li and K. El Emam")]
    assert spans == ["J. Li", "K. El Emam"]
    assert [s.text for s in CatalogueDetector(cat).detect("A Li family")] == []  # undotted "A" is an article


def test_institutions_are_organisations():
    words = {"policy", "business", "science"}
    assert [s.text for s in find_orgs("It is against Capri College policy", words)] == ["Capri College"]
    text = "Department of Computer Science JSPM’s Rajarshi Shahu College of Engineering Pune, India"
    assert [s.text for s in find_orgs(text, words)] == ["JSPM’s Rajarshi Shahu College of Engineering"]
    assert find_orgs("a Business School degree", words) == []


def test_glossary_terms_are_not_people():
    texts = ["PMAY", "Pradhan Mantri Awas Yojana", "Our scheme Integrated Power Development Scheme (IPDS) runs."]
    terms = defined_terms(texts)
    assert "pradhan mantri awas yojana" in terms
    assert "integrated power development scheme" in terms
    assert not discover(texts, NLP).people


def test_word_forms_count_as_lower_case_evidence():
    words = {"integration", "broadly", "self", "certified", "employ"}
    assert english_word("Integrated", words)
    assert english_word("Broad", words)
    assert english_word("Self-Certified", words)
    assert english_word("Employment", words)
    assert not english_word("Hegde", words)


def test_one_letter_words_are_never_distinctive():
    assert distinctive_tokens("E. Limited Protection") == ["Protection"]


def test_website_is_masked_only_when_its_owner_is():
    cat = Catalogue(brand_tokens={"ksh"}, email_domains={"hdfcbank.com"})
    assert owned_url("www.kshinternational.com", cat)
    assert owned_url("https://www.hdfcbank.com/contact", cat)
    assert not owned_url("https://www.ijert.org/", cat)
    assert not owned_url("https://github.com/zxing/zxing", cat)


def test_personal_email_is_masked_even_on_a_public_domain():
    from redactor.detectors.base import Span
    from redactor.pipeline import is_allowed

    assert not is_allowed(Span(0, 1, "EMAIL", "joe.moore@agency.gov"))
    assert is_allowed(Span(0, 1, "EMAIL", "info@agency.gov"))
    assert is_allowed(Span(0, 1, "URL", "https://www.sebi.gov.in"))


def test_possessive_names_are_matched():
    cat = Catalogue(standalone_ok={"romanova"})
    cat.add_person("Natalia Romanova")
    spans = [s.text for s in CatalogueDetector(cat).detect("Natalia Romanova's project and Romanova's team")]
    assert spans == ["Natalia Romanova", "Romanova"]


def test_website_introduced_as_someones_is_masked():
    cat = Catalogue()
    assert owned_url("https://rajeshweber.edu", cat, "You can also visit my personal website at ")
    assert owned_url("blog.amber_sasaki.org", cat, "updates are posted on her blog, ")
    assert not owned_url("https://www.ijert.org/", cat, "Published by : ")


def test_common_name_shapes_are_accepted():
    from redactor.detectors.people import plausible_person

    for name in ["Rohan Kapur", "Amit Nagar", "Neil D'Souza", "Sean O'Brien", "José Álvarez"]:
        assert plausible_person(name, set(), set()), name
    assert not plausible_person("Supa Ahilyanagar", set(), set())  # a place
    assert not plausible_person("Shivaji Nagar", {"shivaji", "nagar"}, set())  # seen in an address


def test_accented_and_apostrophe_names_are_matched_and_fully_replaced():
    from redactor.pseudonymizer import Pseudonymizer

    cat = Catalogue()
    cat.add_person("José Álvarez")
    cat.add_person("Sean O'Brien")
    found = [s.text for s in CatalogueDetector(cat).detect("José Álvarez met Sean O'Brien's team")]
    assert found == ["José Álvarez", "Sean O'Brien"]
    assert Pseudonymizer("k").person("José Álvarez").isascii()  # no stray accent
