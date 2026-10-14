"""Repeat the Remote Config fetch with fresh installations.

If the missing credentials (`in_store_offers_api_key`,
`in_store_offers_backoffice_client_secret`, `in_store_offers_backoffice_password`)
sit behind a Firebase RC rollout / random-percentile condition, a different
Firebase Installation ID lands in a different bucket and the parameter shows up.
"""
from __future__ import annotations

import json
import secrets
import sys
import urllib.error
import urllib.request

PROJECT = "atacadao-b6521"
APP_ID = "1:579536695495:android:3af4b608ce65ef651a4ee2"
API_KEY = "AIzaSyChy2c53_XP1jN6NGS3Qoi1Jv0GG7J_A90"
PACKAGE = "br.com.atacadao.b2c.app"
CERT_SHA1 = "97B1257A29CBA1049C4B1F2D4DE3DBE5B1262040"
APP_VERSION = "13.429.1"
INTERESTING = ("secret", "password", "api_key", "in_store")


def post(url: str, body: dict, headers: dict) -> tuple[int, object]:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode(errors="replace")
    except Exception as exc:  # noqa: BLE001
        return 0, str(exc)


def fetch(index: int) -> tuple[set[str], dict, str]:
    fid = secrets.token_urlsafe(17)[:22]
    status, res = post(
        f"https://firebaseinstallations.googleapis.com/v1/projects/{PROJECT}/installations",
        {"appId": APP_ID, "authVersion": "FIS_v2", "fid": fid, "sdkVersion": "a:17.0.0"},
        {
            "x-goog-api-key": API_KEY,
            "X-Android-Package": PACKAGE,
            "X-Android-Cert": CERT_SHA1,
            "Content-Type": "application/json",
        },
    )
    if status != 200 or not isinstance(res, dict):
        print(f"  [{index}] FIS failed {status} {str(res)[:120]}")
        return set(), {}, fid
    token = res["authToken"]["token"]
    status2, res2 = post(
        f"https://firebaseremoteconfig.googleapis.com/v1/projects/{PROJECT}"
        f"/namespaces/firebase:fetch?key={API_KEY}",
        {
            "app_instance_id": fid,
            "app_instance_id_token": token,
            "app_id": APP_ID,
            "app_version": APP_VERSION,
            "app_build": "130429001",
            "country_code": "BR",
            "language_code": "pt-BR",
            "platform_version": "33",
            "time_zone": "America/Sao_Paulo",
            "package_name": PACKAGE,
            "sdk_version": "22.0.0",
            "analytics_user_properties": {},
        },
        {
            "X-Goog-Firebase-Installations-Auth": token,
            "x-goog-api-key": API_KEY,
            "X-Android-Package": PACKAGE,
            "X-Android-Cert": CERT_SHA1,
            "Content-Type": "application/json",
        },
    )
    if not isinstance(res2, dict) or "entries" not in res2:
        print(f"  [{index}] RC failed {status2} {str(res2)[:160]}")
        return set(), {}, fid
    entries = res2["entries"]
    print(
        f"  [{index}] entries={len(entries)} templateVersion={res2.get('templateVersion')}"
        f" state={res2.get('state')}"
    )
    return set(entries), entries, fid


def main() -> None:
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 25
    union: set[str] = set()
    values: dict[str, str] = {}
    for i in range(1, rounds + 1):
        keys, entries, fid = fetch(i)
        new = keys - union
        union |= keys
        values.update(entries)
        if new:
            print(f"      NEW KEYS: {sorted(new)}")
        for k, v in entries.items():
            if any(t in k.lower() for t in INTERESTING):
                print(f"      {k} = {v!r}")
    print(f"\nunion keys: {len(union)}")
    with open(r"C:\Android\capture\rc_union.json", "w", encoding="utf-8") as fh:
        json.dump(values, fh, ensure_ascii=False, indent=2)
    print("wrote C:\\Android\\capture\\rc_union.json")


if __name__ == "__main__":
    main()
