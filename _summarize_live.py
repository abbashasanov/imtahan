import re
import glob
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
base = r"C:\Users\user\PycharmProjects\imtahan\_pdfcheck"
for path in glob.glob(os.path.join(base, "live_*.html")):
    html = open(path, encoding="utf-8").read()
    title = re.search(r"<title>(.*?)</title>", html, re.S)
    numbers = [int(n) for n in re.findall(r"<h3[^>]*>\s*(\d+)\.", html)]
    if not numbers:
        numbers = [int(n) for n, _t in re.findall(r"<h[23][^>]*>\s*(\d+)\.\s*([^<]+)", html)]
    missing = [n for n in range(1, (max(numbers) if numbers else 1) + 1) if n not in numbers]
    print(os.path.basename(path))
    print(" title", (title.group(1).strip() if title else "?"))
    print(" count", len(numbers), "max", max(numbers) if numbers else None)
    print(" numbers", numbers)
    print(" missing", missing)
    print()
