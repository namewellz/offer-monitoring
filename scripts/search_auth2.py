path = r"C:\Users\Wellz\AppData\Local\Temp\atacadao-xapk\libapp_strings.txt"
with open(path, encoding="utf-8", errors="replace") as fh:
    lines = [ln.rstrip("\n").strip() for ln in fh]

anchors = ["infosec", "protocol/openid-connect", "in_store_offers_backoffice_client_secret",
           "IN_STORE_OFFERS_BACKOFFICE", "in_store_offers_backoffice_password",
           "offers_auth_chave", "BACKOFFICE_CLIENT"]
for a in anchors:
    idxs = [i for i, ln in enumerate(lines) if a in ln and len(ln) < 400]
    print(f"\n########## {a} -> {len(idxs)} hits ##########")
    for i in idxs[:4]:
        lo, hi = max(0, i - 35), min(len(lines), i + 36)
        print(f"--- around line {i} ---")
        for j in range(lo, hi):
            ln = lines[j]
            if 0 < len(ln) < 160:
                print(f"{'>>' if j == i else '  '} {ln}")
