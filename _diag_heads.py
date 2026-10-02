import glob
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()

import pymupdf
from exams.services.pdf_parser import _question_heads, QUESTION_START, extract_pdf_text

def pick(needle):
    for path in glob.glob(r"C:\Users\user\Downloads\*.pdf"):
        name = os.path.basename(path).lower()
        if needle in name:
            return path
    return None

for key, needle in [("g5", "5ci"), ("g6", "6ci"), ("g7", "7ci")]:
    path = pick(needle)
    print("\n########", key, path)
    doc = pymupdf.open(path)
    print("pages", doc.page_count)
    for i, page in enumerate(doc):
        heads = _question_heads(page)
        mid = page.rect.width / 2
        left = [n for n, x, y, y1 in heads if x < mid]
        right = [n for n, x, y, y1 in heads if x >= mid]
        ys = [(n, round(x), round(y)) for n, x, y, y1 in heads]
        print(f" p{i+1} L={left} R={right} ys={ys}")
    doc.close()
    text = extract_pdf_text(path)
    starts = [m.group(1) for m in QUESTION_START.finditer(text)]
    print(" raw_starts", starts)
