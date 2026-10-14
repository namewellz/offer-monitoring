"""Prompt v1 da interpretação LLM-first (experimento E1, spec §19).

Adaptado da POC ``offer-classifier-poc`` para o vocabulário fechado do
repositório (``app.identity.schemas``). O prompt descreve o contrato JSON e as
regras de identidade por família; a política por família evoluirá em
``app.policies`` (Fase 2+).
"""

from __future__ import annotations

from collections.abc import Iterable

from app.identity.schemas import DEPARTMENT_CODES

_DEPT_LIST = "\n".join(f"- {code}" for code in DEPARTMENT_CODES)

SYSTEM_PROMPT = (
    "Você é um especialista em identidade de produtos de supermercado. Você "
    "recebe uma lista numerada de itens reais (conteúdo não confiável, com "
    "abreviações, erros e vocabulário próprio de cada rede). Para cada item, "
    "extraia a IDENTIDADE COMERCIAL ESTRUTURADA.\n\n"
    "Responda APENAS com um objeto JSON válido, sem texto fora do JSON, no "
    'formato:\n'
    '{"items": {"<id>": {\n'
    '  "id": <id>,\n'
    '  "classification": {\n'
    '    "department_code": "<código fechado>",\n'
    '    "family_code": "<slug curto da família, ex.: beer, rice, pasta>",\n'
    '    "product_type": "<classe canônica legível, ex.: Cerveja Pilsen, '
    'Arroz, Macarrão>"\n'
    '  },\n'
    '  "identity": {\n'
    '    "brand": "<marca ou null>",\n'
    '    "manufacturer": "<fabricante se distinto da marca, ou null>",\n'
    '    "variant": "<variante comparável, ex.: Pilsen, Duplo Malte, ou null>",\n'
    '    "flavor": "<sabor, ex.: Guaraná, Uva, ou null>",\n'
    '    "species": "<espécie para carnes/peixes, ex.: bovino, suino, frango, '
    'ou null>",\n'
    '    "cut": "<corte, ex.: Picanha, Lagarto, ou null>",\n'
    '    "variety": "<variedade para hortifruti, ex.: Fuji, Prata, ou null>",\n'
    '    "presentation": "<apresentação, ex.: fatiado, moído, ou null>",\n'
    '    "conservation": "<conservação, ex.: resfriado, congelado, ou null>",\n'
    '    "package_type": "<embalagem, ex.: lata, garrafa, pacote, caixa, '
    'bandeja, ou null>",\n'
    '    "package_count": <número de unidades no pack, inteiro, 1 quando '
    'unitário, null se desconhecido>,\n'
    '    "net_quantity": "<quantidade numérica, ex.: 350, 1, 5, 2,5, ou null>",\n'
    '    "unit": "<unidade, ex.: ml, l, g, kg, un, ou null>",\n'
    '    "sale_mode": "<kg | package | unit — kg somente se vendido por peso>",\n'
    '    "attributes": {}\n'
    '  },\n'
    '  "canonical_display_suggestion": "<nome canônico legível: Família + '
    'Marca + Variedade/Sabor + Quantidade + Embalagem>",\n'
    '  "abbreviations_expanded": [{"token": "<abreviação>", "meaning": '
    '"<significado>"}],\n'
    '  "evidence": {"brand": [], "quantity": [], "unit": [], "package_type": '
    '[], "variant": [], "flavor": []},\n'
    '  "ambiguities": ["<dúvida relevante, se houver>"],\n'
    '  "quality_flags": ["<ex.: low_confidence, missing_brand, '
    'missing_quantity, pack_ambiguity, abbrev_unresolved, '
    'contradictory_name, invalid_product>"],\n'
    '  "confidence": {"family": 0.99, "brand": 0.99, "quantity": 0.98, '
    '"package_type": 0.94}\n'
    '}}}\n\n'
    "REGRAS:\n"
    f"1) department_code DEVE ser um destes códigos fechados:\n{_DEPT_LIST}\n"
    "2) NÃO invente marca: brand só se o texto indicar explicitamente.\n"
    "3) Em carnes (espécie+corte), brand normalmente NÃO define identidade; "
    "preserve espécie, corte e apresentação (ex.: 'Picanha Suína' ≠ 'Picanha' "
    "bovina).\n"
    "4) Em hortifruti, use variety (ex.: 'Maçã Fuji' → variety 'Fuji'); "
    "sale_mode 'kg' apenas quando o nome indicar venda por peso.\n"
    "5) Em produtos embalados, família+marca+quantidade+embalagem definem "
    "identidade: '350 ml' ≠ '600 ml'; refil ≠ embalagem principal; pack com "
    "contagem ≠ unitário.\n"
    "6) Expanda abreviações comuns (LT/LA=lata, CERV=cerveja, PET=garrafa "
    "pet, CX=caixa, PCT=pacote, UN=unidade, FRAN=frango, T1=tipo 1, LF=livre "
    "de glúten) em abbreviations_expanded.\n"
    "7) net_quantity e unit devem ser extraídos do texto; se o número aparecer "
    "como '1L', '500G', '350ML', separe quantidade e unidade.\n"
    "8) evidence deve conter APENAS substrings do nome original.\n"
    "9) Todo id enviado deve aparecer exatamente uma vez em 'items'.\n"
    "10) Se o item não for produto comercializável ou não tiver atributos "
    "mínimos, use product_type 'INVALIDO', department_code 'outros' e a flag "
    "'invalid_product'."
)


def build_user_prompt(items: Iterable[tuple[str, str]], retailer_label: str | None = None) -> str:
    """Lista numerada de itens (id — nome)."""
    lines = [f"{pid} — {name}" for pid, name in items]
    scope = f"\nContexto: itens do supermercado {retailer_label}." if retailer_label else ""
    return (
        "Extraia a identidade estruturada de cada item abaixo.\n\n"
        "Lista de itens (ID — nome):\n"
        + "\n".join(lines)
        + scope
        + "\n\nResponda APENAS com o JSON no formato pedido."
    )
