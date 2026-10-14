"""POC: read in-store (flyer) offers per Atacadao store.

Source: the public Carrefour/Atacadao flyer-services API that backs
https://www.atacadao.com.br/institucional/nossas-lojas. No credentials.

    GET /api/v2/Store/all?api-version=2            -> every store
    GET /api/v2/Store/{storeId}?api-version=2      -> store + its flyers
    GET /api/v2/Flyer/?id={flyerId}                -> flyer PDF (has a text layer)

The flyer PDF is a grid: each column holds [product image] + [price block] +
[product name/description]. The price block carries up to three tiers:
  * PREÇO VAREJO/ATACADO
  * PREÇO COM OFERTA ATIVADA NO APP
  * PREÇO COM OFERTA ATIVADA NO APP/CARTÃO (Atacadao, Carrefour, Sam's Club)
"""
from __future__ import annotations

import io
import json
import re
import sys
import unicodedata
import urllib.error
import urllib.request

import pymupdf

BASE = "https://apigw.cloud.carrefour.com.br/api-middleware-flyer-services"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/139.0 Safari/537.36"
)
PRICE_RE = re.compile(r"^R\$\s?\d{1,4}(?:[.,]\d{2})?$")
LABEL_WORDS = {
    "PREÇO", "PRECO", "VAREJO/ATACADO", "COM", "OFERTA", "ATIVADA", "NO", "APP",
    "PAGANDO", "CARTÃO", "CARTAO", "ATACADÃO", "ATACADAO", "CARREFOUR", "OU",
    "SAM'S", "SAM’S", "CLUB", "Limite", "máximo", "maximo", "de", "un", "unidade",
    "por", "cliente", "nos", "cartões", "cartoes", "OFERTAÇO", "OFERTAÇO", "VERIFICADO",
    "DIA", "DO", "NAS", "NAS", "REDES", "SOCIAIS",
}


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def get_json(url: str) -> object:
    return json.loads(get(url).decode("utf-8", "replace"))


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text).strip().lower()


def money(token: str) -> float | None:
    m = re.match(r"^R\$\s?([\d.]+)(?:,(\d{2}))?$", token)
    if not m:
        return None
    whole = m.group(1).replace(".", "")
    cents = m.group(2) or "00"
    return float(f"{whole}.{cents}")


def page_offers(page: pymupdf.Page) -> list[dict]:
    """Split a flyer page into columns anchored on the 'PREÇO VAREJO/ATACADO' label."""
    words = [(w[0], w[1], w[2], w[3], w[4]) for w in page.get_text("words")]
    blocks = [(b[0], b[1], b[2], b[3], b[4]) for b in page.get_text("blocks")]

    anchors: list[tuple[float, float]] = []
    for x0, y0, x1, y1, text in words:
        if text.upper().startswith("VAREJO") and "/" in text:
            anchors.append((x0, y0))

    offers: list[dict] = []
    for ax, ay in anchors:
        left, right = ax - 70, ax + 70
        # price words belonging to this price block, ordered top -> bottom:
        # 1st = varejo/atacado, 2nd = oferta ativada no app, 3rd = app + cartao
        stacked: list[tuple[float, float]] = []
        for x0, y0, x1, y1, text in words:
            value = money(text)
            if value is None or not (left <= x0 <= right):
                continue
            dy = y0 - ay
            if 0 <= dy <= 200:
                stacked.append((dy, value))
        stacked.sort()
        tiers: dict[str, float | None] = {}
        for index, (_, value) in enumerate(stacked[:3]):
            tiers[("varejo", "app", "cartao")[index]] = value
        if not tiers:
            continue

        # product description: the text block sits LEFT of the price block, while
        # the price-block captions ("CARREFOUR OU", "Limite máximo ...") are centred
        # on the price column, so a centre-x filter separates them cleanly.
        name, best = "", None
        for x0, y0, x1, y1, text in blocks:
            cx = (x0 + x1) / 2
            if cx > ax + 5 or cx < left - 20:
                continue
            if y0 < ay - 40 or y0 > ay + 190:
                continue
            cleaned = " ".join(
                line.strip() for line in text.splitlines() if line.strip() and line.strip() not in LABEL_WORDS
            )
            cleaned = re.sub(r"R\$\s?[\d.,]+", "", cleaned).strip(" :-/")
            if len(cleaned) < 6 or not re.search(r"[A-Za-zÀ-ÿ]{3}", cleaned):
                continue
            score = len(cleaned)
            if best is None or score > best:
                best, name = score, cleaned
        if name:
            offers.append({"x": round(ax), "y": round(ay), "product": name, **tiers})
    return offers


def flyer_offers(pdf_url: str) -> list[dict]:
    doc = pymupdf.open(stream=get(pdf_url), filetype="pdf")
    out: list[dict] = []
    for number, page in enumerate(doc, 1):
        for offer in page_offers(page):
            out.append({"page": number, **offer})
    return out


def main() -> None:
    needle = norm(sys.argv[1]) if len(sys.argv) > 1 else "linguica toscana perdigao nabrasa"
    store_id = int(sys.argv[2]) if len(sys.argv) > 2 else 632

    stores = get_json(f"{BASE}/api/v2/Store/all?api-version=2")
    listing = stores.get("stores", stores) if isinstance(stores, dict) else stores
    print(f"total stores exposed by the API: {len(listing)}")

    store = get_json(f"{BASE}/api/v2/Store/{store_id}?api-version=2")
    print(
        f"store {store['storeId']} = {store['loja']} | {store['endereco']} {store['numero']}"
        f" - {store['bairro']}, {store['cidade']}/{store['estado']} | CEP {store['cep']}"
    )
    print(f"flyers available: {len(store.get('flyers', []))}")

    hits: list[dict] = []
    for flyer in store.get("flyers", []):
        name = flyer["name"]
        validity = flyer["validity"]
        url = flyer["urlFinalDocument"]
        try:
            offers = flyer_offers(url)
        except Exception as exc:  # noqa: BLE001
            print(f"  ! {name}: {exc}")
            continue
        print(f"  - {name} ({validity['initial'][:10]} .. {validity['final'][:10]}): {len(offers)} offers parsed")
        for offer in offers:
            if needle in norm(offer["product"]):
                hits.append({"flyer": name, "validity": validity, **offer})

    print(f"\n=== matches for {needle!r} ===")
    for hit in hits:
        print(
            f"  [{hit['flyer']} p{hit['page']} {hit['validity']['initial'][:10]}..{hit['validity']['final'][:10]}] "
            f"{hit['product']}"
        )
        print(
            f"      varejo/atacado R$ {hit.get('varejo')} | app R$ {hit.get('app')} | "
            f"app+cartao R$ {hit.get('cartao')}"
        )
    print(f"total matches: {len(hits)}")


if __name__ == "__main__":
    main()
