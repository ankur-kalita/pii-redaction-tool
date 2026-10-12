# PII Redaction Tool

Replaces personally identifiable information in a `.docx` with **realistic, consistent fake values** and keeps the document's formatting. The same person or company gets the same fake everywhere, so the redacted text keeps its meaning ("the promoter on the cover is the one signing clause 40") without revealing who anyone is.

Built for the Red Herring Prospectus of an Indian IPO, and tested on six other documents (a US government guide, two research papers, a college policy, a synthetic support-ticket log).

```bash
pip install -r requirements.txt
python -m spacy download en_core_web_lg
export REDACTOR_SECRET=<any key>   # same key -> same fakes; without it a random key is used
python -m redactor "doc/Red Herring Prospectus (6).docx" -o "output/Red Herring Prospectus - redacted.docx"
pytest                              # 59 unit tests
python eval/run_all.py              # rebuild every test document and print the scores
```

The redacted prospectus is in `output/`. The evaluation report is [EVALUATION.md](EVALUATION.md).

## Approach

**Rules + spaCy NER, in two passes, with keyed deterministic fakes.** It runs offline and needs no LLM.

1. **Read the .docx at the XML level.** Body, tables, text boxes, headers, footers, footnotes, hyperlink targets and `HYPERLINK` field codes are all read. Word splits text into formatting "runs", so detection works on whole paragraphs and each replacement is mapped back onto the runs. When a fake has the same number of words as the original, each word keeps its own formatting ("Rashi **Patil**" → "Jatin **Nanda**").
2. **Structured PII uses a pattern plus a check that rejects look-alikes:**
   - email and URL;
   - phone numbers, only with a signal: a country code (`+91`, `+1`, `+44`), an area code written as one (`022-68052182`, `(591)341-7776`), or a label (`Tel:`);
   - SSN, credit card (Luhn checksum), IP address, and date of birth (only when labelled as one);
   - Indian IDs: PAN, Aadhaar (Verhoeff checksum), CIN, GSTIN, SEBI and other registration numbers.
3. **Names, companies and places use two passes** (`redactor/catalogue.py`).
   - *Discovery* builds a catalogue of the people, companies and localities in the document. It uses:
     - NER;
     - legal suffixes ("… Private Limited", "… LLP"), bank and institution names ("State Bank of India", "Capri College"), and partnerships ("Sharp, Wood and Chang");
     - names in reference lists ("B. A. Beckwith, R. Mahaadevan and F. Kuo");
     - names revealed by email addresses (`sachin.gawade@…` next to "Sachin Gawade");
     - addresses anchored on a postal code (Indian PIN, US ZIP, UK postcode).
   - *Matching* finds every occurrence of each catalogued entity, in any casing and in partial forms ("Rajesh Hegde" for "Rajesh Kushal Hegde").
4. **Precision comes from evidence in the document itself, not word lists:**
   - **A real name never appears in lower case.** "Working Days" is rejected because "working" appears in lower case. Related forms count as evidence too: "Integrated" is a common word because the document uses "integration".
   - **An acronym used in capitals inside sentences is never part of a name** ("OMB has issued…").
   - **A phrase spelled out by an acronym next to it is a term, not a person or company** (the glossary row "PMAY" | "Pradhan Mantri Awas Yojana").
   - **A brand that is also an English word is matched only in the ALL-CAPS form** the document uses for the company ("CARE", never "care").
5. **Consistent fakes** (`redactor/pseudonymizer.py`), derived from an HMAC of the real value with the secret key:

   | Real | Fake |
   |---|---|
   | Kushal Subbayya Hegde / KUSHAL SUBBAYYA HEGDE | Advay Urvashi Aurora / ADVAY URVASHI AURORA |
   | Rajesh Kushal Hegde (his son) | Owen **Advay Aurora** |
   | KSH International Limited / cs.connect@kshinternational.com | LNK International Limited / cs.connect@lnkinternational.com |
   | CARE Analytics … Limited / "CARE Report" / "CareEdge Research" | PNVK Ludada … Limited / "PNVK Report" / "PNVKEdge Research" |
   | +91 22 4009 4400 and +91 22 40094400 | the same fake number, each in its own format |
   | CIN U28129PN1979PLC141032 and "Registration number: 141032" | the same fake registration number in both |

   - Names are mapped word by word, so name variants and family links stay consistent.
   - Companies keep their generic words and legal suffix; only the distinctive word changes, and its fake is reused in the company's emails and website.
   - Fakes keep formats valid: Aadhaar fakes pass Verhoeff, card fakes pass Luhn, and IPs are documentation addresses.
   - A collision check guarantees that two real values never share a fake, and that a fake never equals a real name.
   - In an email address, any word that isn't a role word (`support`, `investor`) or an ordinary word is masked. An unknown name fails safe.
