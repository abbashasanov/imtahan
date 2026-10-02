import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()

import pymupdf
from exams.services.pdf_parser import HEADER_BAND, _clip_text, _question_heads

path = r"C:\Users\user\PycharmProjects\imtahan\_pdfcheck\grade1.pdf"
out = r"C:\Users\user\PycharmProjects\imtahan\_pdfcheck\g1p10.txt"
with pymupdf.open(path) as doc, open(out, "w", encoding="utf-8") as handle:
    page = doc[9]
    mid = page.rect.width / 2
    handle.write(f"heads {_question_heads(page)}\n")
    left = _clip_text(page, pymupdf.Rect(0, HEADER_BAND, mid - 6, page.rect.height))
    right = _clip_text(
        page, pymupdf.Rect(mid + 6, HEADER_BAND, page.rect.width, page.rect.height)
    )
    handle.write("LEFT\n" + left + "\n\nRIGHT\n" + right)
print("wrote")
