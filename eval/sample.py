"""Draw the evaluation sample: a fixed, stratified set of paragraphs.

* random: 50 paragraphs drawn uniformly -> measures false positives on
  ordinary text.
* dense: 50 paragraphs that contain a cheap PII *signal* (an "@", "+91", a
  legal suffix, a 6-digit number, or two capitalised words in a row) ->
  measures recall where PII actually is. The signal is deliberately simpler
  than the detectors, so the sample is not biased toward what they find.

Usage: python eval/sample.py INPUT.docx OUT.jsonl [SEED] [EXCLUDE.jsonl]
A second, held-out sample (seed 8) excludes every paragraph of the first one.

Paragraphs longer than 700 characters are skipped to keep manual labelling
reliable (noted as a limitation in the report).
"""
import json
import random
import re
import sys

sys.path.insert(0, ".")
from redactor.docx_io import DocxDocument  # noqa: E402

SIGNAL = re.compile(r"@|\+\s?91|Limited|LLP|Trust\b|\b\d{3}\s?\d{3}\b|\b[A-Z][a-z]+\s+[A-Z][a-z]+")


def main(path: str, out: str, seed: int = 7, exclude: str | None = None) -> None:
    doc = DocxDocument(path)
    skip = set()
    if exclude:
        with open(exclude) as f:
            skip = {json.loads(line)["paragraph"] for line in f}
    pool = [p for p in doc.paragraphs if 25 <= len(p.text.strip()) <= 700 and p.uid not in skip]
    rng = random.Random(seed)
    random_part = rng.sample(pool, 50)
    taken = {p.uid for p in random_part}
    dense_pool = [p for p in pool if p.uid not in taken and SIGNAL.search(p.text)]
    dense_part = rng.sample(dense_pool, 50)
    with open(out, "w") as f:
        for stratum, paras in (("random", random_part), ("dense", dense_part)):
            for p in paras:
                f.write(json.dumps({"paragraph": p.uid, "stratum": stratum, "text": p.text}, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], *([int(sys.argv[3])] if len(sys.argv) > 3 else []), *sys.argv[4:5])