6. **Images** (logos, a QR code, scanned PAN and Aadhaar cards) are replaced with same-size "IMAGE REDACTED" placeholders, so the layout is unchanged.

## What is masked (policy)

- **Masked:** people, the issuer and its group companies, family trusts, customers, suppliers and intermediaries, their identifiers (CIN, registration numbers), rare localities, and websites owned by any of these.
- **Kept:**
  - **Regulators, exchanges, government bodies and laws** (SEBI, BSE, RBI, Companies Act), plus public-sector websites (`gov.in`, `.gov`). Every prospectus mentions them; they identify no one.
  - **Websites of public references:** a journal, github.com, a newspaper.
  - **Financial figures, ordinary dates and product details.** Masking them would destroy the text's value, but they could still help someone infer the company (see trade-offs).
  - **Order and ticket numbers** (`ORD-8430815`). They identify a transaction, not a person. Adding them is one line (see "Extending").

## Results (details in [EVALUATION.md](EVALUATION.md))

| Test set | Precision | Recall | F1 | Token accuracy |
|---|---|---|---|---|
| Prospectus, held-out sample (100 paragraphs) | 97.3% | 100% | 98.6% | 99.2% |
| Synthetic ticket log (US/UK/IN, 635 spans) | 100% | 96.7% | 98.3% | 99.3% |
| NIST SP 800-122 (US guide) | 89.7% | 88.9% | 89.3% | 99.8% |
| Research paper (2018-1337) | 95.3% | 87.2% | 91.1% | 99.7% |
| College PII policy | 100% | 100% | 100% | 100% |
| Research paper (IJERT) | 55.6% | 100% | 71.4% | 99.6% |

- **Labelling:** every set was labelled by hand before the tool ran on it.
- **Fixes:** every fix was a general rule, checked against the prospectus by comparing its output word by word before and after.
- **Leakage:** none of the 238 detected values remains anywhere in the redacted prospectus file, including link targets and Word field codes (an external review found 27 emails there; now fixed).

## Trade-offs, false positives and false negatives

- **Not read yet:** image alt text, charts, embedded objects and content controls (none hold PII in the prospectus, but another file could).
- **Precision over recall for ambiguous single words.** A company word that is also an English word ("Broad" in Broad Family Trust) is replaced only inside the full name, never on its own.
- **Consistency amplifies mistakes.** "Find once, replace everywhere" also spreads a wrong discovery. That's why discovery needs evidence from the document (the lower-case, acronym and glossary rules).
- **False positives:**
  - spaCy calls some product names people ("Spring Boot", "Protocol Labs"), which is most of the IJERT errors. Filtering them would need a word-frequency list.
  - Public institutions' own addresses (SEBI's, NIST's) are masked: the tool can't tell whose address it is.
- **False negatives:**
  - company names with no suffix that NER also misses ("Booz Allen Hamilton", "TCS");
  - double-barrelled company names ("Richardson-Wells"), which read as surnames;
  - author names in a paper's title block.
- **Not anonymous against context:** figures and product details can point to the company. Document metadata and tracked-change authors aren't rewritten (the prospectus has none).
- **The key matters:** without a secret, each run uses a random key. With a shared key, fakes are reproducible, so keep the key and any `--mapping` output private.
- **`en_core_web_lg`, not a transformer:** about 10 s for the whole prospectus on a CPU. The rules make up for its weaker accuracy.

## Extending to a new PII type

1. Add a detector. Usually that's one line in `redactor/detectors/patterns.py`, e.g. `ORDER_ID = RegexDetector("ORDER_ID", r"\bORD-\d{7}\b")`.
2. Register it in `STRUCTURED_DETECTORS` (`redactor/detectors/registry.py`).
3. Add a fake for its label in `Pseudonymizer.fake`. `_digits_like` covers most number formats.
4. Add a test in `tests/`.

## Project layout

```
redactor/
  docx_io.py            read and rewrite the .docx XML, run-aware replacement
  detectors/            patterns (structured PII), organizations, addresses, people, shared lexicon
  catalogue.py          pass 1 (discovery) and pass 2 (matching)
  pseudonymizer.py      consistent, format-preserving fakes
  pipeline.py           detection, overlap resolution, policy, redaction
  images.py             image placeholders
  __main__.py           command line
eval/
  evaluate.py           precision / recall / F1 / token accuracy / leakage
  run_all.py            rebuild and score every test set
  <test set>/           hand-made labels and results
tests/                  unit tests
output/                 redacted prospectus
```

`doc/` (the inputs) is not committed. Converted inputs and redacted test copies are rebuilt in `eval/.work/`.
