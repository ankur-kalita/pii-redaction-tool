# Evaluation report

## Results

| Test set | Scored | Gold spans | Precision | Recall | F1 | Token accuracy |
|---|---|---|---|---|---|---|
| **Prospectus, held-out sample** | 100 paragraphs | 36 | **97.3%** | **100%** | **98.6%** | 99.21% |
| Prospectus, first sample (used for tuning) | 100 paragraphs | 63 | 100% | 100% | 100% | 99.80% |
| Synthetic ticket log (US/UK/IN) | whole document | 635 | 100% | 96.7% | 98.3% | 99.31% |
| NIST SP 800-122 (US guide) | whole document | 45 | 89.7% | 88.9% | 89.3% | 99.84% |
| Research paper 2018-1337 | whole document | 47 | 95.3% | 87.2% | 91.1% | 99.66% |
| Capri College PII policy | whole document | 4 | 100% | 100% | 100% | 100% |
| Research paper (IJERT) | whole document | 20 | 55.6% | 100% | 71.4% | 99.56% |

- **Leakage:** none of the 238 real values detected in the prospectus remains anywhere in the redacted file. The scan reads **every XML part** of the file: text, link targets, field codes and metadata.
- **Correction:** an earlier version of this report claimed zero leakage while scanning only paragraph text. A review found 27 real email addresses still in the file, inside Word `HYPERLINK` field codes (the hidden link targets behind clickable text). They are now rewritten, and the scan covers the whole file.
- **Headline number:** the held-out prospectus sample, because the document the tool was built for matters most. The other documents show how well the tool generalises.
- **Reproduce:** `python eval/run_all.py` rebuilds every test document from `doc/` (or from the generator), redacts it and writes the results above to `eval/<set>/results.json`.

## Method

1. **Ground truth.** Every PII span was labelled by hand, with LLM assistance and checked, *before* the tool was run on that text. Labels follow the policy in the README:
   - **Labelled:** people, private companies and their identifiers, private addresses, and websites of masked entities.
   - **Not labelled:** regulators, government bodies, cited publishers, public reference URLs, and public institutions' addresses.
2. **Samples.**
   - **Prospectus** (about 4,200 paragraphs): two stratified samples (`eval/prospectus/sample.py`). Each has 50 random paragraphs, to measure false positives, and 50 paragraphs with a cheap PII signal (`@`, `+91`, a legal suffix, a 6-digit number, two capitalised words), to measure recall. The signal is cruder than the detectors, so the sample isn't biased towards what they find.
   - **Held-out sample:** seed 8, excluding every paragraph of the first sample (seed 7).
   - **Every other document** is scored in full.
3. **Matching.** Detection runs on the whole document, because the catalogue needs the full text. A prediction matches a gold span if they **overlap**. The headline view ignores the label, because the privacy question is "was it replaced?". The per-type view also requires the label to agree.
4. **Token accuracy.** Each whitespace token is PII or not, in the gold labels and in the predictions; accuracy is the share where they agree. Entity-level accuracy is undefined, because there is no countable set of true negatives.
5. **Leakage scan.** Every detected value, and every gold value, is searched for in the redacted output.
6. **Honesty protocol.**
   - A test set used to *find* errors is no longer an unbiased measure. So after fixing a set's errors, the score that counts comes from text the fixes never saw.
   - Every fix is a **general rule**, never a word list for one document.
   - Every fix is checked with a word-by-word comparison of the full prospectus output before and after.

## How the scores developed

| Round | What was tested | Before | After |
|---|---|---|---|
| 1 | Prospectus, first sample | P 100%, R 87.3%, F1 93.2% | — |
| 2 | Round-1 fixes, on the **held-out** sample | P 94.3%, R 91.7%, F1 93.0% | P 94.7%, R 100%, F1 97.3% |
| 3 | Other domains: NIST | P 10.2%, R 82.2%, F1 18.2% | P 78.0%, R 82.2%, F1 80.1% |
| 3 | Other domains: tickets | P 78.3%, R 83.1%, F1 80.6% | P 100%, R 96.7%, F1 98.3% |
| 4 | Three **unseen** documents: paper 2018-1337 | F1 14.8% (R 8.5%) | F1 91.1% |
| 4 | Capri policy | R 0% | F1 100% |
| 4 | IJERT paper | F1 15.6% (P 11.4%) | F1 71.4% |

**What each round taught:**

1. **Brands that are English words, nicknames, banks, split addresses.**
   - "CARE" is matched only in its ALL-CAPS company form.
   - `Company (“Nickname”)` is an alias when the nickname reuses the company's word.
   - "<Name> Bank of <Place>" is a bank's name.
   - A line that is only a postal code ends the address on the line above.
2. **The fixes generalised:** recall reached 100% on paragraphs they had never seen.
3. **The tool was fitted to Indian documents.**
   - On NIST, one capitals-only acronym line ("NARA NIST NPPI") was read as a person. The catalogue then replaced every "OMB" and "NIST" with a fake person: 205 false positives from one bad discovery.
   - Fixes: the acronym rule, international phone and postal formats, public-sector sites, companies without a legal suffix.
