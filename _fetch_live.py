import re
import sys
import urllib.parse
import urllib.request
import http.cookiejar

sys.stdout.reconfigure(encoding="utf-8")

BASE = "https://parentlink.az/exam"
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
opener.addheaders = [("User-Agent", "Mozilla/5.0")]

login_page = opener.open(BASE + "/accounts/login/").read().decode("utf-8", "replace")
csrf = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', login_page)
if not csrf:
    raise SystemExit("no csrf")
data = urllib.parse.urlencode(
    {
        "csrfmiddlewaretoken": csrf.group(1),
        "username": "test",
        "password": "Test1234?",
        "next": "/",
    }
).encode()
req = urllib.request.Request(
    BASE + "/accounts/login/",
    data=data,
    headers={"Referer": BASE + "/accounts/login/"},
)
resp = opener.open(req)
print("after login", resp.geturl(), resp.status)

home = opener.open(BASE + "/").read().decode("utf-8", "replace")
print("home title matches", re.findall(r"<h[12][^>]*>.*?</h[12]>", home, re.S)[:8])
# exam links
links = sorted(set(re.findall(r'href="([^"]*exams/\d+/[^"]*)"', home)))
print("exam links", links)
open(r"C:\Users\user\PycharmProjects\imtahan\_pdfcheck\live_home.html", "w", encoding="utf-8").write(home)

for path in links:
    url = path if path.startswith("http") else (BASE + path if path.startswith("/") else BASE + "/" + path)
    # site is mounted at /exam/ so path may already include /exam/
    if path.startswith("/exam/"):
        url = "https://parentlink.az" + path
    elif path.startswith("/exams/"):
        url = BASE + path
    print("fetch", url)
    try:
        page = opener.open(url).read().decode("utf-8", "replace")
    except Exception as exc:
        print(" fail", exc)
        continue
    title = re.search(r"<title>(.*?)</title>", page, re.S)
    qheads = re.findall(r"<h[23][^>]*>\s*(\d+)\.\s*([^<]+)", page)
    qnums = re.findall(r'(?:Sual|question)[^\d]*(\d+)', page, re.I)
    numbers = [int(n) for n, _t in qheads]
    print(" title", title.group(1).strip() if title else None)
    print(" qheads", len(qheads), numbers[:20], "..." if len(numbers) > 20 else "")
    fname = re.sub(r"\W+", "_", (title.group(1) if title else path))[:40]
    open(rf"C:\Users\user\PycharmProjects\imtahan\_pdfcheck\live_{fname}.html", "w", encoding="utf-8").write(page)
print("done")
