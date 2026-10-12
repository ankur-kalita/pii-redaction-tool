"""Consistent, deterministic, realistic fake values.

Consistency is the core requirement: the same real entity must become the same
fake entity everywhere in the document, so a model trained on the output still
learns that "the person on the cover" and "the person in clause 40" are one.

* Names are mapped token by token (Kushal -> Arjun, Hegde -> Mehta). Every
  variant of a name ("Kushal Subbayya Hegde", "KUSHAL HEGDE", "Hegde") then
  maps consistently, and family relations survive ("Rajesh Kushal Hegde" is
  still recognisably the son of "Kushal ... Hegde").
* Company names keep their generic words and legal suffix; only the
  distinctive part changes ("KSH International Limited" -> "Torvan
  International Limited"), and the same distinctive word is reused inside
  emails and websites (kshinternational.com -> torvaninternational.com).
* Numbers keep their format (separators, length, prefixes like +91, the PAN
  holder-type letter, CIN structure) so the document still reads naturally.
* Everything is derived from a keyed hash of the real value, so a run is
  reproducible, and two different real values never share a fake.
"""
from __future__ import annotations

import hashlib
import hmac
import random
import re
from datetime import datetime, timedelta

from faker.providers.address.en_IN import Provider as AddressProvider
from faker.providers.person.en_IN import Provider as PersonProvider

from .detectors.entities import GENERIC_ORG_WORDS, KEEP_DOMAINS, distinctive_tokens
from .detectors.patterns import digits, verhoeff_check_digit

