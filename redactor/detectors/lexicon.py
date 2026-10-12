"""Shared vocabulary and policy lists."""

from __future__ import annotations

import re

# Words that never belong to a person's name ("Supa Facility", "Rajesh Branch").
NON_NAME_WORDS = set(
    """
    ab account accountants act advanced analytics annexure area associates auditor auditors bank
    bid bill board branch building cap capital cell center centre chairman chartered chemistry
    chowk circular clause colony committee company complex corporate department director
    district dollars e-mail east ebit ebitda email equity estate facility finance fiscal fiscals
    floor foundation fund funds group highway hospital house huf id ind india industrial
    investor investors lane leasing limited llc llp ltd management marg mission north
    offer office officer park partner pat peth pin plant plot portal portion price private
    registered regulations road rules schedule scheme secretary section sector securities share
    shares slip society south states station street taluka tower transformation trust unit
    united urban village warehouse west wing
    """.split()
)

# Generic words in company names: kept, only the distinctive part is replaced.
GENERIC_ORG_WORDS = set(
    """
    & 1 2 3 a academy accountants advisors advisory agency agro and asset assets associates auto
    automotive b bank broking bureau c capital center centre chambers chartered chemicals co
    college company components consultants corporation council department division electrical
    electricals electronics energy engineering engineers enterprises equities estates exports
    family finance financial foods formerly fund funds general global group holdings i ii iii
    imports india indian industrial industries infra infrastructure institute institution
    institutional insurance international intime investment investments iv ix laboratories
    laboratory law legal life limited llp logistics ltd management manufacturing market markets
    metals motors of park partners pharma plastics power private products pvt realty research
    school securities services solutions steel systems technologies technology textiles the
    trading trust university v venture ventures vi vii viii wealth x
    """.split()
)

# Legal-form words: part of a company name, never its distinctive part.
LEGAL_WORDS = {"llc", "llp", "plc", "ltd", "inc", "pvt", "huf", "gmbh"}

# Words the company-name rules can sweep up in front of a name.
ORG_LEADING_JUNK = set(
    """
    & a agreement all also an and any are as at auditor auditors banker bankers being between
    book by company contact counsel dated each email entities entity for from group in is issuer
    its lead legal manager managers member members name namely note of offer on our person
    promoter promoters pursuant refer registrar running said see selling shareholder
    shareholders sponsor statutory subsidiaries subsidiary such telephone that the their this to
    under was website were which with
    """.split()
)

# Policy: public institutions are kept. They identify no individual, and the
# structure of every prospectus depends on them.
KEEP_ORG_RE = re.compile(
    "|".join(
        [
            r"securities and exchange board",
            r"\bsebi\b",
            r"\bbse\b",
            r"national stock exchange",
            r"reserve bank",
            r"\brbi\b",
            r"national securities depository",
            r"\bnsdl\b",
            r"central depository services",
            r"\bcdsl\b",
            r"registrar of companies",
            r"government of",
            r"ministry of",
            r"income tax",
            r"unique identification authority",
            r"\b(?:bombay|metropolitan|calcutta) stock exchange",
            r"^(?:the\s+)?stock exchanges?(?:\s+limited)?$",
            r"national company law",
            r"\bnclt\b",
            r"\bicai\b",
            r"institute of chartered accountants",
            r"insurance regulatory",
            r"\birdai\b",
            r"pension fund regulatory",
            r"\bmca\b",
            r"high court",
            r"supreme court",
            r"life insurance companies",
            r"provident fund",
            r"national payments corporation",
            r"solar energy corporation",
            r"export-import bank",
        ]
    ),
    re.IGNORECASE,
)

# Public-sector hosts, matched at the end of the hostname only.
PUBLIC_HOST_RE = re.compile(
    r"(?:^|\.)(?:bseindia\.com|nseindia\.com|rbi\.org\.in|nsdl\.co\.in|cdslindia\.com|npci\.org\.in|"
    r"gov\.in|gov|gov\.[a-z]{2}|mil|int)$",
    re.IGNORECASE,
)


def public_host(address: str) -> bool:
    """True for a URL, domain or email address hosted by a public body. Only
    the hostname counts: "x.com/r?u=sebi.gov.in" is not public."""
    host = address.replace(" ", "").split("@")[-1]
    host = re.sub(r"(?i)^[a-z]+://", "", host)
    host = re.split(r"[/?#:]", host)[0].rstrip(".")
    return bool(PUBLIC_HOST_RE.search(host))


# Mailbox names that describe a role, not a person.
ROLE_WORDS = set(
    """
    accounts admin billing care careers complaints compliance connect contact customercare
    customerservice desk enquiries enquiry finance grievance grievances hello help helpdesk info
    investor investors ipo legal mail media noreply office privacy reply sales secretarial
    security service services support team
    """.split()
)

# Big cities and states identify no one; rare localities do.
MAJOR_PLACES = set(
    """
    ahmedabad bangalore bengal bengaluru chennai delhi goa gujarat gurugram haryana hyderabad
    india karnataka kerala kolkata maharashtra mumbai nadu new noida pradesh pune rajasthan
    tamil telangana uttar west
    """.split()
)

PLACE_SUFFIXES = ("nagar", "wadi", "pur", "abad", "gaon", "pada", "khed", "marg")

WORD_ENDINGS = ("s", "es", "d", "ed", "ing", "ings", "ly", "er", "ion", "ions", "ation", "ment", "ments", "al")


def is_caps(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return bool(letters) and sum(c.isupper() for c in letters) / len(letters) > 0.8


def english_word(word: str, lower_words: set[str]) -> bool:
    """True if the document uses the word, or a form of it, in lower case
    ("Integrated" -> "integration"), so it is a common word, not a name."""
    word = word.lower()
    if "-" in word:
        return all(english_word(part, lower_words) for part in word.split("-") if part)
    stems = {word} | {word[: -len(e)] for e in WORD_ENDINGS if word.endswith(e) and len(word) - len(e) >= 3}
    return any(stem in lower_words or any(stem + e in lower_words for e in WORD_ENDINGS) for stem in stems)


def role_mailbox(email: str) -> bool:
    """An address that names a role, not a person: "info@", "investor.grievance@"."""
    words = re.findall(r"[a-z]+", email.split("@")[0].lower())
    return bool(words) and all(w in ROLE_WORDS or len(w) <= 2 for w in words)
