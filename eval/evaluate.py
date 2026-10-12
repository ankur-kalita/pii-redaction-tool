"""Score the redactor against the hand-labelled ground truth.

Usage: python eval/evaluate.py INPUT.docx REDACTED.docx [SAMPLE GOLD RESULTS]
(defaults: eval/sample.jsonl eval/ground_truth.jsonl eval/results.json; the
held-out set is eval/sample_holdout.jsonl eval/ground_truth_holdout.jsonl)

* Detection is run on the whole document (the catalogue needs the full text),
  then predictions are compared with gold labels on the sampled paragraphs.
* A prediction matches a gold span if they overlap. Two views are reported:
  - "redaction": label ignored. This is what matters for privacy (was the
    text replaced at all?).
  - per type: the label must also agree.
* Token accuracy: every whitespace token in the sample is PII or not, in gold
  and in prediction; accuracy = share of tokens where both agree. (Entity-level
  "accuracy" is undefined because there is no countable set of true
  negatives, so we define it at token level.)
* Leakage: every real value the script detected anywhere in the document, and
  every gold value, is searched for in the redacted output.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, ".")
from redactor.docx_io import DocxDocument
from redactor.pipeline import Redactor


def load_gold(sample: list[dict], path: str) -> dict[str, list[tuple[int, int, str, str]]]:
    """Gold entries are (paragraph, label, text); expand to every occurrence of
    the text in that paragraph, dropping occurrences inside a longer gold span."""
    texts = {s["paragraph"]: s["text"] for s in sample}
    raw = defaultdict(set)
    with open(path) as f:
        for line in f:
            g = json.loads(line)
            raw[g["paragraph"]].add((g["label"], g["text"]))
    gold = {}
    for uid, items in raw.items():
        spans = []
        for label, value in sorted(items, key=lambda x: -len(x[1])):
            for m in re.finditer(re.escape(value), texts[uid]):
                if all(m.end() <= s or m.start() >= e for s, e, _, _ in spans):
                    spans.append((m.start(), m.end(), label, value))
        gold[uid] = spans
    return gold


def overlaps(a, b) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def prf(tp_p: int, n_pred: int, tp_g: int, n_gold: int) -> tuple[float, float, float]:
    p = tp_p / n_pred if n_pred else 1.0
    r = tp_g / n_gold if n_gold else 1.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def main(input_path: str, redacted_path: str, sample_path: str = "eval/sample.jsonl",
         gold_path: str = "eval/ground_truth.jsonl", results_path: str = "eval/results.json") -> None:
    with open(sample_path) as f:
        sample = [json.loads(line) for line in f]
    gold = load_gold(sample, gold_path)

    doc = DocxDocument(input_path)
    redactor = Redactor()
    _, per_par = redactor.detect([p.text for p in doc.paragraphs])
    pred_by_uid = {p.uid: [(s.start, s.end, s.label, s.text) for s in spans] for p, spans in zip(doc.paragraphs, per_par)}

    labels = sorted({g[2] for spans in gold.values() for g in spans} | {"(all)"})
    counts = {l: Counter() for l in labels}
    errors = {"fn": [], "fp": []}
    tok_agree = tok_total = 0

    for s in sample:
        uid, text = s["paragraph"], s["text"]
        g_spans = gold.get(uid, [])
        p_spans = pred_by_uid.get(uid, [])
        # redaction view (label-agnostic) and typed view
        for g in g_spans:
            hit_any = any(overlaps(g, p) for p in p_spans)
            hit_typed = any(overlaps(g, p) and p[2] == g[2] for p in p_spans)
            counts["(all)"]["gold"] += 1
            counts["(all)"]["gold_hit"] += hit_any
            counts[g[2]]["gold"] += 1
            counts[g[2]]["gold_hit"] += hit_typed
            if not hit_any:
                errors["fn"].append((g[2], g[3], text[max(0, g[0] - 40): g[1] + 20]))
        for p in p_spans:
            hit_any = any(overlaps(p, g) for g in g_spans)
            counts["(all)"]["pred"] += 1
            counts["(all)"]["pred_hit"] += hit_any
            if p[2] in counts:
                counts[p[2]]["pred"] += 1
                counts[p[2]]["pred_hit"] += any(overlaps(p, g) and p[2] == g[2] for g in g_spans)
            if not hit_any:
                errors["fp"].append((p[2], p[3], text[max(0, p[0] - 40): p[1] + 20]))
        # token-level accuracy
        for m in re.finditer(r"\S+", text):
            t = (m.start(), m.end())
            in_gold = any(overlaps(t, g) for g in g_spans)
            in_pred = any(overlaps(t, p) for p in p_spans)
            tok_agree += in_gold == in_pred
            tok_total += 1

    # leakage over the whole redacted document
    out_text = "\n".join(p.text for p in DocxDocument(redacted_path).paragraphs)
    detected_values = {sp[3] for spans in pred_by_uid.values() for sp in spans if sp[2] != "ADDRESS" and len(sp[3]) > 3}
    leaked_detected = sorted(v for v in detected_values if re.search(r"(?<!\w)" + re.escape(v) + r"(?!\w)", out_text))
    gold_values = {g[3] for spans in gold.values() for g in spans}
    leaked_gold = sorted(v for v in gold_values if v in out_text)

    lines = ["| PII type | Gold | Predicted | Precision | Recall | F1 |", "|---|---|---|---|---|---|"]
    for l in ["(all)"] + [x for x in labels if x != "(all)"]:
        c = counts[l]
        p, r, f = prf(c["pred_hit"], c["pred"], c["gold_hit"], c["gold"])
        name = "**All PII (redaction view)**" if l == "(all)" else l
        lines.append(f"| {name} | {c['gold']} | {c['pred']} | {p:.1%} | {r:.1%} | {f:.1%} |")
    report = {
        "table": "\n".join(lines),
        "token_accuracy": f"{tok_agree / tok_total:.2%} ({tok_agree}/{tok_total} tokens)",
        "paragraphs": len(sample),
        "gold_entities": counts["(all)"]["gold"],
        "false_negatives": errors["fn"],
        "false_positives": errors["fp"],
        "leaked_detected_values": leaked_detected,
        "leaked_gold_values": leaked_gold,
        "detected_values_checked": len(detected_values),
    }
    with open(results_path, "w") as f:
        json.dump(report, f, indent=1, ensure_ascii=False)
    print(report["table"])
    print("Token accuracy:", report["token_accuracy"])
    print("False negatives:", *errors["fn"], sep="\n  ")
    print("False positives:", *errors["fp"], sep="\n  ")
    print(f"Leakage: {len(leaked_detected)} of {len(detected_values)} detected values still in output; gold values still in output: {leaked_gold}")


if __name__ == "__main__":
    main(*sys.argv[1:6])
