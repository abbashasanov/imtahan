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
    QUESTION_START,
    _question_heads,
    _is_real_question_body,
    HEADER_BAND,
    _clip_text,
)

def diagnose(label, path, interesting):
    print(f"\n######## {label} ########", flush=True)
    with pymupdf.open(path) as doc:
        print("pages", doc.page_count)
        for i, page in enumerate(doc):
            heads = _question_heads(page)
            mid = page.rect.width / 2
            nums = [(n, "L" if x < mid else "R", round(x,1), round(y0,1)) for n,x,y0,y1 in heads]
            if any(n in interesting or n <= 3 for n, *_ in nums):
                print(f" p{i+1} heads {nums}")
    text = extract_pdf_text(path)
    matches = list(QUESTION_START.finditer(text))
    print("starts", [m.group(1) for m in matches])
    for index, match in enumerate(matches):
        num = int(match.group(1))
        if num not in interesting:
            continue
        end = matches[index + 1].start() if index + 1 < len(matches) else min(len(text), match.end() + 400)
        body = text[match.end():end]
        print(f"--- {num} real={_is_real_question_body(body)} indent={len(match.group(0))-len(match.group(0).lstrip())} ---")
        print(repr(body[:400]))
        print()

base = r"C:\Users\user\PycharmProjects\imtahan\_pdfcheck"
diagnose("G1", os.path.join(base, "grade1.pdf"), {48, 49, 50, 51})
diagnose("G2", os.path.join(base, "grade2.pdf"), {24, 25, 26, 30, 31, 32, 43, 44, 45})
diagnose("G4", os.path.join(base, "grade4.pdf"), {6, 7, 8, 9, 10, 11, 12, 15, 20, 21, 46, 47, 50, 1, 2, 3})
