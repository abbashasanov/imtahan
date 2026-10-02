import glob
import os
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8")

dest_dir = r"C:\Users\user\PycharmProjects\imtahan\_pdfcheck"
os.makedirs(dest_dir, exist_ok=True)

mapping = {
    "1": "grade1.pdf",
    "2": "grade2.pdf",
    "3": "grade3.pdf",
    "4": "grade4.pdf",
}
for path in glob.glob(r"C:\Users\user\Downloads\*sinif*.pdf"):
    name = os.path.basename(path).lower()
    size = os.path.getsize(path)
    if "bilik" in name:
        continue
    key = None
    if name.startswith("1"):
        key = "1"
    elif name.startswith("2") and size > 1_000_000:
        key = "2"
    elif name.startswith("3") and size > 1_000_000:
        key = "3"
    elif name.startswith("4") and size > 1_000_000:
        key = "4"
    if key:
        dest = os.path.join(dest_dir, mapping[key])
        shutil.copyfile(path, dest)
        print(key, size, dest)
