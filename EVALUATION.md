# Evaluation report

## Summary

| | Test set | Precision | Recall | F1 | Token accuracy |
|---|---|---|---|---|---|
| Round 1: first version | prospectus, 100 paragraphs, 63 PII spans | 100.0% | 87.3% | 93.2% | 98.91% |
| Round 2: Round-1 misses fixed | prospectus, **held-out** 100 paragraphs, 36 spans | **94.7%** | **100.0%** | **97.3%** | 99.12% |
| Round 3: other domains, before → after | NIST SP 800-122 (US guide), whole document, 45 spans | 10.2% → **78.0%** | 82.2% → **82.2%** | 18.2% → **80.1%** | 98.46% → 99.81% |
| | synthetic support-ticket log (US/UK/IN), 635 spans | 78.3% → **100.0%** | 83.1% → **96.7%** | 80.6% → **98.3%** | 87.98% → 99.31% |

**Leakage:** 0 of the 237 real values the script detected remain anywhere in the redacted prospectus. Round 3 also found real names that the earlier versions **missed and leaked** in the prospectus. That leakage scan couldn't see them; see Round 3.

**How to read the rounds:**
- **Round 2** is the honest prospectus number. Round 1 found 4 problems, I fixed them with general rules, then measured on a **new sample the fixes had never seen**, labelled before running the tool on it. The first sample now scores 100% on every metric, but that isn't reported as a result, because the fixes were made by looking at that sample's errors.
- **Round 3** asks whether the tool works beyond Indian legal documents. The assignment asks for SSNs and describes the input as a "ticket log", so it must.

## Method

1. **Sample** (`eval/sample.py`, fixed seed): 100 paragraphs from the prospectus, stratified:
   - 50 drawn uniformly at random, to measure false positives on ordinary text;
   - 50 drawn from paragraphs with a simple PII *signal* (an `@`, `+91`, a legal suffix, a 6-digit number, or two capitalised words in a row), to measure recall where PII actually occurs. The signal is deliberately cruder than the detectors, so the sample isn't biased toward what they already find.
   - Paragraphs over 700 characters are skipped to keep manual labelling reliable.
   - The first sample uses seed 7 (`eval/sample.jsonl`). The held-out sample uses seed 8 and excludes every paragraph of the first one (`eval/sample_holdout.jsonl`).
2. **Ground truth** (`eval/ground_truth.jsonl`, `eval/ground_truth_holdout.jsonl`): every PII span, labelled from the raw text *before* looking at the script's output for those paragraphs. Labelling was LLM-assisted (Claude) and checked by hand. Labels follow the masking policy in the README:
   - **Labelled:** "State Bank of India", because it is the company's banker (a counterparty).
   - **Not labelled:** "SEBI", SEBI's own office address, and sebi.gov.in links, because regulators are kept.
3. **Matching** (`eval/evaluate.py`): detection runs on the whole document, then predictions are compared with the gold spans of the sampled paragraphs. A prediction matches a gold span if the two **overlap**.
   - **Redaction view:** the label is ignored. This is the privacy question: "was this text replaced?"
   - **Per-type view:** the label must also agree.
4. **Accuracy** is reported at **token level**: each whitespace token in the sample is PII or not, in the gold labels and in the predictions, and accuracy is the share of tokens where the two agree. Entity-level accuracy is not defined for span detection, because there is no countable set of true negatives.
5. **Leakage scan** over the **whole** redacted document: every real value the script detected anywhere, plus every gold value, is searched for in the output.

## Round 1: first version, first sample

| PII type | Gold | Predicted | Precision | Recall | F1 |
|---|---|---|---|---|---|
| **All PII (redaction view)** | 63 | 55 | 100.0% | 87.3% | 93.2% |
| ADDRESS | 5 | 4 | 100.0% | 80.0% | 88.9% |
| EMAIL | 11 | 11 | 100.0% | 100.0% | 100.0% |
| LOCATION | 1 | 1 | 100.0% | 100.0% | 100.0% |
| ORGANIZATION | 20 | 13 | 100.0% | 65.0% | 78.8% |
| PERSON | 14 | 14 | 100.0% | 100.0% | 100.0% |
| PHONE | 3 | 3 | 100.0% | 100.0% | 100.0% |
| REGISTRATION_ID | 4 | 4 | 100.0% | 100.0% | 100.0% |
| URL | 5 | 5 | 100.0% | 100.0% | 100.0% |

