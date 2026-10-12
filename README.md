# PII Redaction Tool

Replaces personally identifiable information in a `.docx` with **realistic, consistent fake values**, and keeps the document's formatting.

- **Main input:** the Red Herring Prospectus of an Indian IPO, where the redacted text is meant for model training. The model should learn how such documents are written ("the promoter named on the cover is the same person signing in clause 40") without learning who the company or the people are.
- **Also tested on** a US government guide (NIST SP 800-122) and a synthetic US/UK/Indian support-ticket log, because the tool must work beyond one document type.

```bash
pip install -r requirements.txt
python -m spacy download en_core_web_lg
python -m redactor "doc/Red Herring Prospectus (6).docx" -o "output/Red Herring Prospectus - redacted.docx"
pytest
```

The redacted file is in `output/`. The evaluation report is in [EVALUATION.md](EVALUATION.md).

## Approach

**Rules + NER, two passes, deterministic fakes.** No LLM is used at runtime: the script runs offline, for free, and gives the same output every time.

1. **Read every text part of the .docx at the XML level:** body, tables, text box, 75 headers, 74 footers, and hyperlink targets. Word splits text into formatting "runs", so a name can be stored in three pieces. Detection runs on the joined paragraph text, and each replacement is written back into the first run it touches, which keeps the formatting.
2. **Structured PII: regex plus validation.** Validators remove look-alikes:
   - email, URL;
   - phone, accepted only with a phone signal: a country code (`+91`, `+1`, `+44`…), an area/STD code written as one (`022-68052182`, `(591)341-7776`, `0113 496 0141`), or a label (`Tel:`, `Callback number:`);
   - PAN, where the 4th letter must be a valid holder type;
   - Aadhaar, with a Verhoeff checksum;
   - credit card, with a Luhn checksum;
   - SSN and IP, with range checks;
   - date of birth, only when introduced as one;
   - CIN, GSTIN, SEBI registration numbers, and labelled registration/peer-review/DIN numbers.
3. **Names, companies, addresses: two passes.**
   - *Discovery:* spaCy NER, run on a title-cased copy of ALL-CAPS text because NER can't read capitals, plus company-suffix rules ("… Private Limited", "… LLP", "… Family Trust"). Together they build a catalogue of the real people and organisations.
   - *Matching:* every catalogued entity is found everywhere, in any casing and in partial forms. A name NER saw once is replaced in all its occurrences.
   - Two data-driven filters keep this precise:
     - **A real name never appears in lower case anywhere in the document, while ordinary words do.** That rejects "Working Days" or "Refund Bank" as names.
     - **An acronym is used in capitals inside ordinary sentences and is never written title-cased.** "OMB has issued…" means "OMB" is never part of a name, even when a capitals-only line ("NARA NIST NPPI") looks like one to NER.
   - **Names are also learned from emails:** `sachin.gawade@…` plus the text "Sachin Gawade" is a person, even if NER missed it.
   - **Companies without a legal suffix:** "… Group", "… & Sons", and partnership names ("Sharp, Wood and Chang") whose words are all proper nouns.
   - **Addresses** are anchored on a postal code: Indian "City – PIN", US "City, ST 12345", or a UK postcode. In prose, an address starts after "located at" / "Office at" / "address on file:".
   - Rare place names learned from those addresses ("our plant at Chakan") are also masked.
   - **A brand that is also an English word** ("CARE", the industry-report provider) is matched only in ALL CAPS, and only because the document writes it in ALL CAPS inside a company name. "care" and "Care" are never touched.
   - **Defined-term nicknames** (`… Private Limited (“CareEdge Research”)`) become aliases when they reuse the company's distinctive word.
   - **An address split over lines** ("2401 Gen Thimmayya Road, Cantonment" / "Pune – 411 001") is recognised from the "City – PIN" line below the street line.
4. **Consistent pseudonymization.** This is the core requirement:

   | Real | Fake |
   |---|---|
   | Kushal Subbayya Hegde / KUSHAL SUBBAYYA HEGDE | Advay Urvashi Aurora / ADVAY URVASHI AURORA |
   | Rajesh Kushal Hegde (his son) | Owen **Advay Aurora** |
   | Rohit Hegde | Aarnav Aurora (same as "Rohit Kushal Hegde" → "Aarnav Advay Aurora") |
   | KSH International Limited / cs.connect@kshinternational.com | LNK International Limited / cs.connect@lnkinternational.com |
   | +91 22 4009 4400 and +91 22 40094400 | the same fake number, each in its own format |
   | CIN U28129PN1979PLC141032 and "Registration number: 141032" | the CIN's registration part and the standalone number get the same fake |
   | CARE Analytics … Limited / "CARE Report" / "CareEdge Research" | PNVK Ludada … Limited / "PNVK Report" / "PNVKEdge Research" |

   - Names are mapped **word by word**, so every variant of a name, and family relations, stay consistent.
   - Companies keep their generic words and legal suffix. Only the distinctive word changes, and the same fake word is reused in the company's emails and website.
   - Fakes come from a keyed hash of the real value, so they're reproducible. A collision check means two real values never share a fake, and a fake never equals a real name.
   - Emails fail safe. A word in the part before the "@" is kept only if it's a role word (`support`, `investor`, `cs.connect`) or an ordinary word. Anything else is treated as a name and replaced.
5. **Images.** All 8 images identify someone: the company logo, a QR code linking to the real prospectus, intermediaries' logos, and scans of a PAN card and an Aadhaar card with photo, name, DOB and number. They are replaced with same-size "IMAGE REDACTED" placeholders, so the layout is unchanged.

### What is masked (policy)

