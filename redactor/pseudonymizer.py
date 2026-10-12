"""Consistent, deterministic, realistic fake values.

The same real value always gets the same fake, derived from a keyed hash:
* names are mapped word by word, so every variant of a name and family
  links stay consistent ("Rajesh Kushal Hegde" keeps his father's fake names);
* companies keep their generic words and legal suffix, and the fake brand is
  reused in their emails and websites;
* numbers keep their format (separators, country code, checksums).
"""

from __future__ import annotations

import hashlib
import hmac
import random
import re
from datetime import datetime, timedelta

from faker.providers.address.en_IN import Provider as AddressProvider
from faker.providers.person.en_IN import Provider as PersonProvider

from .detectors.lexicon import GENERIC_ORG_WORDS, ROLE_WORDS, public_host
from .detectors.organizations import distinctive_tokens
from .detectors.patterns import digits, luhn_valid, verhoeff_check_digit

FIRST_NAMES = sorted({n for n in PersonProvider.first_names_male + PersonProvider.first_names_female if n.isalpha()})
LAST_NAMES = sorted({n for n in PersonProvider.last_names if n.isalpha()})
CITIES = sorted({c for c in AddressProvider.cities if c.isalpha()})
STREET_SUFFIXES = ["Road", "Marg", "Nagar", "Lane", "Street", "Chowk", "Colony"]
# Order matters: fake brand names are drawn from this list.
SYLLABLES = "ka ro vel tan mi sor da len vi qua ra zen lo nex ta bri cor ven sa lu".split()
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


def _country_code(number: str) -> str:
    """Dialling-code length by ITU zone: +1/+7, three digits for the blocks
    below, otherwise two (+44, +91)."""
    if number[:1] in "17":
        return number[:1]
    if re.match(r"2[1-9]|3[578]|42|5[09]|6[7-9]|8[058]|9[679]", number):
        return number[:3]
    return number[:2]


DATE_FORMATS = (
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%d/%m/%y",
    "%B %d, %Y",
    "%b %d, %Y",
    "%d %B %Y",
    "%d %b %Y",
    "%B %d %Y",
)


def _parse_date(text: str) -> tuple[datetime, str] | None:
    plain = re.sub(r"(st|nd|rd|th) ", " ", text)
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(plain, fmt), fmt
        except ValueError:
            continue
    return None