All 8 misses were companies or addresses. Every person, email, phone and ID was caught. The 8 missed spans came from 4 distinct problems:

| Missed | Why | Fix (a general rule, not a special case) |
|---|---|---|
| "CARE" in "CARE Report" (×4) | "Care" is an English word, so a single-word match for it was disabled to protect precision. | A company's distinctive word that is also an English word is matched **only in ALL CAPS**, and only if the document itself writes it in ALL CAPS inside a company name ("CARE Analytics and Advisory Private Limited"). "care" and "Care" are never touched. In an ALL-CAPS paragraph, the word could be the English word ("WE TAKE CARE OF…"), so there it is matched only in short cells of up to 3 words, such as the rating "‘CARE A-’". |
| "CareEdge Research" (×2) | Nickname without a legal suffix. | **Defined-term nickname:** `Company Ltd (“Nickname”)` makes the nickname an alias, but only when the nickname reuses the company's distinctive word. That rejects defined terms that are roles, such as `(“Practicing Company Secretary”)`. Its fake is built on the company's fake (CARE → PNVK, CareEdge → PNVKEdge), so the link between the two survives. |
| "State Bank of India" | Every word is a common word, so the weak-suffix rule rejected it. | `<Name> Bank of <Place>` is treated as a bank name. Regulators stay on the keep list (Reserve Bank of India, Export-Import Bank of India). |
| "2401 Gen Thimmayya Road, Cantonment" | Address line with no PIN code. | **Multi-line address:** a line that is only "City – PIN" ends an address that starts on the line above. The line above must look like a street line: short, with a number or an address word, and no "Telephone:"/email label. |

**Safety check.** I compared the old and new output of the full prospectus word by word. Exactly 34 paragraphs changed, and every change is one of the four fixes:
- "CARE" → "PNVK" (44 times);
- "CareEdge" → "PNVKEdge" (7 times);
- "State" → "Lenven" in "State Bank of India";
- two street lines replaced. One of them ("Tara Chambers, Mumbai-Pune Road, Wakdewadi") was a miss outside the sample that nobody had found yet.

Nothing else in the document changed.

## Round 2: held-out sample (seed 8), scored with the old and new code

| | Precision | Recall | F1 | Token accuracy |
|---|---|---|---|---|
| Before the fixes | 94.3% | 91.7% | 93.0% | 98.90% |
| **After the fixes** | **94.7%** | **100.0%** | **97.3%** | **99.12%** |

Per type, after the fixes:

| PII type | Gold | Predicted | Precision | Recall | F1 |
|---|---|---|---|---|---|
| **All PII (redaction view)** | 36 | 38 | 94.7% | 100.0% | 97.3% |
| ADDRESS | 5 | 6 | 83.3% | 100.0% | 90.9% |
| CIN | 1 | 1 | 100.0% | 100.0% | 100.0% |
| EMAIL | 1 | 1 | 100.0% | 100.0% | 100.0% |
| ORGANIZATION | 14 | 14 | 100.0% | 100.0% | 100.0% |
| PERSON | 10 | 11 | 90.9% | 100.0% | 95.2% |
| PHONE | 3 | 3 | 100.0% | 100.0% | 100.0% |
| REGISTRATION_ID | 2 | 2 | 100.0% | 100.0% | 100.0% |

**False positives (2).** Both were already there before the fixes, and both are left unfixed so that this sample stays held-out:
- **"Deen Dayal"** in "Deen Dayal Upadhyaya Gram Jyoti Yojana", a government scheme named after a historical person. The text reads as a name, and the "never in lower case" filter can't tell a scheme from a person. Fix: treat a capitalised name followed by a scheme word (Yojana, Scheme, Mission) as a scheme name.
- **SEBI's own office address** ("SEBI Bhavan, Plot No. C4 A, 'G' Block"). It's a public regulator address and is kept by policy, but the address rule doesn't check whose address it is. Fix: skip an address whose line names a kept organisation.

Both errors replace public text, so nothing private leaks. They cost readability, not privacy.

**Caveat on independence.** Detection is document-wide: once "CARE" is learned, it is replaced everywhere. So the two samples are not fully independent. Part of the recall gain on the held-out sample comes from the same entity (CARE / CareEdge) appearing in new paragraphs. What the held-out sample does show is that the rule works on occurrences it was not tuned on, and that it added no false positives: precision did not drop.

## Round 3: other domains

### Test sets

