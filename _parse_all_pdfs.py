import glob
import os
import sys
import traceback

sys.stdout.reconfigure(encoding="utf-8")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()

from exams.services.pdf_parser import extract_pdf_text, parse_questions, ParseError

out_dir = r"C:\Users\user\PycharmProjects\imtahan\_pdfcheck"
os.makedirs(out_dir, exist_ok=True)

wanted = [
    ("g5", 400_000, 700_000, "5ci"),
    ("g6", 400_000, 700_000, "6ci"),
    ("g7", 400_000, 700_000, "7ci"),
    ("g3", 5_000_000, 7_000_000, "3-c"),
    ("g4", 6_000_000, 9_000_000, "4-c"),
    ("g2", 10_000_000, 14_000_000, "2-ci sinif.pdf"),
    ("g1", 14_000_000, 20_000_000, "1-ci"),
]

pdfs = glob.glob(r"C:\Users\user\Downloads\*.pdf")
picked = []
used = set()
for key, lo, hi, needle in wanted:
    for path in pdfs:
        if path in used:
            continue
        size = os.path.getsize(path)
        name = os.path.basename(path)
        if lo <= size <= hi and needle.lower() in name.lower().replace("ü", "u").replace("\u0308", ""):
            picked.append((key, path, size))
            used.add(path)
            break
        if lo <= size <= hi and needle[:3] in name:
            picked.append((key, path, size))
            used.add(path)
            break

print("picked", [(k, os.path.basename(p), s) for k, p, s in picked])

summary_path = os.path.join(out_dir, "parse_summary.txt")
with open(summary_path, "w", encoding="utf-8") as summary:
    for key, path, size in picked:
        print("parsing", key, size)
        try:
            questions = parse_questions(extract_pdf_text(path))
        except Exception as exc:
            traceback.print_exc()
            summary.write(f"{key} FAIL {exc}\n")
            continue
        numbers = [q["number"] for q in questions]
        missing = [n for n in range(min(numbers), max(numbers) + 1) if n not in numbers] if numbers else []
        line = f"{key} count={len(questions)} numbers={numbers} missing={missing}\n"
        print(line.strip())
        summary.write(line)
        dump = os.path.join(out_dir, f"parsed_{key}.txt")
        with open(dump, "w", encoding="utf-8") as handle:
            handle.write(f"count={len(questions)} numbers={numbers}\n\n")
            for q in questions:
                letters = "".join(c["letter"] for c in q["choices"])
                handle.write(f"===== Q{q['number']} {letters} =====\n{q['text'][:200]}\n")
                for c in q["choices"]:
                    handle.write(f"  {c['letter']}) {c['text'][:100]}\n")
                handle.write("\n")
print("done")
