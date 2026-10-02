import glob
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()

import pymupdf
from exams.services.pdf_parser import (
    extract_pdf_text,
    parse_questions,
    _question_heads,
    _pymupdf_page_text,
    QUESTION_START,
)

pdfs = glob.glob(r"C:\Users\user\Downloads\*5ci*.pdf")
print("files", pdfs)
path = pdfs[0]
print("using", path, os.path.getsize(path))

doc = pymupdf.open(path)
print("pages", doc.page_count)
for i, page in enumerate(doc):
    heads = _question_heads(page)
    mid = page.rect.width / 2
    left = [(n, round(x), round(y)) for n, x, y, y1 in heads if x < mid]
    right = [(n, round(x), round(y)) for n, x, y, y1 in heads if x >= mid]
    text, cols = _pymupdf_page_text(page)
    print(f"\n=== PAGE {i+1} {page.rect} cols={cols} heads={len(heads)}")
    print("LEFT", left)
    print("RIGHT", right)
    print("TEXT SAMPLE:\n", text[:800].replace("\n", " | "))
    if i >= 3:
        break
doc.close()

text = extract_pdf_text(path)
starts = [m.group(1) for m in QUESTION_START.finditer(text)]
print("\nRAW STARTS", len(starts), starts)
qs = parse_questions(text)
print("PARSED", [q["number"] for q in qs])
