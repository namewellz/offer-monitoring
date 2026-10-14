"""Fetch Firebase Remote Config values for the Atacadão app via the public FIS + RC REST APIs."""
import json
import secrets
import urllib.error
import urllib.request

PROJECT = "atacadao-b6521"
APP_ID = "1:579536695495:android:3af4b608ce65ef651a4ee2"
API_KEY = "AIzaSyChy2c53_XP1jN6NGS3Qoi1Jv0GG7J_A90"
PACKAGE = "br.com.atacadao.b2c.app"
CERT_SHA1 = "97B1257A29CBA1049C4B1F2D4DE3DBE5B1262040"  # uppercase, no colons
APP_VERSION = "13.429.1"


def _fid() -> str:
    return secrets.token_urlsafe(17)[:22]


def _post(url, body, headers):
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode(errors="replace")


def main():
    fid = _fid()
    print("fid:", fid)

    status, result = _post(
        f"https://firebaseinstallations.googleapis.com/v1/projects/{PROJECT}/installations",
        {"appId": APP_ID, "authVersion": "FIS_v2", "fid": fid, "sdkVersion": "a:17.0.0"},
        {
            "x-goog-api-key": API_KEY,
            "X-Android-Package": PACKAGE,
            "X-Android-Cert": CERT_SHA1,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    print("installations status:", status)
    print(json.dumps(result, indent=2)[:1500])
    if status != 200:
        return
    token = result["authToken"]["token"]

    status2, result2 = _post(
        f"https://firebaseremoteconfig.googleapis.com/v1/projects/{PROJECT}/namespaces/firebase:fetch?key={API_KEY}",
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
            "Accept": "application/json",
        },
    )
    print("remoteconfig status:", status2)
    if isinstance(result2, dict):
        entries = result2.get("entries", {})
        print(f"entries: {len(entries)}")
        with open(r"C:\Android\capture\remote_config.json", "w", encoding="utf-8") as fh:
            json.dump(result2, fh, ensure_ascii=False, indent=2)
        for key in sorted(entries):
            if any(t in key.lower() for t in ("offer", "mercaf", "zanthus", "propz", "api", "store", "seller", "region")):
                print(f"  {key} = {str(entries[key])[:200]}")
    else:
        print(str(result2)[:1000])


if __name__ == "__main__":
    main()
