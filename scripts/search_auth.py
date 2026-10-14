import re

path = r"C:\Users\Wellz\AppData\Local\Temp\atacadao-xapk\libapp_strings.txt"
with open(path, encoding="utf-8", errors="replace") as fh:
    lines = [ln.rstrip("\n") for ln in fh]

kws = ["OfertaMobile-TokenAuth", "kcc-ofertas-externo", "skadi", "realms",
       "openid-connect", "grant_type", "client_credentials", "client_secret",
       "OfertasMobilesDev", "freyr.portal", "tyr.portal", "portal.atacadao"]

for kw in kws:
    hits = [(i, ln) for i, ln in enumerate(lines) if kw in ln and len(ln) < 300]
    print(f"===== {kw} ({len(hits)}) =====")
    for i, ln in hits[:12]:
        print(f"  [{i}] {ln.strip()}")
        # print short context
        for j in range(max(0, i - 3), min(len(lines), i + 4)):
            if j != i and len(lines[j]) < 200:
                print(f"       . {lines[j].strip()}")
