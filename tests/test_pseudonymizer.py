from redactor.detectors.patterns import luhn_valid, verhoeff_valid
from redactor.pseudonymizer import Pseudonymizer


def make():
    p = Pseudonymizer("test", reserved={"kushal", "hegde", "rajesh"})
    p.person_roles = {"kushal": "first", "rajesh": "first", "hegde": "last"}
    return p


def test_names_are_consistent_across_variants_and_case():
    p = make()
    full = p.person("Kushal Subbayya Hegde")
    son = p.person("Rajesh Kushal Hegde")
    caps = p.person("KUSHAL SUBBAYYA HEGDE")
    assert caps == full.upper()
    assert son.split()[1:] == [full.split()[0], full.split()[2]]  # father's name carried by the son
    assert "Kushal" not in full and "Hegde" not in full


def test_fake_never_equals_a_real_name():
    p = make()
    assert p.person("Hegde").lower() not in {"kushal", "hegde", "rajesh"}


def test_company_keeps_generic_words_and_matches_its_email_and_website():
    p = make()
    org = p.organization("KSH International Limited")
    fake_brand = org.split()[0]
    assert org.endswith("International Limited") and fake_brand != "KSH"
    assert p.email("cs.connect@kshinternational.com") == f"cs.connect@{fake_brand.lower()}international.com"
    assert p.url("www.kshinternational.com") == f"www.{fake_brand.lower()}international.com"


def test_regulator_domains_are_kept():
    assert make().url("www.sebi.gov.in") == "www.sebi.gov.in"


def test_phone_same_number_same_fake_in_each_format():
    p = make()
    a = p.phone("+91 22 4009 4400")
    b = p.phone("+91 22 40094400")
    assert a.replace(" ", "") == b.replace(" ", "")
    assert a.startswith("+91 ") and a != "+91 22 4009 4400"
    assert p.phone("022-68052182").startswith("0")


def test_checksummed_fakes_stay_valid():
    p = make()
    assert verhoeff_valid(p.aadhaar("2943 6593 3461"))
    assert luhn_valid(p.credit_card("4111 1111 1111 1111"))


def test_deterministic_across_runs():
    assert make().person("Kushal Hegde") == make().person("Kushal Hegde")
