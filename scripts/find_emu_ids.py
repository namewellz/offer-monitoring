import re
import urllib.request

for url in [
    "https://dl.google.com/android/repository/repository2-1.xml",
    "https://dl.google.com/android/repository/repository2-3.xml",
]:
    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "Mozilla/5.0")
        data = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
    except Exception as exc:
        print(url, "ERR", exc)
        continue
    ids = sorted(set(int(x) for x in re.findall(r"emulator-windows_x64-(\d+)\.zip", data)))
    print(url, "->", len(ids), "build ids")
    print(" ", ids[-25:])
