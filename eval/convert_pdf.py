"""Turn a PDF into a .docx the redactor can read: one Word
paragraph per text block from `pdftotext`. Formatting is irrelevant for
scoring detection.

Usage: python eval/convert_pdf.py INPUT.pdf OUTPUT.docx
"""

import re
import subprocess
import sys

import docx


def main(pdf: str, out: str) -> None:
    raw = subprocess.run(["pdftotext", pdf, "-"], capture_output=True, text=True, check=True).stdout
    d = docx.Document()
    for block in re.split(r"\n\s*\n|\f", raw):
        text = " ".join(line.strip() for line in block.splitlines() if line.strip())
        text = re.sub(r"(\w)- (\w)", r"\1-\2", text)
        if text:
            d.add_paragraph(text)
    d.save(out)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