4. **The three unseen documents exposed:**
   - citation-style names ("B. A. Beckwith");
   - colleges ("Capri College");
   - public websites masked for no reason.
   - Fixes: citation names, institution names, and masking a URL only when its owner is masked.
   - The same round **removed every document-specific word list.** They were replaced by evidence rules: related word forms ("Integrated" → "integration") and glossary terms ("PMAY" | "Pradhan Mantri Awas Yojana").

**Real leaks found on the way.** All three are fixed and are the strongest argument for testing beyond the target document:
- **Round 3:** contact names that NER had missed (Sachin Gawade, Hitesh Ramani, Manisha Shukla, Sharmila Hayer) were left in the redacted prospectus, in the text and in their emails. The leakage scan couldn't see them, because it only checks detected values. Fix: names are learned from email addresses, and unknown words in an email address are masked by default.
- **External review:** 27 real email addresses survived inside Word `HYPERLINK` field codes, which the tool never read; the old leak scan read only paragraph text, so it missed them too. Fix: field codes are rewritten like visible links, and the leak scan reads every XML part.
- **Round 4:** a hard-coded word list was hiding "EVEREST" (Everest Family Trust, a selling shareholder) in a capitals heading. Removing the list fixed it.

## Per-type results, prospectus held-out sample

| PII type | Gold | Predicted | Precision | Recall | F1 |
|---|---|---|---|---|---|
| **All PII** | 36 | 37 | 97.3% | 100% | 98.6% |
| ADDRESS | 5 | 6 | 83.3% | 100% | 90.9% |
| CIN | 1 | 1 | 100% | 100% | 100% |
| EMAIL | 1 | 1 | 100% | 100% | 100% |
| ORGANIZATION | 14 | 14 | 100% | 100% | 100% |
| PERSON | 10 | 10 | 100% | 100% | 100% |
| PHONE | 3 | 3 | 100% | 100% | 100% |
| REGISTRATION_ID | 2 | 2 | 100% | 100% | 100% |

## Per-type results, ticket log

| PII type | Gold | Predicted | Precision | Recall | F1 |
|---|---|---|---|---|---|
| **All PII** | 635 | 622 | 100% | 96.7% | 98.3% |
| ADDRESS (US/UK) | 33 | 30 | 100% | 90.9% | 95.2% |
| CREDIT_CARD | 11 | 11 | 100% | 100% | 100% |
| DATE_OF_BIRTH | 10 | 10 | 100% | 100% | 100% |
| EMAIL | 120 | 120 | 100% | 100% | 100% |
| IP_ADDRESS | 25 | 25 | 100% | 100% | 100% |
| ORGANIZATION | 120 | 111 | 99.1% | 85.0% | 91.5% |
| PERSON | 275 | 273 | 98.9% | 98.2% | 98.5% |
| PHONE | 37 | 37 | 100% | 100% | 100% |
| SSN | 4 | 4 | 100% | 100% | 100% |

- **Generator:** the ticket log is generated with Faker (`eval/tickets/generate.py`, fixed seed), so its labels are exact.
- **Look-alikes mixed in:** order and ticket numbers, versions, amounts and RFC numbers. None of them was redacted.
- **Only source of SSNs, cards and IPs:** the prospectus text has none of these. They appear only in the scanned ID images, which are replaced whole. Unit tests cover these types too.

## Remaining errors

| Test set | False positives | False negatives |
|---|---|---|
| Prospectus held-out | SEBI's own office address (public, kept by policy) | — |
| Tickets | — | double-barrelled company names ("Richardson-Wells", which spaCy itself calls a person); 4 first names used alone at the start of a sentence |
| NIST | NIST's own address; two cited institutes; one newspaper link | "Booz Allen Hamilton"-style names with no suffix; "L. Sweeney" written alone; "ICRI" |
| Paper 2018-1337 | "Long Short-Term Memory" read as a name | the two authors and their employers in the title block; a dataset owner's handle |
| IJERT paper | product names read as people ("Spring Boot", "Intel", "Protocol Labs") | — |

**Most remaining false positives are spaCy calling products and technical terms people.** Rejecting a name made only of common words would fix them, but it needs a word-frequency list. spaCy's vocabulary ranks aren't ordered by frequency, so they can't serve as one. Every false positive replaces public text, so they cost readability, not privacy.

## Limitations

- **Small samples.** 36–635 gold spans per set, so one error moves a small set's score by several points.
- **Prospectus sampling skips paragraphs over 700 characters,** where names are densest. Recall there is checked only indirectly, through the leakage scan.
- **The leakage scan only sees detected values,** as the Round 3 leak showed. Missed entities are by definition not in it.
- **One annotator, with LLM assistance.** A second annotator would let us measure agreement.
- **Not fully independent samples.** The prospectus samples share entities (the catalogue is document-wide), and NIST, the tickets and the three papers were each used to find errors after their first score. The "before" column above is their unbiased score.
