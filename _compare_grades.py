import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()

from exams.services.pdf_parser import extract_pdf_text, parse_questions, QUESTION_START

base = r"C:\Users\user\PycharmProjects\imtahan\_pdfcheck"
out_dir = os.path.join(base, "dump")
os.makedirs(out_dir, exist_ok=True)

for name in ("grade1.pdf", "grade2.pdf", "grade3.pdf", "grade4.pdf"):
    path = os.path.join(base, name)
    print("===", name, "size", os.path.getsize(path), flush=True)
    text = extract_pdf_text(path)
    raw_matches = [m.group(1) for m in QUESTION_START.finditer(text)]
    questions = parse_questions(text)
    numbers = [q["number"] for q in questions]
    expected = list(range(1, numbers[-1] + 1)) if numbers else []
    missing = [n for n in expected if n not in numbers]
    mixed = []
    for q in questions:
        letters = [c["letter"] for c in q["choices"]]
        text_blob = " ".join(c["text"] for c in q["choices"])
        if any(x in text_blob for x in ("Natiq", " 22.", " 29.", "Mətnə əsasən")):
            mixed.append(q["number"])
        if letters and letters != sorted(letters):
            mixed.append(q["number"])
    report = [
        f"raw_starts={len(raw_matches)} {raw_matches[:15]}...{raw_matches[-8:]}",
        f"parsed={len(questions)} numbers={numbers}",
        f"missing={missing}",
        f"last={numbers[-1] if numbers else None}",
    ]
    print("\n".join(report), flush=True)
    dump_path = os.path.join(out_dir, name.replace(".pdf", ".txt"))
    with open(dump_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(report) + "\n\n")
        for q in questions:
            letters = "".join(c["letter"] for c in q["choices"])
            handle.write(f"===== Q{q['number']} n={len(q['choices'])} {letters} =====\n")
            handle.write((q["text"] or "")[:300] + "\n")
            for c in q["choices"]:
                handle.write(f"  {c['letter']}) {(c['text'] or '')[:140]}\n")
            handle.write("\n")
print("done")
