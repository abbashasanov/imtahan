import glob
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

live_dir = r"C:\Users\user\PycharmProjects\imtahan\_pdfcheck"
print("=== LIVE ===")
for path in sorted(glob.glob(os.path.join(live_dir, "live_*.html"))):
    if "home" in os.path.basename(path):
        continue
    html = open(path, encoding="utf-8").read()
    title = re.search(r"<title>(.*?)</title>", html, re.S)
    numbers = [int(n) for n in re.findall(r"<h3[^>]*>\s*(\d+)\.", html)]
    if not numbers:
        numbers = [int(n) for n, _t in re.findall(r"<h[23][^>]*>\s*(\d+)\.\s*([^<]+)", html)]
    expected = list(range(min(numbers), max(numbers) + 1)) if numbers else []
    missing = [n for n in expected if n not in numbers]
    print(
        f"{os.path.basename(path)} title={(title.group(1).strip() if title else '?')!r} "
        f"count={len(numbers)} min={numbers[0] if numbers else None} max={numbers[-1] if numbers else None} "
        f"gaps={missing[:30]}{'...' if len(missing)>30 else ''}"
    )
    # mix signals: a choice containing another question-like number
    mix = re.findall(r"(?:choice|option|q-choice)[^<]{0,40}(\d{1,3}\.\s)", html[:50000], re.I)
    # dump first 8 stems
    stems = re.findall(r"<h3[^>]*>\s*(\d+)\.\s*([^<]{0,80})", html)
    for n, t in stems[:6]:
        print(f"  {n}. {re.sub(r'\s+', ' ', t).strip()[:70]}")
    print()
