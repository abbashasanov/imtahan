import glob
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()

from exams.services.pdf_parser import extract_pdf_text, parse_questions

def pick(needle):
    for path in glob.glob(r"C:\Users\user\Downloads\*.pdf"):
        if needle.lower() in os.path.basename(path).lower():
            return path
    return None

for key, needle in [("g5", "5ci"), ("g6", "6ci"), ("g7", "7ci")]:
    path = pick(needle)
    print("====", key, os.path.basename(path))
    qs = parse_questions(extract_pdf_text(path))
    nums = [q["number"] for q in qs]
    missing = [n for n in range(min(nums), max(nums) + 1) if n not in nums] if nums else []
    print("count", len(qs), "last", nums[-1] if nums else None, "missing", missing)
    print("numbers", nums)
    for q in qs:
        if q["number"] in {7, 11, 12, 22, 28, 36, 46, 50, 51, 60}:
            letters = "".join(c["letter"] for c in q["choices"])
            d = (q["choices"][-1]["text"][:80] if q["choices"] else "")
            print(f"  Q{q['number']} {letters} | {q['text'][:90]} | D={d}")
