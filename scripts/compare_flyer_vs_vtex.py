"""Compare flyer (encarte) prices with the VTEX price search.

For every offer extracted from a store's flyers, match it against the VTEX
catalog and compare:
    encarte varejo/atacado  vs  VTEX catalog price / VTEX simulation
    encarte app / cartao    vs  VTEX regionalized price

Usage: python scripts/compare_flyer_vs_vtex.py [storeId] [cep]
"""
from __future__ import annotations

import difflib
import json
import re
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://apigw.cloud.carrefour.com.br/api-middleware-flyer-services"
SEARCH_URL = "https://atacadaobr.vtexcommercestable.com.br/api/catalog_system/pub/products/search"
SIMULATION_URL = "https://www.atacadao.com.br/api/checkout/pub/orderForms/simulation"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0 Safari/537.36"
REPORT = Path(r"C:\Android\capture\encarte_vs_vtex.md")

sys.path.insert(0, str(Path(__file__).parent))
from flyer_offers_poc import flyer_offers  # noqa: E402


def norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(c for c in value if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", value)).strip()


def request(url: str, data: bytes | None = None) -> tuple[int, bytes]:
    headers = {"User-Agent": UA, "Accept": "application/json, text/plain, */*"}
    if data:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def catalog_match(name: str) -> dict | None:
    url = f"{SEARCH_URL}?ft={urllib.parse.quote(name)}&_from=0&_to=9"
    status, body = request(url)
    if status not in (200, 206):
        return None
    rows = json.loads(body.decode("utf-8", "replace"))
    target = norm(name)
    best: tuple[float, dict] | None = None
    for row in rows:
        for item in row.get("items") or []:
            ratio = difflib.SequenceMatcher(
                None, target, norm(str(row.get("productName") or ""))
            ).ratio()
            prices = [
                float(offer.get("Price") or 0)
                for seller in (item.get("sellers") or [])
                if (offer := seller.get("commertialOffer") or {}).get("Price")
            ]
            payload = {
                "productName": row.get("productName"),
                "skuId": str(item.get("itemId")),
                "ean": item.get("ean"),
                "catalogPrice": round(max(prices), 2) if prices else None,
                "ratio": round(ratio, 3),
            }
            if best is None or ratio > best[0]:
                best = (ratio, payload)
    return best[1] if best else None


def simulate(sku_ids: list[str], seller: str | None, cep: str | None = None) -> dict[str, float]:
    out: dict[str, float] = {}
    for start in range(0, len(sku_ids), 100):
        chunk = sku_ids[start : start + 100]
        body: dict = {
            "items": [{"id": sku, "quantity": 1, **({"seller": seller} if seller else {})} for sku in chunk],
            "country": "BRA",
        }
        if cep:
            body["postalCode"] = cep
        status, raw = request(f"{SIMULATION_URL}?sc=1", json.dumps(body).encode())
        if status != 200:
            continue
        for row in json.loads(raw.decode("utf-8", "replace")).get("items") or []:
            price = row.get("price")
            if price:
                out[str(row.get("id"))] = round(price / 100, 2)
    return out


def fmt(value: float | None) -> str:
    return f"{value:.2f}".replace(".", ",") if value else "—"


def main() -> None:
    store_id = int(sys.argv[1]) if len(sys.argv) > 1 else 632
    cep = sys.argv[2] if len(sys.argv) > 2 else None
    store = json.loads(request(f"{BASE}/api/v2/Store/{store_id}?api-version=2")[1].decode())
    print(f"loja {store['storeId']} {store['loja']} | CEP {store['cep']}")

    offers: list[dict] = []
    seen: set[str] = set()
    for flyer in store.get("flyers", []):
        for offer in flyer_offers(flyer["urlFinalDocument"]):
            key = norm(offer["product"])[:60]
            if key in seen:
                continue
            seen.add(key)
            offers.append({"flyer": flyer["name"], **offer})
    print(f"ofertas extraidas do encarte: {len(offers)}")

    matched = []
    for offer in offers:
        hit = catalog_match(offer["product"])
        if hit and hit["ratio"] >= 0.62:
            matched.append({"offer": offer, "vtex": hit})
    print(f"casadas no catalogo VTEX (ratio>=0.62): {len(matched)}")

    skus = [entry["vtex"]["skuId"] for entry in matched]
    sim_base = simulate(skus, "1")
    sim_cep = simulate(skus, "1", cep) if cep else {}

    lines = [
        f"# Encarte (loja {store['storeId']} {store['loja']}) vs VTEX",
        "",
        f"CEP da loja: {store['cep']}" + (f" · simulação com CEP {cep}" if cep else ""),
        "",
        "| produto (encarte) | varejo | app | cartão | VTEX catálogo | VTEX sim | VTEX sim CEP | igual? |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    stats = {"igual_vtex": 0, "app": 0, "cartao": 0, "diferente": 0, "sem_preco": 0}
    buckets = {
        "alta": {"total": 0, "igual": 0},
        "media": {"total": 0, "igual": 0},
        "baixa": {"total": 0, "igual": 0},
    }

    for entry in matched:
        offer, vtex = entry["offer"], entry["vtex"]
        sku = vtex["skuId"]
        sim = sim_base.get(sku)
        sim_c = sim_cep.get(sku)
        reference = sim if sim is not None else vtex["catalogPrice"]
        verdict = "?"
        if reference is None:
            stats["sem_preco"] += 1
            verdict = "s/ preço"
        elif offer.get("varejo") is not None and abs(reference - offer["varejo"]) <= 0.02:
            stats["igual_vtex"] += 1
            verdict = "= varejo"
        elif offer.get("app") is not None and abs(reference - offer["app"]) <= 0.02:
            stats["app"] += 1
            verdict = "= app"
        elif offer.get("cartao") is not None and abs(reference - offer["cartao"]) <= 0.02:
            stats["cartao"] += 1
            verdict = "= cartão"
        else:
            stats["diferente"] += 1
            verdict = "≠"
        bucket = "alta" if vtex["ratio"] >= 0.85 else ("media" if vtex["ratio"] >= 0.72 else "baixa")
        buckets[bucket]["total"] += 1
        if verdict == "= varejo":
            buckets[bucket]["igual"] += 1
        lines.append(
            f"| {offer['product']} | {fmt(offer.get('varejo'))} | {fmt(offer.get('app'))} "
            f"| {fmt(offer.get('cartao'))} | {fmt(vtex['catalogPrice'])} | {fmt(sim)} "
            f"| {fmt(sim_c)} | {verdict} ({vtex['ratio']}) |"
        )

    total = len(matched)
    confidence = "\n".join(
        f"match {level:<6} (n={data['total']:>3}): varejo==VTEX em {data['igual']} "
        f"({(100 * data['igual'] / data['total']):.0f}%)"
        for level, data in buckets.items()
        if data["total"]
    )
    summary = (
        f"\n{confidence}\n"
        f"\nVTEX == varejo do encarte: {stats['igual_vtex']}/{total}\n"
        f"VTEX == app do encarte:    {stats['app']}/{total}\n"
        f"VTEX == cartão do encarte: {stats['cartao']}/{total}\n"
        f"VTEX diferente:            {stats['diferente']}/{total}\n"
        f"sem preço na VTEX:         {stats['sem_preco']}/{total}"
    )
    print(summary)
    REPORT.write_text("\n".join(lines) + "\n" + summary, encoding="utf-8")
    print(f"relatorio completo: {REPORT}")


if __name__ == "__main__":
    main()
