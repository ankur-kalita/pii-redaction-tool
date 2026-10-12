"""Score the detector on a token-labelled PII dataset (CSV).

Usage: python eval/pii_dataset/evaluate_csv.py doc/pii_dataset.csv RESULTS.json [all|dev|test]

The rows are split at random (fixed seed) into a dev half, used to find
errors, and a test half, scored once at the end.

Each row is its own document: `tokens`, `trailing_whitespace` and BIO
`labels` give the gold spans. Dataset labels map to ours; USERNAME has no
detector here and counts as missed. The dataset labels only the planted
person and has no company or place labels, so precision is also reported
"in scope": predictions of types the dataset labels.
"""

import ast
import csv
import json
import random
import sys
from collections import Counter

sys.path.insert(0, ".")
from eval.evaluate import overlaps, prf  # noqa: E402
from redactor.pipeline import Redactor  # noqa: E402

LABELS = {
    "NAME_STUDENT": "PERSON",
    "EMAIL": "EMAIL",
    "PHONE_NUM": "PHONE",
    "STREET_ADDRESS": "ADDRESS",
    "URL_PERSONAL": "URL",
    "USERNAME": "USERNAME",
}


def gold_spans(row: dict) -> list[tuple[int, int, str]]:
    """BIO token labels -> character spans, without trailing punctuation."""
    tokens, spaces, tags = (ast.literal_eval(row[k]) for k in ("tokens", "trailing_whitespace", "labels"))
    spans, pos = [], 0
    for token, space, tag in zip(tokens, spaces, tags, strict=True):
        if tag.startswith("B-") or (tag.startswith("I-") and not spans):
            spans.append([pos, pos + len(token), LABELS[tag[2:]]])
        elif tag.startswith("I-"):
            spans[-1][1] = pos + len(token)
        pos += len(token) + space
    text = row["text"]
    out = []
    for start, end, label in spans:
        while end > start and text[end - 1] in ".,;:!?)\"'":
            end -= 1
        out.append((start, end, label))
    return out


def split(rows: list[dict], part: str) -> list[dict]:
    if part == "all":
        return rows
    order = list(range(len(rows)))
    random.Random(42).shuffle(order)
    half = order[: len(rows) // 2] if part == "dev" else order[len(rows) // 2 :]
    return [rows[i] for i in sorted(half)]


def main(csv_path: str, results_path: str, part: str = "all") -> None:
    csv.field_size_limit(sys.maxsize)
    with open(csv_path, newline="") as f:
        rows = split(list(csv.DictReader(f)), part)
    redactor = Redactor()
    counts = {label: Counter() for label in [*LABELS.values(), "(all)", "(in scope)"]}
    errors = {"fn": [], "fp": []}
    tok_agree = tok_total = 0
    for row in rows:
        text = row["text"]
        gold = gold_spans(row)
        _, (pred,) = redactor.detect([text])
        pred = [(s.start, s.end, s.label) for s in pred]
        for g in gold:
            hit = any(overlaps(g, p) for p in pred)
            for label in ("(all)", g[2]):
                counts[label]["gold"] += 1
                counts[label]["gold_hit"] += hit
            if not hit:
                errors["fn"].append((g[2], text[g[0] : g[1]]))
        for p in pred:
            hit = any(overlaps(p, g) for g in gold)
            for view in ("(all)", "(in scope)") if p[2] in LABELS.values() else ("(all)",):
                counts[view]["pred"] += 1
                counts[view]["pred_hit"] += hit
            if not hit:
                errors["fp"].append((p[2], text[p[0] : p[1]], text[max(0, p[0] - 50) : p[1] + 30]))
        for token_start in range(len(text)):
            if text[token_start].isspace() or (token_start and not text[token_start - 1].isspace()):
                continue
            token_end = token_start
            while token_end < len(text) and not text[token_end].isspace():
                token_end += 1
            t = (token_start, token_end)
            tok_agree += any(overlaps(t, g) for g in gold) == any(overlaps(t, p) for p in pred)
            tok_total += 1

    lines = ["| PII type | Gold | Recall |", "|---|---|---|"]
    for label in LABELS.values():
        c = counts[label]
        lines.append(f"| {label} | {c['gold']} | {c['gold_hit'] / c['gold']:.1%} |")
    c, scoped = counts["(all)"], counts["(in scope)"]
    p, r, f = prf(c["pred_hit"], c["pred"], c["gold_hit"], c["gold"])
    sp, _, sf = prf(scoped["pred_hit"], scoped["pred"], c["gold_hit"], c["gold"])
    report = {
        "documents": len(rows),
        "overall": f"precision {p:.1%}, recall {r:.1%}, F1 {f:.1%}",
        "in_scope": f"precision {sp:.1%}, recall {r:.1%}, F1 {sf:.1%}",
        "token_accuracy": f"{tok_agree / tok_total:.2%} ({tok_agree}/{tok_total} tokens)",
        "recall_by_type": "\n".join(lines),
        "false_negatives": Counter(label for label, _ in errors["fn"]).most_common(),
        "false_negative_examples": errors["fn"][:60],
        "false_positives": Counter(label for label, *_ in errors["fp"]).most_common(),
        "false_positive_examples": errors["fp"][:80],
    }
    with open(results_path, "w") as out:
        json.dump(report, out, indent=1, ensure_ascii=False)
    print(f"{len(rows)} documents: {report['overall']}; token accuracy {report['token_accuracy']}")
    print(f"in scope (PII types the dataset labels): {report['in_scope']}")
    print(report["recall_by_type"])
    print("False negatives by type:", report["false_negatives"])
    print("False positives by type:", report["false_positives"])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], *sys.argv[3:4])
