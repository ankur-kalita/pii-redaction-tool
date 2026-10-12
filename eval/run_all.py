"""Redact and score every test set.

Usage: python eval/run_all.py
"""
import subprocess
import sys

PROSPECTUS = "doc/Red Herring Prospectus (6).docx"
PROSPECTUS_OUT = "output/Red Herring Prospectus - redacted.docx"
EXTERNAL = [
    "2018-1337",
    "Personally-Identifiable-Information-Security-Procedure-2018",
    "detecting-government-issued-pii-IJERTV15IS051137",
]

# (name, input, output, sample, ground truth, results)
TEST_SETS = [
    ("prospectus", PROSPECTUS, PROSPECTUS_OUT, "eval/sample.jsonl", "eval/ground_truth.jsonl", "eval/results.json"),
    ("prospectus held-out", PROSPECTUS, PROSPECTUS_OUT, "eval/sample_holdout.jsonl",
     "eval/ground_truth_holdout.jsonl", "eval/results_holdout.json"),
    ("nist", "eval/nist/nist.docx", "eval/nist/nist_redacted.docx", "eval/nist/sample.jsonl",
     "eval/nist/ground_truth.jsonl", "eval/nist/results.json"),
    ("tickets", "eval/tickets/tickets.docx", "eval/tickets/tickets_redacted.docx", "eval/tickets/sample.jsonl",
     "eval/tickets/ground_truth.jsonl", "eval/tickets/results.json"),
] + [
    (name, f"eval/external/{name}/doc.docx", f"eval/external/{name}/redacted.docx",
     f"eval/external/{name}/sample.jsonl", f"eval/external/{name}/ground_truth.jsonl",
     f"eval/external/{name}/results.json")
    for name in EXTERNAL
]


def run(*args: str) -> str:
    return subprocess.run([sys.executable, *args], capture_output=True, text=True, check=True).stdout


def main() -> None:
    redacted = set()
    for name, doc, out, sample, gold, results in TEST_SETS:
        if out not in redacted:
            run("-m", "redactor", doc, "-o", out)
            redacted.add(out)
        summary = next(line for line in run("eval/evaluate.py", doc, out, sample, gold, results).splitlines()
                       if line.startswith("| **All PII"))
        precision, recall, f1 = summary.strip("| ").split(" | ")[3:6]
        print(f"{name:<62} P {precision:>6}  R {recall:>6}  F1 {f1:>6}")


if __name__ == "__main__":
    main()
