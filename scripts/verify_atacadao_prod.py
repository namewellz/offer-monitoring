"""Verificacao pos-deploy na Oracle (roda dentro do container de producao).

Confirma, contra a API real, que:
  * a credencial do app autentica a partir da rede da Oracle;
  * o catalogo de uma loja de Campinas responde (Hortolandia 632 e Americana 625,
    justamente as que a VTEX nao precificava);
  * o preco de gondola e as faixas de oferta do app chegam no mapeamento novo.
"""

import asyncio
import os

from app.catalog.atacadao import AtacadaoCatalogClient, parse_app_products


async def main() -> None:
    print("credencial no ambiente:", bool(os.environ.get("ATACADAO_APP_CLIENT_SECRET")))
    api = AtacadaoCatalogClient()
    client = api._make_client()
    try:
        print("token ok:", bool(await api.authenticate()))

        for city in ("hortolandia", "americana", "campinas"):
            stores = await api.find_stores([city])
            print(f"{city}: {[(s['filial'], s['name']) for s in stores]}")

        for filial in (632, 625):
            departments = await api.departments(filial)
            target = next(
                (d for d in departments if "carne" in str(d.get("category", "")).lower()),
                departments[0],
            )
            rows, errors = await api._department_products(
                client, asyncio.Semaphore(4), filial, target
            )
            products = parse_app_products(rows, target.get("category"))
            hits = [
                p
                for p in products
                if "toscana" in p.name.lower() and "perdig" in p.name.lower()
            ]
            print(
                f"filial {filial}: {len(departments)} departamentos | "
                f"{target.get('category')} -> {len(rows)} linhas, {len(errors)} erros"
            )
            for product in hits[:4]:
                tiers = ", ".join(f"{t.condition}={t.price}" for t in product.tier_prices)
                print(
                    f"   {product.id} {product.name[:46]:<46} "
                    f"regular={product.regular_price} sales={product.sales_price} "
                    f"oferta={tiers or '-'} disp={product.available} ean={product.ean}"
                )
    finally:
        await client.aclose()


asyncio.run(main())
