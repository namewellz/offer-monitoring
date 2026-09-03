"""Prompt builders + definitions of the meat product lines we classify.

Each *line* is a canonical product that retailers sell in several presentations
(ex.: Bacon). The deterministic parser mis-groups many items that merely carry
the meat word as a flavour/ingredient, so we ask the LLM to pick, from a list of
candidate products (sent with their internal ids), which ones are truly that
product. The reply only returns ids, so results can be related back to the DB.
"""

from __future__ import annotations

from app.classification.canonical import CANONICAL_CATEGORIES

# The meat lines supported today. ``keywords`` drives candidate collection
# (any raw name containing one of them), ``definition`` + ``examples`` teach the
# LLM what the real product looks like, and ``flavours`` names the usual false
# positives (products that only use the meat as flavour/ingredient).
MEAT_LINES: dict[str, dict] = {
    "bacon": {
        "label": "Bacon",
        "keywords": ("bacon",),
        "definition": (
            "produto cárneo suíno (defumado/curado): fatias, manta, mantinha, "
            "tablete, pedaço, meia-manta, bandeja, em cubos, extra paleta. "
            "O nome normalmente começa com 'bacon' (ou 'carne suína bacon')."
        ),
        "flavours": (
            "produtos prontos/industrializados que usam bacon apenas como sabor ou "
            "ingrediente secundário: macarrão/mac'n cheese, massas (rondelli), "
            "salgadinhos, biscoitos, geleia, catchup, tempero/caldo, lanche "
            "(x-bacon), pururuca/porks rinds, petisco canino, pizza, etc."
        ),
        "retailer_scope": None,  # None = todas as redes
    },
}

# Canonical definition used by all lines: the system role.
SYSTEM_PROMPT = (
    "Você é um especialista em classificação de produtos de supermercado "
    "(departamento de açougue/frios). Você recebe uma lista numerada de itens "
    "reais, cada um com um ID inteiro. Sua tarefa é decidir, para a linha de "
    "produto pedida, quais itens SÃO de fato esse produto. Responda APENAS com "
    "um objeto JSON válido no formato: "
    '{"accepted_ids": [ids que SÃO o produto], "rejected_ids": [ids que NÃO são], '
    '"reasons": {"<id>": "motivo curto"}} — reasons opcional, em português. '
    "Todo ID enviado deve aparecer em accepted_ids OU rejected_ids, sem duplicar."
)


def build_user_prompt(
    line: dict,
    items: list[tuple[int, str]],
    retailer_label: str | None = None,
) -> str:
    """Numbered item list + per-line instruction (mirrors the Bacon example)."""
    lines = []
    for pid, name in items:
        lines.append(f"{pid} — {name}")
    scope = f"\nContexto: itens do supermercado {retailer_label}." if retailer_label else ""

    return (
        f"Identifique quais destes itens se trata de {line['label']} e quais são "
        f"falsos positivos. Quero apenas o que for {line['label']} de fato.\n\n"
        f"Definição de {line['label']} de verdade: {line['definition']}\n\n"
        f"ATENÇÃO — falsos positivos: {line['flavours']}. "
        "Esses devem ir para rejected_ids.\n\n"
        f"Lista de itens (ID — nome):\n" + "\n".join(lines) + scope +
        "\n\nResponda com o JSON no formato pedido."
    )


# Categories commonly expected when classifying the Açougue department. They are
# only *examples*: the model may propose a short canonical label when needed, but
# must be consistent (same product in different stores = same label).
ACOUGUE_CATEGORY_EXAMPLES = (
    "Bacon", "Linguiça Calabresa", "Linguiça Toscana", "Linguiça Fininha",
    "Linguiça Suína", "Linguiça Pernil", "Salsicha", "Picanha", "Contra-filé",
    "Alcatra", "Filé Mignon", "Fraldinha", "Costela Bovina", "Acém", "Patinho",
    "Cupim", "Carne Moída", "Peito de Frango", "Coxa/Sobrecoxa de Frango",
    "Asa de Frango", "Frango Inteiro", "Pernil Suíno", "Lombo Suíno",
    "Costela Suína", "Bisteca Suína", "Pé Suíno", "Peixe (filé inteiro)",
    "Camarão", "Bacalhau", "Presunto Fatiado", "Peito de Peru Defumado",
)

ACOUGUE_SYSTEM_PROMPT = (
    "Você é um especialista em classificação de produtos de açougue e frios de "
    "supermercado. Você recebe uma lista numerada de itens reais com IDs. Para "
    "cada item diga a CATEGORIA canônica mais adequada (ex.: 'Bacon', 'Linguiça "
    "Calabresa', 'Picanha', 'Peito de Frango', 'Presunto Fatiado'...). Regras:\n"
    "1) Se o item NÃO for um produto cárneo cru/embutido/fatiado de açougue ou "
    "frios — ex.: comida pronta/congelada com sabor de carne, salgadinho, "
    "tempero, geleia, petisco, ração — use exatamente 'NAO_CARNE'.\n"
    "2) Seja CONSISTENTE: o mesmo produto em lojas/marcas diferentes deve cair "
    "na mesma categoria (o nome pode ter marca/peso).\n"
    "3) Não invente ids. Responda apenas com um objeto JSON válido no formato "
    '{"items": {"<id>": "<categoria>"}} — sem notas, sem texto fora do JSON, '
    "sem quebras de linha dentro das aspas.\n"
    "4) Use SEMPRE uma das CATEGORIAS CANÔNICAS listadas na mensagem (ou "
    "'NAO_CARNE'). Não crie sinônimos/variantes (ex.: use 'Acém', não "
    "'Acém Bovino'/'Acém em Cubos'; use 'Peito de Frango' como padrão de frango)."
)


def build_acougue_prompt(
    items: list[tuple[int, str]],
    retailer_label: str | None = None,
    canonical: list[str] | None = None,
) -> str:
    lines = [f"{pid} — {name}" for pid, name in items]
    scope = f"\nContexto: itens do supermercado {retailer_label}." if retailer_label else ""
    categories = canonical or list(CANONICAL_CATEGORIES)
    canonical_text = "\n".join(f"- {c}" for c in categories)
    return (
        "Classifique cada item abaixo em UMA das CATEGORIAS CANÔNICAS listadas "
        "(departamento de açougue/frios). Use 'NAO_CARNE' para itens que não são "
        "produto cárneo de açougue/frios (comida pronta, sabor artificial, "
        "petisco, etc.). Seja consistente: mesmo produto = mesma categoria; "
        "não crie variações do nome.\n\n"
        "CATEGORIAS CANÔNICAS:\n" + canonical_text + "\n\n"
        "Lista de itens (ID — nome):\n" + "\n".join(lines) + scope +
        '\n\nResponda APENAS com o JSON no formato exato {"items": {"<id>": '
        '"<categoria>"}}.'
    )
