import json

rc = json.load(open(r"C:\Android\capture\remote_config.json", encoding="utf-8"))["entries"]
print("=== ALL REMOTE CONFIG KEYS (399) ===")
for k in sorted(rc):
    print(" ", k)

print("\n=== searching libapp for env-var names ===")
path = r"C:\Users\Wellz\AppData\Local\Temp\atacadao-xapk\libapp_strings.txt"
with open(path, encoding="utf-8", errors="replace") as fh:
    lines = [ln.rstrip("\n") for ln in fh]
for kw in ["IN_STORE_OFFERS_BACKOFFICE", "BACKOFFICE_CLIENT_SECRET", "BACKOFFICE_PASSWORD",
           "OFFERS_BACKOFFICE", "dart_defines", "DART_DEFINES", "String.fromEnvironment",
           "IN_STORE_OFFERS_API_KEY"]:
    hits = [ln for ln in lines if kw in ln]
    print(f"  {kw}: {len(hits)}")
    for h in hits[:5]:
        print("     ", h[:200])