**1. NIST SP 800-122**, the US guide to protecting PII (`eval/nist/`).
- **Conversion:** a PDF converted to one Word paragraph per text block (`convert.py`).
- **Labelling:** all 559 paragraphs, labelled **before** running the tool.
- **Gold labels:** 37 real people (authors, reviewers, cited authors, officials) and 8 private organisations (the reviewers' employers).
- **Not labelled, the same policy as SEBI in the prospectus:** government bodies, cited publishers, NIST's own office address and public reference URLs.
- **What it tests:** the text talks *about* PII constantly ("social security number", "SSN", "ZIP code") but contains little real PII, so this is mostly a false-positive test.

**2. Synthetic support-ticket log** (`eval/tickets/generate.py`, seed 2026).
- **Contents:** 120 tickets, 635 paragraphs, generated with Faker in US, UK and Indian formats: names, lone first names, emails, international phones, US/UK addresses, SSNs, cards, IPs, dates of birth and companies.
- **Look-alikes mixed in:** ticket and order numbers, versions, amounts, ordinary dates, RFC numbers.
- **Gold labels:** the generator inserts every PII value, so the labels are exact.
- **When it was made:** generated and scored **before** any Round-3 change.

### Before the changes

| | Precision | Recall | Main errors |
|---|---|---|---|
| NIST | 10.2% | 82.2% | 205 of 289 false positives came from **one** bad discovery (below); 84 public .gov URLs replaced |
| Tickets | 78.3% | 83.1% | US/UK addresses 9% recall; international phones 22%; companies without a legal suffix 30%; every ticket header "TCK-100000" read as "City – PIN" |

**The NIST false positives came from one bad guess being copied everywhere.**
- Appendix F lists acronyms in capital-only lines ("NARA NIST NPPI").
- NER can't read capitals, so the tool title-cases such lines first. That turned the line into "Nara Nist Nppi", which spaCy called a person.
- The catalogue then did what it's built to do: every "NIST", "OMB" (41×), "HIPAA" and "SSN" in the document became a fake person.
- So the mechanism that makes replacements consistent also amplifies a single bad discovery.

### Changes (general rules, each checked against the prospectus)

| Problem | Rule |
|---|---|
| Acronyms read as names | An ALL-CAPS word of 3–6 letters that appears in capitals inside ordinary sentences, and is never written title-cased ("Nist"), is an acronym and can't be part of a name. This mirrors the "real names never appear in lower case" rule. Names in capitals ("KUSHAL HEGDE") also appear as "Hegde", so they're unaffected. Two-letter initials ("DM Shetty") are unaffected. |
| Public sites masked | `.gov`, `.gov.xx`, `.mil` and `.int` join the keep list, the same policy as gov.in. |
| Phones | Any `+<country code>` number; North American `(591)341-7776` / `206.269.0743`; UK `0113 496 0141`; more labels (`Callback number:`, `Cell:`). A bare digit run still needs a label. The fake keeps the country code and the format. |
| Addresses | US "City, ST 12345" and UK postcodes are address anchors next to the Indian "City – PIN". "address … :" is a cue. A capitals-only code ("TCK-100000") is never a city. |
| Companies without a legal suffix | "Group" and "& Sons" are company designators. "Surname, Surname and Surname" is a partnership name when every word is a proper noun. (If it's really a list of people, masking it is still correct, since surnames are PII.) Law titles ("…Trades, Callings and Employment **Act**") and words whose base form appears in lower case ("Employment" → "employ") are excluded. |
| Institution words learned as places | "Institute", "Laboratory", "University", etc. are generic words: never places, never the identifying part of a name. |
| **Names leaked through emails** | Explained in the next section. |

### A leak found in the prospectus

The prospectus output committed after Round 2 still contained **real names that NER had missed**:
- Sachin Gawade, Hitesh Ramani, Manisha Shukla and Sharmila Hayer (bank and intermediary contacts), both in the text and inside their email addresses;
- the email local parts `parag.pansare`, `sheetal.parab` and `ashishmp`.

**Why nothing caught it:** the email's domain *was* replaced, and the leakage scan only checks values the tool detected. The bug was that, inside an email's local part, any word that wasn't a known name was kept, to protect role words like `cs.connect`.

**Two fixes:**
1. **Names are learned from emails.** If a local part looks like `first.last` and "First Last" appears in the text, that's a person.
2. **Unknown local-part words are treated as names by default.** Only role words (support, investor, ipo…), ordinary words from the document, and 1–2 letter pieces are kept. A miss is now masked instead of leaked.

**Result:** the only email local parts left unchanged in the prospectus output are `cs.connect`, `customerservice.mb` and `ipo`.

### After the changes

| | Precision | Recall | F1 |
|---|---|---|---|
| Prospectus, first sample / held-out | 100% / 94.7% | 100% / 100% | 100% / 97.3% (unchanged) |
| NIST | 78.0% | 82.2% | 80.1% |
| Tickets | 100.0% | 96.7% | 98.3% |

**Safety check:** a word-by-word comparison of the full prospectus output, before and after, shows 19 changed paragraphs. All of them are the leak fixes above, plus role mailboxes (`pro@`, `ipocmg@`) that are now masked, which is on the safe side.

### Still wrong, and why it's left

- **NIST:**
  - NIST's own office address is masked, the same issue as SEBI's address: the tool can't tell whose address it is.
  - Public citation URLs (nytimes.com, apec.org, findlaw.com) are masked. In the prospectus, URLs were company websites, which do identify the company. Telling a citation from a company's site needs semantics, and masking a URL by mistake costs readability, not privacy.
  - Names written initial-first ("L. Sweeney", "A. Pfitzmann") are missed.
  - Companies NER doesn't recognise ("Booz Allen Hamilton", "Carnegie Mellon University", "ICRI") are missed.
- **Tickets:**
  - Double-barrelled company names ("Richardson-Wells") are missed. spaCy itself calls them people, and without context they read as a surname.
  - Four lone first names at the start of a sentence are missed.
- **Caveat:** NIST and the ticket set were used to *find* these problems, so their "after" numbers are no longer clean held-out scores, in the same way as the first prospectus sample. What stays clean is that the prospectus scores didn't drop. The next honest step would be a fourth document no one has looked at.

## Other notes

- **Not in either sample:** PAN, Aadhaar, SSN, credit card, IP and date of birth do not occur in the document's text. They appear only inside the two ID-card images, which are replaced entirely. These detectors are covered by unit tests instead (`tests/test_detectors.py`), including checksum rejection of look-alikes.
- **Partial match:** "105215W/ W100057", an auditor's firm registration number, is caught only as "105215". It counts as a hit by overlap, but "W/ W100057" stays in the output. The ID pattern should allow a letter suffix and a "/ W…" continuation.

## Limitations

- Each sample covers 100 of about 4,200 paragraphs and skips paragraphs over 700 characters. Long prose paragraphs are where names are densest, so recall there is checked only indirectly, through the whole-document leakage scan.
- With 36–63 gold spans per sample, one error moves recall by 1.5–3 points. Read the numbers as approximate.
- The leakage scan can only confirm that *detected* values were removed. Missed entities are by definition not in that list.
- Ground truth was produced by one annotator with LLM assistance. A second independent annotator would let us measure inter-annotator agreement.

## Reproduce

```bash
python -m redactor "doc/Red Herring Prospectus (6).docx" -o "output/Red Herring Prospectus - redacted.docx"
# held-out sample (headline numbers)
python eval/evaluate.py "doc/Red Herring Prospectus (6).docx" "output/Red Herring Prospectus - redacted.docx" \
    eval/sample_holdout.jsonl eval/ground_truth_holdout.jsonl eval/results_holdout.json
# first sample
python eval/evaluate.py "doc/Red Herring Prospectus (6).docx" "output/Red Herring Prospectus - redacted.docx"
# NIST (PDF in doc/, public) and the synthetic ticket log
python eval/convert_pdf.py doc/nistspecialpublication800-122.pdf eval/nist/nist.docx
python -m redactor eval/nist/nist.docx -o eval/nist/nist_redacted.docx
python eval/evaluate.py eval/nist/nist.docx eval/nist/nist_redacted.docx eval/nist/sample.jsonl eval/nist/ground_truth.jsonl eval/nist/results.json
python eval/tickets/generate.py
python -m redactor eval/tickets/tickets.docx -o eval/tickets/tickets_redacted.docx
python eval/evaluate.py eval/tickets/tickets.docx eval/tickets/tickets_redacted.docx eval/tickets/sample.jsonl eval/tickets/ground_truth.jsonl eval/tickets/results.json
# how the samples were drawn (already committed)
python eval/sample.py "doc/Red Herring Prospectus (6).docx" eval/sample.jsonl 7
python eval/sample.py "doc/Red Herring Prospectus (6).docx" eval/sample_holdout.jsonl 8 eval/sample.jsonl
```
