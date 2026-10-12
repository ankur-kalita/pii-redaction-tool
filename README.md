# PII Redaction Tool

Replaces personally identifiable information in a `.docx` with **realistic, consistent fake values**, and keeps the document's formatting. Built for the Red Herring Prospectus of an Indian IPO, where the redacted text is meant for model training: the model should learn how such documents are written ("the promoter named on the cover is the same person signing in clause 40") without learning who the company or the people are.

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
   - phone, accepted only with a phone signal: `+91`, an STD code with a hyphen, or a `Tel:` label;
   - PAN, where the 4th letter must be a valid holder type;
   - Aadhaar, with a Verhoeff checksum;
   - credit card, with a Luhn checksum;
   - SSN and IP, with range checks;
   - date of birth, only when introduced as one;
   - CIN, GSTIN, SEBI registration numbers, and labelled registration/peer-review/DIN numbers.
3. **Names, companies, addresses: two passes.**
   - *Discovery:* spaCy NER, run on a title-cased copy of ALL-CAPS text because NER can't read capitals, plus company-suffix rules ("… Private Limited", "… LLP", "… Family Trust"). Together they build a catalogue of the real people and organisations.
   - *Matching:* every catalogued entity is found everywhere, in any casing and in partial forms. A name NER saw once is replaced in all its occurrences.
   - A data-driven filter keeps this precise: **a real name never appears in lower case anywhere in the document, while ordinary words do**. That rejects "Working Days" or "Refund Bank" as names.
   - Addresses are anchored on "City – PIN code". In prose, an address starts after "located at" / "Office at".
   - Rare place names learned from those addresses ("our plant at Chakan") are also masked.
4. **Consistent pseudonymization.** This is the core requirement:

   | Real | Fake |
   |---|---|
   | Kushal Subbayya Hegde / KUSHAL SUBBAYYA HEGDE | Advay Urvashi Aurora / ADVAY URVASHI AURORA |
   | Rajesh Kushal Hegde (his son) | Owen **Advay Aurora** |
   | Rohit Hegde | Aarnav Aurora (same as "Rohit Kushal Hegde" → "Aarnav Advay Aurora") |
   | KSH International Limited / cs.connect@kshinternational.com | LNK International Limited / cs.connect@lnkinternational.com |
   | +91 22 4009 4400 and +91 22 40094400 | the same fake number, each in its own format |
   | CIN U28129PN1979PLC141032 and "Registration number: 141032" | the CIN's registration part and the standalone number get the same fake |

   - Names are mapped **word by word**, so every variant of a name, and family relations, stay consistent.
   - Companies keep their generic words and legal suffix. Only the distinctive word changes, and the same fake word is reused in the company's emails and website.
   - Fakes come from a keyed hash of the real value, so they're reproducible. A collision check means two real values never share a fake, and a fake never equals a real name.
5. **Images.** All 8 images identify someone: the company logo, a QR code linking to the real prospectus, intermediaries' logos, and scans of a PAN card and an Aadhaar card with photo, name, DOB and number. They are replaced with same-size "IMAGE REDACTED" placeholders, so the layout is unchanged.

### What is masked (policy)

- **Masked:** the issuer and its group companies, promoters, directors and officers, selling shareholders and their family trusts, named customers and suppliers, and intermediaries (lead managers, registrar, auditors, banks). All of these identify *this* IPO.
- **Also masked:** extra identifiers (CIN, registration numbers, websites, plant localities).
- **Kept:** regulators, exchanges, depositories, government bodies and laws (SEBI, BSE, NSE, RBI, NSDL, Companies Act), plus their websites. They appear in every prospectus and carry the document's structure.
- **Kept on purpose:** financial figures, ordinary dates and product descriptions. Masking them would destroy what the model should learn, but a determined reader could still guess the company from them.
- Order/ticket numbers don't occur in this document.

## Results (details in [EVALUATION.md](EVALUATION.md))

On 100 hand-labelled paragraphs (63 PII spans):
- **precision 100%**, **recall 87.3%**, F1 93.2%;
- token-level accuracy 98.9%;
- 0 of the 231 detected real values remain anywhere in the output.

## Trade-offs, false positives and false negatives

- **Precision was favoured over recall for single words.** "CARE" (the industry-report provider) and "Broad" (Broad Family Trust) are English words, so they are only replaced as part of a full name. Masking "care" everywhere would corrupt the text. This causes the main false negatives: "CARE Report" and "CareEdge Research", where the brand is used without a legal suffix. Also missed: "State Bank of India" and one PIN-less address line. See the evaluation report for the fix for each.
- **No false positives in the sample.** Before the conservative filters, NER produced many: "Supa Facility", "Working Days", "United States Dollars" and "Refund Bank" were all candidate names or companies.
- **Addresses** are the weakest type. Lines with no PIN code are only accepted with at least 2 address words and a number.
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
