"""Probe which VTEX simulation variants return prices for the Hortolandia CEP."""
from __future__ import annotations

import json
import urllib.error
import urllib.request

SIM = "https://www.atacadao.com.br/api/checkout/pub/orderForms/simulation"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/139.0"

SKUS = ["59299", "60012", "63969"]  # Linguiça Toscana Perdigão Nabrasa (700g / kg / queijo coalho 600g)


def post(body: dict, sc: str = "1") -> tuple[int, str]:
    req = urllib.request.Request(
        f"{SIM}?sc={sc}",
        data=json.dumps(body).encode(),
        headers={"User-Agent": UA, "Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def show(label: str, body: dict, sc: str = "1") -> None:
    status, text = post(body, sc)
    if status != 200:
        print(f"  {label:<44} {status} {text[:130]}")
        return
    items = json.loads(text).get("items") or []
    rendered = [
        (
            i.get("id"),
            i.get("seller"),
            (i.get("price") or 0) / 100,
            i.get("availability"),
            (i.get("sellingPrice") or 0) / 100,
        )
        for i in items
    ]
    print(f"  {label:<44} 200 {rendered}")


def main() -> None:
    for cep in ("13184668", None):
        for seller in (None, "1", "atacadaobr632", "atacadaobr60", "atacadaobr662"):
            body = {
                "items": [
                    {"id": sku, "quantity": 1, **({"seller": seller} if seller else {})} for sku in SKUS
                ],
                "country": "BRA",
            }
            if cep:
                body["postalCode"] = cep
            show(f"cep={cep} seller={seller}", body)


if __name__ == "__main__":
    main()
