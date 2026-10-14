import urllib.error
import urllib.request

urls = [
    "https://freyr.portal.atacadao.com.br/mobile/ofertas-backoffice/v1/busca-loja-via-cep/v2?cep=13184-668",
    "https://freyr.portal.atacadao.com.br/mobile/ofertas-transacional/v1/vitrine/mobile/v2?cep=13184-668",
]
for u in urls:
    req = urllib.request.Request(u)
    req.add_header("User-Agent", "okhttp/4.12.0")
    req.add_header("Accept", "application/json")
    req.add_header("Origin", "https://www.atacadao.com.br")
    req.add_header("Referer", "https://www.atacadao.com.br/")
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            print("OK", u, r.status, r.read()[:300])
    except urllib.error.HTTPError as e:
        print("ERR", u, e.code, dict(e.headers))
        print("   body:", e.read()[:300])
    except Exception as e:
        print("ERR", u, repr(e)[:200])
