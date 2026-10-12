"""Command line: python -m redactor INPUT.docx -o OUTPUT.docx"""
from __future__ import annotations

import argparse
import json
from collections import Counter

from .pipeline import Redactor


def main() -> None:
    ap = argparse.ArgumentParser(description="Replace PII in a .docx with consistent fake values.")
    ap.add_argument("input")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--secret", default="evaratus-redaction", help="key for deterministic fakes; change it to get different fakes")
    ap.add_argument("--findings", help="write every detection (contains REAL PII, keep private) as JSON lines")
    ap.add_argument("--mapping", help="write the real->fake mapping (contains REAL PII, keep private)")
    args = ap.parse_args()

    result = Redactor(secret=args.secret).redact(args.input, args.output)

    counts = Counter(f.span.label for f in result.findings)
    print(f"Wrote {args.output}")
    for label, n in counts.most_common():
        print(f"  {label:<16}{n}")
    print(f"  {'IMAGES':<16}{result.images_replaced}")

    if args.findings:
        with open(args.findings, "w") as f:
            for x in result.findings:
                f.write(json.dumps({"paragraph": x.paragraph, "label": x.span.label, "start": x.span.start,
                                    "end": x.span.end, "text": x.span.text, "replacement": x.replacement}) + "\n")
    if args.mapping:
        with open(args.mapping, "w") as f:
            json.dump(result.mapping, f, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
