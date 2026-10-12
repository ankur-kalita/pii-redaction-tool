"""Build every test document, redact it and score it.

Usage: python eval/run_all.py

Inputs come from doc/ (the prospectus and the public PDFs, not committed) or
are generated (the ticket log); converted inputs and redacted copies go to
eval/.work/. Only the hand-made labels and the results live in the repo.
"""

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, ".")
from eval.convert_pdf import main as convert_pdf  # noqa: E402
from eval.tickets.generate import main as generate_tickets  # noqa: E402

WORK = Path("eval/.work")
PROSPECTUS = "doc/Red Herring Prospectus (6).docx"
PROSPECTUS_OUT = "output/Red Herring Prospectus - redacted.docx"
PDFS = {
    "nist": "doc/nistspecialpublication800-122.pdf",
    "ml_paper": "doc/2018-1337.pdf",
    "capri_policy": "doc/Personally-Identifiable-Information-Security-Procedure-2018.pdf",
    "ijert_paper": "doc/detecting-government-issued-pii-IJERTV15IS051137.pdf",
}
# A fixed key keeps the committed outputs reproducible.
ENV = {**os.environ, "REDACTOR_SECRET": "evaratus-redaction"}


def run(*args: str) -> str:
    return subprocess.run([sys.executable, *args], capture_output=True, text=True, check=True, env=ENV).stdout


def score(name: str, doc: str, redacted: str, folder: str, prefix: str = "", sample: bool = False) -> None:
    args = [doc, redacted, f"eval/{folder}/{prefix}ground_truth.jsonl", f"eval/{folder}/{prefix}results.json"]
    if sample:
        args += ["--sample", f"eval/{folder}/{prefix}sample.jsonl"]
    summary = next(line for line in run("eval/evaluate.py", *args).splitlines() if line.startswith("| **All PII"))
    precision, recall, f1 = summary.strip("| ").split(" | ")[3:6]
    print(f"{name:<22} P {precision:>6}  R {recall:>6}  F1 {f1:>6}")


def main() -> None:
    WORK.mkdir(exist_ok=True)
    run("-m", "redactor", PROSPECTUS, "-o", PROSPECTUS_OUT)
    score("prospectus", PROSPECTUS, PROSPECTUS_OUT, "prospectus", sample=True)
    score("prospectus held-out", PROSPECTUS, PROSPECTUS_OUT, "prospectus", "holdout_", sample=True)

    tickets = str(WORK / "tickets.docx")
    generate_tickets(tickets, "eval/tickets/ground_truth.jsonl")
    run("-m", "redactor", tickets, "-o", str(WORK / "tickets_redacted.docx"))
    score("tickets", tickets, str(WORK / "tickets_redacted.docx"), "tickets")

    for name, pdf in PDFS.items():
        doc, redacted = str(WORK / f"{name}.docx"), str(WORK / f"{name}_redacted.docx")
        convert_pdf(pdf, doc)
        run("-m", "redactor", doc, "-o", redacted)
        score(name, doc, redacted, name)


if __name__ == "__main__":
    main()
