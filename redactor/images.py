"""Images are replaced by same-size placeholders.

Logos, QR codes and scanned ID cards identify people and companies, and their
text is out of reach of the text detectors (no OCR), so every image goes.
"""

from __future__ import annotations

import io

from PIL import Image, ImageDraw

from .docx_io import DocxDocument

FORMATS = {".png": "PNG", ".jpeg": "JPEG", ".jpg": "JPEG", ".gif": "GIF", ".bmp": "BMP"}


def placeholder(original: bytes, fmt: str) -> bytes:
    with Image.open(io.BytesIO(original)) as img:
        size = img.size
    canvas = Image.new("RGB", size, (225, 225, 225))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([0, 0, size[0] - 1, size[1] - 1], outline=(150, 150, 150))
    label = "IMAGE REDACTED"
    w = draw.textlength(label)
    if w < size[0] - 4:
        draw.text(((size[0] - w) / 2, size[1] / 2 - 5), label, fill=(90, 90, 90))
    out = io.BytesIO()
    canvas.save(out, fmt)
    return out.getvalue()


def replace_images(doc: DocxDocument) -> int:
    count = 0
    for name, data in doc.media().items():
        ext = name[name.rfind(".") :].lower()
        if ext in FORMATS:
            doc.replace_media(name, placeholder(data, FORMATS[ext]))
            count += 1
    return count
