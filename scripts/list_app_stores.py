"""List the Meu Atacadao branches the app returns for a city / CEP.

Usage:
    python scripts/list_app_stores.py hortolandia campinas "santa barbara"
    python scripts/list_app_stores.py --cep 13184668
    python scripts/list_app_stores.py --region            # default RMC list, saves JSON

Saves the registry to C:\\Android\\capture\\app_stores.json so the catalog
collector can reuse the branch ids (filialId) without hardcoding them.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from atacadao_app_api import AppApiError, MeuAtacadaoAppApi  # noqa: E402

OUT = Path(r"C:\Android\capture")

# Cities covered by the current catalog runs (RMC + the Vila Maria reference store).
REGION_CITIES = [
    "sao paulo",
    "campinas",
    "hortolandia",
    "americana",
    "indaiatuba",
    "itu",
    "jundiai",
    "santa barbara d'oeste",
    "sumare",
    "valinhos",
    "vinhedo",
    "paulini",
    "mogi mirim",
    "piracicaba",
    "limeira",
    "rio claro",
    "araras",
    "sorocaba",
]


def rows(payload) -> list[dict]:
    if isinstance(payload, dict):
        for key in ("data", "content", "lojas", "stores", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
        return []
    return payload if isinstance(payload, list) else []


def main() -> None:
    arguments = sys.argv[1:]
    api = MeuAtacadaoAppApi()
    api.authenticate()
    print("token ok\n")

    registry: dict[str, dict] = {}
    if "--cep" in arguments:
        cep = arguments[arguments.index("--cep") + 1]
        payload = api.stores_by_cep(cep, page_size=20)
        print(f"CEP {cep}:")
        for row in rows(payload):
            print("  " + json.dumps(row, ensure_ascii=False))
            registry[str(row.get("idStore"))] = row
    else:
        cities = [c for c in arguments if not c.startswith("-")] or REGION_CITIES
        for city in cities:
            try:
                payload = api.stores_by_city(city, page_size=50)
            except AppApiError as exc:
                print(f"{city}: {exc}")
                continue
            found = rows(payload)
            print(f"{city}: {len(found)} loja(s)")
            for row in found:
                print(
                    f"   {row.get('idStore'):>5}  {row.get('storeName')}"
                    f"  | {row.get('address')}, {row.get('number')} - {row.get('neighborhood')}"
                    f"  | {row.get('city')}/{row.get('state')}  CEP {row.get('zipCode')}"
                    f"  | seller {row.get('vtexSellerId')} | ecommerce={row.get('ecommerce')}"
                )
                registry[str(row.get("idStore"))] = row

    if registry:
        OUT.mkdir(parents=True, exist_ok=True)
        path = OUT / "app_stores.json"
        existing = {}
        if path.exists():
            existing = {str(k): v for k, v in json.loads(path.read_text(encoding="utf-8")).items()}
        existing.update(registry)
        path.write_text(
            json.dumps(existing, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8"
        )
        print(f"\n{len(registry)} loja(s) -> {path} ({len(existing)} no total)")


if __name__ == "__main__":
    main()
