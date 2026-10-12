# Evaluation report

## Approach

1. **Sample** (`eval/sample.py`, fixed seed): 100 paragraphs from the prospectus, stratified:
   - 50 drawn uniformly at random, to measure false positives on ordinary text;
   - 50 drawn from paragraphs with a simple PII *signal* (an `@`, `+91`, a legal suffix, a 6-digit number, or two capitalised words in a row), to measure recall where PII actually occurs. The signal is deliberately cruder than the detectors, so the sample isn't biased toward what they already find.
   - Paragraphs over 700 characters were skipped to keep manual labelling reliable.
2. **Ground truth** (`eval/ground_truth.jsonl`): every PII span in the 100 paragraphs, labelled from the raw text *before* looking at the script's output. Labelling was LLM-assisted (Claude) and checked by hand. Labels follow the masking policy in the README. For example, "State Bank of India" is labelled because it is the company's banker (a counterparty), while "SEBI" and "National Securities Depository Limited" are not.
3. **Matching** (`eval/evaluate.py`): detection runs on the whole document, then predictions are compared with the gold spans of the sampled paragraphs. A prediction matches a gold span if the two **overlap**.
   - **Redaction view:** the label is ignored. This is the privacy question: "was this text replaced?"
   - **Per-type view:** the label must also agree.
4. **Accuracy** is reported at **token level**: each whitespace token in the sample is PII or not, in the gold labels and in the predictions, and accuracy is the share of tokens where the two agree. Entity-level accuracy is not defined for span detection, because there is no countable set of true negatives.
5. **Leakage scan** over the **whole** redacted document: every real value the script detected anywhere (231 distinct values), plus every gold value, is searched for in the output.

**No tuning on the sample.** The misses below were found by this evaluation and deliberately left unfixed, so the numbers measure the system as designed rather than a system fitted to its own test set.

## Results

100 paragraphs, 2,016 tokens, 63 gold PII spans in 33 paragraphs.

| PII type | Gold | Predicted | Precision | Recall | F1 |
|---|---|---|---|---|---|
| **All PII (redaction view)** | 63 | 55 | **100.0%** | **87.3%** | **93.2%** |
| ADDRESS | 5 | 4 | 100.0% | 80.0% | 88.9% |
| EMAIL | 11 | 11 | 100.0% | 100.0% | 100.0% |
| LOCATION | 1 | 1 | 100.0% | 100.0% | 100.0% |
| ORGANIZATION | 20 | 13 | 100.0% | 65.0% | 78.8% |
| PERSON | 14 | 14 | 100.0% | 100.0% | 100.0% |
| PHONE | 3 | 3 | 100.0% | 100.0% | 100.0% |
| REGISTRATION_ID | 4 | 4 | 100.0% | 100.0% | 100.0% |
| URL | 5 | 5 | 100.0% | 100.0% | 100.0% |

- **Token-level accuracy: 98.91%** (1,994 / 2,016 tokens).
- **Leakage:** 0 of the 231 detected real values appear anywhere in the redacted output.
- **Not in the sample:** PAN, Aadhaar, SSN, credit card, IP and date of birth do not occur in the document's text. They appear only inside the two ID-card images, which are replaced entirely. These detectors are covered by unit tests instead (`tests/test_detectors.py`), including checksum rejection of look-alikes.

## Error analysis

**False positives: none in the sample.** Precision comes from the conservative rules:
- validators (checksums, holder-type letters);
- phone numbers accepted only with a phone signal;
- dates of birth only when labelled as such;
- the "never lower-case in this document" test for names;
- the allow-list for regulators.

**False negatives (8 spans, 4 distinct issues):**

| Missed | Why | Fix |
|---|---|---|
| "CARE" in "CARE Report" (×4), "CareEdge Research" (×2) | Brand of the industry-report provider used **without** a legal suffix. "Care" is also an English word, so single-word matching for it is disabled to protect precision. | Treat a token as a brand when it appears in an organisation name **and** in ALL-CAPS or CamelCase form elsewhere ("CARE", "CareEdge"). |
| "State Bank of India" | Excluded on purpose by the weak-suffix rule (organisations ending in "Bank" need a rare word); every word here is common. | A small list of known bank names, or NER ORG accepted when the entity also has a website or email nearby. |
| "2401 Gen Thimmayya Road, Cantonment" | An address line with no PIN code and only one address keyword. | Accept a line that starts with a house number and directly follows a company name in the same table cell. |

**Partial matches:** "105215W/ W100057" (an auditor's firm registration number) is caught only as "105215". It counts as a hit by overlap, but "W/ W100057" stays in the output. The ID pattern should allow a letter suffix and a "/ W…" continuation.

## Limitations

- The sample covers 100 of about 4,200 paragraphs and skips paragraphs over 700 characters. Long prose paragraphs are where names are densest, so recall there is checked only indirectly, through the whole-document leakage scan.
- The leakage scan can only confirm that *detected* values were removed. Missed entities (the false negatives above) are by definition not in that list. The gold values found in the output (CARE, CareEdge Research, State Bank of India, the Cantonment address) are exactly the false negatives.
- Ground truth was produced by one annotator with LLM assistance. A second independent annotator would let us measure inter-annotator agreement.

## Reproduce

```bash
python eval/sample.py "doc/Red Herring Prospectus (6).docx" eval/sample.jsonl   # already committed
python -m redactor "doc/Red Herring Prospectus (6).docx" -o "output/Red Herring Prospectus - redacted.docx"
python eval/evaluate.py "doc/Red Herring Prospectus (6).docx" "output/Red Herring Prospectus - redacted.docx"
```