class Pseudonymizer:
    def __init__(self, secret: str, reserved: set[str] = frozenset()):
        self._key = secret.encode()
        self._maps: dict[str, dict[str, str]] = {}
        self._used: dict[str, set[str]] = {}
        self._reserved = {r.lower() for r in reserved}  # real words a fake must never equal
        self.person_roles: dict[str, str] = {}  # token -> "first" | "last"
        self.common_words: set[str] = set()  # words the document uses in lower case

    # --- infrastructure ---------------------------------------------------
    def _rng(self, kind: str, value: str, attempt: int = 0) -> random.Random:
        digest = hmac.new(self._key, f"{kind}|{value}|{attempt}".encode(), hashlib.sha256).digest()
        return random.Random(int.from_bytes(digest[:8], "big"))

    def _consistent(self, kind: str, key: str, make) -> str:
        """The fake for `key`, made once by `make(rng)`; retried until it is
        unique within its kind and equals no real value."""
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
            "LOCATION": self.location,
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
        return re.sub(r"[^\W\d_][\w'’\-]*\.?", lambda m: self.name_token(m.group(0)), real)

    # --- organisations ----------------------------------------------------
    def brand(self, token: str) -> str:
        """Fake for a company's distinctive word, shared by all casings ("KSH",
        "ksh" in an email). A word built on a known brand keeps the link:
        "CareEdge" -> "PNVKEdge"."""

        def make(r: random.Random) -> str:
            known = self._maps.get("brand", {})
            for k in sorted(known, key=len, reverse=True):
                rest = token[len(k) :]
                if len(k) >= 3 and token.lower().startswith(k) and rest[:1].isupper():
                    return match_case(known[k], token[: len(k)]) + rest
            if token.isupper() and len(token) <= 6:  # acronym, sharing no letter position: KSH -> LNK
                return "".join(r.choice([c for c in "ABCDEFGHKLMNPRSTVWZ" if c != real_c]) for real_c in token)
            return "".join(r.choice(SYLLABLES) for _ in range(2 if len(token) < 7 else 3)).capitalize()

        return match_case(self._consistent("brand", token.lower(), make), token)

    def organization(self, real: str) -> str:
        distinct = {t.lower() for t in distinctive_tokens(real)}

        def repl(m: re.Match) -> str:
            tok = m.group(0)
            low = tok.lower()
            if low not in distinct or low in GENERIC_ORG_WORDS:
                return tok
            if low in self.person_roles:  # "Kushal Motors" stays linked to Kushal
                return self.name_token(tok)
            return self.brand(tok)

        return re.sub(r"[A-Za-z][A-Za-z0-9'\-]*", repl, real)

    # --- emails & websites -------------------------------------------------
    def _domain(self, domain: str) -> str:
        if domain.lower() in PUBLIC_EMAIL_DOMAINS or public_host(domain):
            return domain
        labels = domain.split(".")
        tld_start = len(labels) - (2 if len(labels) > 2 and labels[-2] in {"co", "gov", "org", "ac", "net"} else 1)

        def fake_label(label: str) -> str:
            low = label.lower()
            new = self._replace_known(low)
            if new != low:
                return new
            return self._consistent("domain", low, lambda r: "".join(r.choice(SYLLABLES) for _ in range(3)))

        kept = {"www", "in", "mail", "mb"}
        return ".".join(
            fake_label(part) if i < tld_start and part.lower() not in kept else part for i, part in enumerate(labels)
        )

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
            if replaced != low:
                return match_case(replaced, tok)
            # role and ordinary words are kept; anything else is masked as a name
            if len(low) <= 2 or low in ROLE_WORDS or low in self.common_words:
                return tok
            return self.name_token(tok)

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
        if public_host(spaced):
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
        """Keeps the country code, a leading 0 and the separators. The fake is
        keyed on the digits, so "+91 22 4009 4400" and "+91 22 40094400" agree."""
        real_digits = digits(real)
        cc = _country_code(real_digits) if real.lstrip().startswith("+") else ""
        national = real_digits[len(cc) :]

        def make(r: random.Random) -> str:
            if national.startswith("0"):
                first = "0"
            elif len(national) == 10 and national[0] in "6789":
                first = r.choice("6789")  # stays a plausible mobile number
            else:
                first = r.choice("123456789")
            return first + "".join(r.choice("0123456789") for _ in national[1:])

        fake_national = self._consistent("phone", national, make)
        it = iter(cc + fake_national)
        return "".join(next(it) if c.isdigit() else c for c in real)

    def pan(self, real: str) -> str:
        def make(r):
            return (
                "".join(r.choice("ABCDEFGHJKLMNPRSTUVWXYZ") for _ in range(3))
                + real[3]
                + r.choice("ABCDEFGHKLMNPRS")
                + f"{r.randrange(10000):04d}"
                + r.choice("ABCDEFGHKLMNPRS")
            )

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
            def fake_char(c: str) -> str:
                if c.isdigit():
                    return r.choice("0123456789")
                if c.isalpha() and not real.startswith("IN"):  # keep SEBI's "INR"/"INM" prefix
                    return r.choice("ABCDEFGHKLMNPRSTVWZ")
                return c

            return "".join(fake_char(c) for c in real)

        return self._consistent("regid", real, make)

    def cin(self, real: str) -> str:
        # L/U, industry(5), state(2), year(4), type(3), registration number(6);
        # the registration number shares its fake with a standalone mention
        def make(r):
            reg = self.registration_id(real[-6:])
            industry, state, year = r.randrange(10000, 99999), r.choice(STATE_CODES), r.randrange(1950, 2020)
            return f"{real[0]}{industry}{state}{year}{real[12:15]}{reg}"

        return self._consistent("cin", real, make)

    def gstin(self, real: str) -> str:
        def make(r):
            state, pan = f"{r.randrange(1, 37):02d}", self.pan("ABCPX0000X")[:5]
            return f"{state}{pan}{r.randrange(10000):04d}{r.choice('ABCDEFGH')}1Z{r.choice('0123456789')}"

        return self._consistent("gstin", real, make)

    def ssn(self, real: str) -> str:
        return self._consistent(
            "ssn",
            real,
            lambda r: f"{r.randrange(100, 665):03d}-{r.randrange(10, 99):02d}-{r.randrange(1000, 9999):04d}",
        )

    def credit_card(self, real: str) -> str:
        def make(r):
            ds = [r.choice("0123456789") for _ in range(len(digits(real)) - 1)]
            check = next(c for c in "0123456789" if luhn_valid("".join(ds) + c))
            it = iter(ds + [check])
            return "".join(next(it) if c.isdigit() else c for c in real)

        return self._consistent("card", digits(real), make)

    def ip_address(self, real: str) -> str:
        if ":" in real:
            return self._consistent("ip", real, lambda r: "2001:db8::" + format(r.randrange(1, 65535), "x"))
        # RFC 5737 documentation ranges: never a real host
        return self._consistent(
            "ip", real, lambda r: f"{r.choice(['192.0.2', '198.51.100', '203.0.113'])}.{r.randrange(1, 255)}"
        )

    def date_of_birth(self, real: str) -> str:
        parsed = _parse_date(real)
        if not parsed:
            return self._digits_like("dob", real)
        day, fmt = parsed
        return self._consistent(
            "dob", real, lambda r: (day + timedelta(days=r.choice([-1, 1]) * r.randrange(60, 900))).strftime(fmt)
        )

    # --- addresses ----------------------------------------------------------
    def location(self, real: str) -> str:
        return match_case(self._consistent("location", real.lower(), lambda r: r.choice(CITIES)), real)

    def address(self, real: str) -> str:
        def make(r: random.Random) -> str:
            pin = re.search(r"[1-9]\d{2}\s?\d{3}\s*$", real)
            parts = [f"{r.randrange(1, 400)}", f"{r.choice(LAST_NAMES)} {r.choice(STREET_SUFFIXES)}"]
            if len(real) > 40:
                parts.insert(1, f"{r.choice(['Floor', 'Wing', 'Block', 'Tower'])} {r.randrange(1, 12)}")
            text = ", ".join(parts)
            if pin:
                sep = "–" if "–" in real else "-" if "-" in real[-12:] else ""
                space = " " if " " in pin.group(0).strip() else ""
                code = f"{r.randrange(1, 9)}{r.randrange(10, 99)}{space}{r.randrange(0, 999):03d}"
                text += f", {r.choice(CITIES)} {sep} {code}".replace("  ", " ")
            return text

        return self._consistent("address", " ".join(real.split()).lower(), make)
