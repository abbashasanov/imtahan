import glob
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()

from exams.services.pdf_parser import _pymupdf_text, parse_questions, _question_heads
import pymupdf

def pick(needles):
    for path in glob.glob(r"C:\Users\user\Downloads\*.pdf"):
        name = os.path.basename(path).lower().replace("ü", "u").replace("\u0308", "")
        if all(n in name for n in needles):
            return path
    return None

files = [
    ("g1", ["1-ci"]),
    ("g2", ["2-ci"]),
    ("g3", ["3-c"]),
    ("g4", ["4-c"]),
    ("g5", ["5ci"]),
]
for key, needles in files:
    path = pick(needles)
    if not path:
        print(key, "NOT FOUND")
        continue
    print("====", key, os.path.basename(path), os.path.getsize(path))
    if key in {"g1", "g2", "g4"}:
        doc = pymupdf.open(path)
        print("pages", doc.page_count)
        for i, page in enumerate(doc):
            heads = _question_heads(page)
            mid = page.rect.width / 2
            left = [n for n, x, y, y1 in heads if x < mid]
            right = [n for n, x, y, y1 in heads if x >= mid]
            print(f" p{i+1} L={left} R={right}")
        data = open(path, "rb").read()
        doc.close()
    else:
        data = open(path, "rb").read()
    text, cols = _pymupdf_text(data)
    qs = parse_questions(text)
    nums = [q["number"] for q in qs]
    missing = [n for n in range(min(nums), max(nums) + 1) if n not in nums]
    print("cols", cols, "count", len(qs), "last", nums[-1], "missing", missing)
    print("numbers", nums)
    if key == "g5":
        q7 = next(q for q in qs if q["number"] == 7)
        print("Q7", "".join(c["letter"] for c in q7["choices"]), q7["text"][:80], [c["text"][:40] for c in q7["choices"]])
        q11 = next(q for q in qs if q["number"] == 11)
        print("Q11D", q11["choices"][-1]["text"][:80])