- **Masked:** the issuer and its group companies, promoters, directors and officers, selling shareholders and their family trusts, named customers and suppliers, and intermediaries (lead managers, registrar, auditors, banks). All of these identify *this* IPO.
- **Also masked:** extra identifiers (CIN, registration numbers, websites, plant localities).
- **Kept:** regulators, exchanges, depositories, government bodies and laws (SEBI, BSE, NSE, RBI, NSDL, Companies Act), plus their websites and other public-sector sites (`gov.in`, `.gov`, `.mil`, `.int`). They appear in every prospectus and carry the document's structure.
- **Kept on purpose:** financial figures, ordinary dates and product descriptions. Masking them would destroy what the model should learn, but a determined reader could still guess the company from them.
- **Order and ticket numbers are not treated as PII** (`ORD-8430815`, `TCK-100000`). They identify a transaction, not a person, and keeping them keeps support logs traceable. Adding them is one regex (see "Extending").

## Results (details in [EVALUATION.md](EVALUATION.md))

| | Test set | Precision | Recall | F1 |
|---|---|---|---|---|
| Round 1 | prospectus, 100 hand-labelled paragraphs | 100% | 87.3% | 93.2% |
| **Round 2** (Round-1 misses fixed) | prospectus, **held-out** 100 paragraphs | **94.7%** | **100%** | **97.3%** |
| Round 3, before → after | NIST SP 800-122 (US), whole document | 10.2% → 78.0% | 82.2% → 82.2% | 18.2% → 80.1% |
| | synthetic ticket log (US/UK/IN), 635 spans | 78.3% → 100% | 83.1% → 96.7% | 80.6% → 98.3% |

- **Round 2:** the Round 1 misses were fixed with general rules, then measured on paragraphs those fixes had never seen.
- **Round 3** showed the first versions were fitted to Indian documents. On NIST, one bad discovery spread into 200+ false positives.
- **Round 3's fixes** were general rules, checked with a word-by-word comparison of the prospectus output so its scores couldn't drop. That comparison also revealed **real names that earlier versions had leaked** through email addresses. They are now fixed.

## Trade-offs, false positives and false negatives

- **Precision was favoured over recall for single words.** "Broad" (Broad Family Trust) is an English word, so it is only replaced as part of the full name. Masking "broad" everywhere would corrupt the text.
  - "CARE" had the same problem; it was the main miss in Round 1.
  - It is now caught by a narrower signal, the ALL-CAPS form, instead of by loosening the filter. "care" and "Care" stay untouched.
- **False positives:** none in Round 1, and 2 in the held-out round, both public text:
  - "Deen Dayal" in a government scheme's name;
  - SEBI's own office address.
  - They were left unfixed so that the held-out sample stays honest. See EVALUATION.md for the fix for each.
  - Before the conservative filters, NER produced many: "Supa Facility", "Working Days", "United States Dollars" and "Refund Bank" were all candidate names or companies.
- **Addresses** are the weakest type. Lines with no postal code are only accepted with at least 2 address words and a number.
- **Catalogue amplification cuts both ways.** "Find once, replace everywhere" is what makes fakes consistent, but one wrong discovery is also replaced everywhere. The acronym and lower-case filters exist to stop that.
- **Policy needs context the tool doesn't have:**
  - it can't tell a public institution's address from a private one (SEBI's and NIST's offices are masked);
  - it can't tell a citation URL from a company's website, so both are masked.
  - Both errors cost readability, not privacy.
- **Not detected:** names written initial-first ("L. Sweeney"); companies that are neither suffixed nor recognised by NER ("Booz Allen Hamilton"); double-barrelled company names ("Richardson-Wells"), which read as surnames without context.
- **Not anonymous against context:** figures, dates and product details are kept, so the company could still be inferred. Document metadata (author in the file properties) and tracked-change authors are not rewritten. The prospectus's metadata is empty, but other files may not be.
- **The secret:** fakes are reproducible with the default `--secret`. Pass your own secret, and keep `--mapping` files private, because they contain the real values.
- **Formatting:** when a name or company name crosses formatting runs ("Rashi **Patil**"), each fake word keeps its real word's formatting ("Jatin **Nanda**"). A fake *address* has a different shape from the real one, so formatting applied to part of an address (e.g. one coloured locality) isn't carried over. The address itself is still fully replaced.
- **Text inside images** isn't read (no OCR). Images are replaced whole instead, which gives full recall for images at the cost of losing harmless content such as logos' shapes.
- `en_core_web_lg` rather than a transformer NER model: much faster on CPU (the whole document in about 10 s). The rules compensate for its weaker accuracy.

## Extending to a new PII type

1. Add a detector. Usually that's one line in `redactor/detectors/patterns.py`, e.g. `VOTER_ID = RegexDetector("VOTER_ID", r"\b[A-Z]{3}\d{7}\b")`, or a class with `label` and `detect(text) -> list[Span]`.
2. Register it in `STRUCTURED_DETECTORS` (`redactor/detectors/registry.py`).
3. Add a fake generator for its label in `Pseudonymizer.fake` (`redactor/pseudonymizer.py`). `_digits_like` covers most number formats.
4. Add a test in `tests/test_detectors.py`.

## Project layout

```
redactor/
  docx_io.py         read/write all XML parts, run-aware replacement
  detectors/         base interface, regex detectors, entity rules, registry
  catalogue.py       pass 1 (discovery) and pass 2 (matching) for names/companies/places
  pseudonymizer.py   consistent, format-preserving fakes
  images.py          image placeholders
  pipeline.py        end-to-end redaction, overlap resolution, policy allow-list
  __main__.py        CLI (--findings / --mapping write real PII: keep them private)
eval/                sample, ground truth, scoring script, results
tests/               unit tests
output/              redacted prospectus
```

The original document and any real→fake mapping are git-ignored, since they contain real PII.
