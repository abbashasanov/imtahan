import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()

import pymupdf
from exams.services.pdf_parser import (
    QUESTION_START,
    decode_azlat,
    extract_pdf_text,
    parse_questions,
    _question_heads,
    _is_real_question_body,
    _drop_inner_numbered_lists,
    _prepare,
)

path = r"C:\Users\user\Downloads\1-ci sinif.pdf.pdf"
print("exists", os.path.exists(path), os.path.getsize(path))

doc = pymupdf.open(path)
print("pages", doc.page_count)
for i, page in enumerate(doc):
    if i + 1 < 8:
        continue
    heads = _question_heads(page)
    mid = page.rect.width / 2
    left = [(n, round(x), round(y)) for n, x, y, y1 in heads if x < mid]
    right = [(n, round(x), round(y)) for n, x, y, y1 in heads if x >= mid]
    print(f"\n=== p{i+1} L={left} R={right}")
    extra = []
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            raw = "".join(span.get("text", "") for span in line.get("spans", []))
            dec = decode_azlat(raw)
            if any(ch.isdigit() for ch in dec) or QUESTION_START.match(dec):
                bbox = [round(v) for v in (line.get("bbox") or [0, 0, 0, 0])]
                extra.append((repr(dec.strip()[:70]), bbox))
    for item in extra:
        print(" ", item)

qs = parse_questions(extract_pdf_text(path))
nums = [q["number"] for q in qs]
print("\nparsed count", len(qs), "nums", nums)
print("missing 1-60", [n for n in range(1, 61) if n not in nums])
for q in qs:
    if 43 <= q["number"] <= 52:
        letters = "".join(c["letter"] for c in q["choices"])
        print(f"\n===== Q{q['number']} {letters} =====")
        print(q["text"][:250])
        for c in q["choices"]:
            print(f"  {c['letter']}) {c['text'][:80]}")

text = extract_pdf_text(path)
norm = _prepare(text)
matches = list(QUESTION_START.finditer(norm))
print("\nRAW STARTS", [m.group(1) for m in matches])
kept = _drop_inner_numbered_lists(matches, norm)
print("KEPT", [m.group(1) for m in kept])
for index, match in enumerate(kept):
    n = int(match.group(1))
    if n not in {44, 45, 46, 47, 48, 49, 50, 51}:
        continue
    end = kept[index + 1].start() if index + 1 < len(kept) else min(len(norm), match.end() + 500)
    body = norm[match.end() : end]
    print(f"--- kept {n} real={_is_real_question_body(body)} ---")
    print(repr(body[:400]))
doc.close()
