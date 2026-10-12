# Evaluation report

## Summary

| | Sample | Precision | Recall | F1 | Token accuracy |
|---|---|---|---|---|---|
| Round 1: first version, first sample | 100 paragraphs, 63 PII spans | 100.0% | 87.3% | 93.2% | 98.91% |
| Round 2: fixed version, **held-out sample** (headline) | 100 new paragraphs, 36 PII spans | **94.7%** | **100.0%** | **97.3%** | **99.12%** |

**Leakage:** 0 of the 234 real values the script detected remain anywhere in the redacted document.

The headline is Round 2. Round 1 found 4 problems. I fixed them with general rules, then measured on a **new sample the fixes had never seen**, labelled before running the tool on it. The first sample now scores 100% on every metric, but that number is not reported as a result, because the fixes were made by looking at that sample's errors.

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
# how the samples were drawn (already committed)
python eval/sample.py "doc/Red Herring Prospectus (6).docx" eval/sample.jsonl 7
python eval/sample.py "doc/Red Herring Prospectus (6).docx" eval/sample_holdout.jsonl 8 eval/sample.jsonl
```