FIRST_NAMES = sorted({n for n in PersonProvider.first_names_male + PersonProvider.first_names_female if n.isalpha()})
LAST_NAMES = sorted({n for n in PersonProvider.last_names if n.isalpha()})
CITIES = sorted({c for c in AddressProvider.cities if c.isalpha()})
STREET_SUFFIXES = ["Road", "Marg", "Nagar", "Lane", "Street", "Chowk", "Colony"]
SYLLABLES = ["ka", "ro", "vel", "tan", "mi", "sor", "da", "len", "vi", "qua", "ra", "zen", "lo", "nex", "ta", "bri", "cor", "ven", "sa", "lu"]
PUBLIC_EMAIL_DOMAINS = {"gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "rediffmail.com", "icloud.com"}
STATE_CODES = ["MH", "KA", "TN", "GJ", "DL", "UP", "WB", "TG", "RJ", "HR", "KL", "MP"]


def match_case(fake: str, real: str) -> str:
    if real.isupper() and len(real) > 1:
        return fake.upper()
    if real.islower():
        return fake.lower()
    if real[:1].isupper():
        return fake[:1].upper() + fake[1:]
    return fake


class Pseudonymizer:
    def __init__(self, secret: str = "evaratus-redaction", reserved: set[str] = frozenset()):
        self._key = secret.encode()
        self._maps: dict[str, dict[str, str]] = {}
        self._used: dict[str, set[str]] = {}
        # Real tokens that a fake must never equal (otherwise a fake could
        # accidentally reproduce a different real person's name).
        self._reserved = {r.lower() for r in reserved}
        self.person_roles: dict[str, str] = {}  # token -> "first" | "last"

    # --- infrastructure ---------------------------------------------------
    def _rng(self, kind: str, value: str, attempt: int = 0) -> random.Random:
        digest = hmac.new(self._key, f"{kind}|{value}|{attempt}".encode(), hashlib.sha256).digest()
        return random.Random(int.from_bytes(digest[:8], "big"))

    def _consistent(self, kind: str, key: str, make) -> str:
        """Return the fake for ``key``, creating it once with ``make(rng)``.
        Retries with a new seed until the fake is unique within its kind and
        does not collide with a real value."""
        table = self._maps.setdefault(kind, {})
        if key in table:
            return table[key]
        used = self._used.setdefault(kind, set())
        for attempt in range(100):
            fake = make(self._rng(kind, key, attempt))
            if fake.lower() not in used and fake.lower() not in self._reserved and fake.lower() != key.lower():
                break
        table[key] = fake
        used.add(fake.lower())
        return fake

    def mapping(self) -> dict[str, dict[str, str]]:
        return self._maps

    # --- entry point ------------------------------------------------------
    def fake(self, label: str, real: str) -> str:
        handler = {
            "PERSON": self.person,
            "ORGANIZATION": self.organization,
            "EMAIL": self.email,
            "URL": self.url,
            "PHONE": self.phone,
            "ADDRESS": self.address,
            "PAN": self.pan,
            "AADHAAR": self.aadhaar,
            "CIN": self.cin,
            "GSTIN": self.gstin,
            "SSN": self.ssn,
            "CREDIT_CARD": self.credit_card,
            "IP_ADDRESS": self.ip_address,
            "DATE_OF_BIRTH": self.date_of_birth,
            "REGISTRATION_ID": self.registration_id,
        }[label]
        return handler(real)

    # --- names ------------------------------------------------------------
    def name_token(self, token: str) -> str:
        core = token.strip(".")
        if len(core) == 1:  # an initial: map letter to letter
            fake = self._consistent("initial", core.upper(), lambda r: r.choice("ABCDEGHJKLMNPRSTV"))
            return match_case(fake, core) + ("." if token.endswith(".") else "")
        role = self.person_roles.get(core.lower(), "first")
        pool = LAST_NAMES if role == "last" else FIRST_NAMES
        fake = self._consistent("name", core.lower(), lambda r: r.choice(pool))
        return match_case(fake, core)

    def person(self, real: str) -> str:
        return re.sub(r"[A-Za-z][A-Za-z'\-]*\.?", lambda m: self.name_token(m.group(0)), real)

    # --- organisations ----------------------------------------------------
    def brand(self, token: str) -> str:
        """Fake for the distinctive word of a company name. One map for all
        casings, so "KSH", "Ksh" and "ksh" (in an email) agree. The style
        (acronym vs word) is fixed by the first, normally-cased sighting."""
        def make(r: random.Random) -> str:
            if token.isupper() and len(token) <= 6:  # acronym: KSH -> RVT
                return "".join(r.choice("ABCDEFGHKLMNPRSTVWZ") for _ in token)
            return "".join(r.choice(SYLLABLES) for _ in range(2 if len(token) < 7 else 3)).capitalize()
        return match_case(self._consistent("brand", token.lower(), make), token)

    def organization(self, real: str) -> str:
        distinct = {t.lower() for t in distinctive_tokens(real)}
        # A company name can contain a person's name ("Kushal Motors"); those
        # tokens go through the name map so they stay linked to the person.
        def repl(m: re.Match) -> str:
            tok = m.group(0)
            low = tok.lower()
            if low not in distinct or low in GENERIC_ORG_WORDS:
                return tok
            if low in self.person_roles:
                return self.name_token(tok)
            return self.brand(tok)
        return re.sub(r"[A-Za-z][A-Za-z0-9'\-]*", repl, real)

    # --- emails & websites -------------------------------------------------
    def _domain(self, domain: str) -> str:
        if domain.lower() in PUBLIC_EMAIL_DOMAINS or KEEP_DOMAINS.search(domain):
            return domain
        labels = domain.split(".")
        tld_start = len(labels) - (2 if len(labels) > 2 and labels[-2] in {"co", "gov", "org", "ac", "net"} else 1)

        def fake_label(label: str) -> str:
            low = label.lower()
            # Replace every known distinctive word inside the label
            # ("kshinternational" -> "rvtinternational"), else invent one.
            new = self._replace_known(low)
            if new != low:
                return new
            return self._consistent("domain", low, lambda r: "".join(r.choice(SYLLABLES) for _ in range(3)))

        new = [fake_label(l) if i < tld_start and l.lower() not in {"www", "in", "mail", "mb"} else l for i, l in enumerate(labels)]
        return ".".join(new)

    def _replace_known(self, word: str) -> str:
        """Replace every known company word inside a lower-case string
        ("kshinternational" -> "rvtinternational")."""
        brands = self._maps.get("brand", {})
        for k in sorted((k for k in brands if len(k) >= 3 and k in word), key=len, reverse=True):
            word = word.replace(k, brands[k].lower())
        return word

    def _local_part(self, local: str) -> str:
        def repl(m: re.Match) -> str:
            tok = m.group(0)
            low = tok.lower()
            if low in self.person_roles:
                return self.name_token(tok)
            replaced = self._replace_known(low)
            # role words like "investor", "cs.connect" are not identifying
            return match_case(replaced, tok) if replaced != low else tok
        return re.sub(r"[A-Za-z]+", repl, local)

    def email(self, real: str) -> str:
        local, _, domain = real.partition("@")
        return f"{self._local_part(local)}@{self._domain(domain)}"

    def url(self, real: str) -> str:
        m = re.match(r"(?i)(https?://)?((?:[\w-]+\.\s?)+[a-z]{2,})(.*)", real)
        if not m:
            return real
        scheme, host, path = m.group(1) or "", m.group(2), m.group(3)
        spaced = host.replace(" ", "")
        if KEEP_DOMAINS.search(spaced):
            return real
        return scheme + self._domain(spaced) + path

    # --- numbers & ids ------------------------------------------------------
    def _digits_like(self, kind: str, real: str, keep_prefix: int = 0, first_nonzero: bool = True) -> str:
        """Replace digits, keeping every separator and the first ``keep_prefix`` digits."""
        def make(r: random.Random) -> str:
            out, seen = [], 0
            for ch in real:
                if ch.isdigit():
                    if seen < keep_prefix:
                        out.append(ch)
                    elif seen == keep_prefix and first_nonzero:
                        out.append(r.choice("123456789"))
                    else:
                        out.append(r.choice("0123456789"))
                    seen += 1
                else:
                    out.append(ch)
            return "".join(out)
        return self._consistent(kind, digits(real) or real, make)

    def phone(self, real: str) -> str:
        """Keep the +91 country code, a leading 0 (STD prefix) and every
        separator. The fake digits are tied to the real digits, so the same
        number written differently ("+91 22 4009 4400" / "+91 22 40094400")
        gets the same fake, rendered in each occurrence's own format."""
        has_cc = bool(re.match(r"\s*\+\s?91", real))
        real_digits = digits(real)
        national = real_digits[2:] if has_cc else real_digits

        def make(r: random.Random) -> str:
            if national.startswith("0"):
                first = "0"
            elif len(national) == 10 and national[0] in "6789":
                first = r.choice("6789")  # stays a plausible mobile number
            else:
                first = r.choice("123456789")
            return first + "".join(r.choice("0123456789") for _ in national[1:])

        fake_national = self._consistent("phone", national, make)
        it = iter(("91" if has_cc else "") + fake_national)
        return "".join(next(it) if c.isdigit() else c for c in real)

    def pan(self, real: str) -> str:
        def make(r):
            return "".join(r.choice("ABCDEFGHJKLMNPRSTUVWXYZ") for _ in range(3)) + real[3] + r.choice("ABCDEFGHKLMNPRS") + f"{r.randrange(10000):04d}" + r.choice("ABCDEFGHKLMNPRS")
        return self._consistent("pan", real, make)

    def aadhaar(self, real: str) -> str:
        def make(r):
            body = r.choice("23456789") + "".join(r.choice("0123456789") for _ in range(10))
            number = body + verhoeff_check_digit(body)
            it = iter(number)
            return "".join(next(it) if c.isdigit() else c for c in real)
        return self._consistent("aadhaar", digits(real), make)

    def registration_id(self, real: str) -> str:
        def make(r):
            return "".join(r.choice("0123456789") if c.isdigit() else r.choice("ABCDEFGHKLMNPRSTVWZ") if c.isalpha() and not real.startswith("IN") else c for c in real)
        return self._consistent("regid", real, make)

    def cin(self, real: str) -> str:
        # L/U + industry(5) + state(2) + year(4) + ownership type(3) + registration number(6).
        # The registration number is mapped with the same table as a standalone
        # "Registration number: 141032", so the two stay consistent.
        def make(r):
            reg = self.registration_id(real[-6:])
            return real[0] + f"{r.randrange(10000, 99999)}" + r.choice(STATE_CODES) + str(r.randrange(1950, 2020)) + real[12:15] + reg
        return self._consistent("cin", real, make)

    def gstin(self, real: str) -> str:
        return self._consistent("gstin", real, lambda r: f"{r.randrange(1, 37):02d}" + self.pan("ABCPX0000X")[:5] + f"{r.randrange(10000):04d}" + r.choice("ABCDEFGH") + "1Z" + r.choice("0123456789"))

    def ssn(self, real: str) -> str:
        return self._consistent("ssn", real, lambda r: f"{r.randrange(100, 665):03d}-{r.randrange(10, 99):02d}-{r.randrange(1000, 9999):04d}")

    def credit_card(self, real: str) -> str:
        def make(r):
            ds = [r.choice("0123456789") for _ in range(len(digits(real)) - 1)]
            for check in "0123456789":
                from .detectors.patterns import luhn_valid
                if luhn_valid("".join(ds) + check):
                    break
            it = iter(ds + [check])
            return "".join(next(it) if c.isdigit() else c for c in real)
        return self._consistent("card", digits(real), make)

    def ip_address(self, real: str) -> str:
        if ":" in real:
            return self._consistent("ip", real, lambda r: "2001:db8::" + format(r.randrange(1, 65535), "x"))
        # RFC 5737 documentation ranges: guaranteed not to be a real host.
        return self._consistent("ip", real, lambda r: f"{r.choice(['192.0.2', '198.51.100', '203.0.113'])}.{r.randrange(1, 255)}")

    def date_of_birth(self, real: str) -> str:
        for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y", "%B %d %Y"):
            try:
                d = datetime.strptime(real.replace("th ", " ").replace("st ", " ").replace("nd ", " ").replace("rd ", " "), fmt)
            except ValueError:
                continue
            return self._consistent("dob", real, lambda r: (d + timedelta(days=r.choice([-1, 1]) * r.randrange(60, 900))).strftime(fmt))
        return self._digits_like("dob", real)

    # --- addresses ----------------------------------------------------------
    def address(self, real: str) -> str:
        def make(r: random.Random) -> str:
            pin = re.search(r"[1-9]\d{2}\s?\d{3}\s*$", real)
            parts = [f"{r.randrange(1, 400)}", f"{r.choice(LAST_NAMES)} {r.choice(STREET_SUFFIXES)}"]
            if len(real) > 40:
                parts.insert(1, f"{r.choice(['Floor', 'Wing', 'Block', 'Tower'])} {r.randrange(1, 12)}")
            text = ", ".join(parts)
            if pin:
                sep = "–" if "–" in real else "-" if "-" in real[-12:] else ""
                code = f"{r.randrange(1, 9)}{r.randrange(10, 99)}" + (" " if " " in pin.group(0).strip() else "") + f"{r.randrange(0, 999):03d}"
                text += f", {r.choice(CITIES)} {sep} {code}".replace("  ", " ")
            return text
        return self._consistent("address", " ".join(real.split()).lower(), make)
