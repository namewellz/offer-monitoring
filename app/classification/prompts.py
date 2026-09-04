"""Prompt builders + definitions of the meat product lines we classify.

Each *line* is a canonical product that retailers sell in several presentations
(ex.: Bacon). The deterministic parser mis-groups many items that merely carry
the meat word as a flavour/ingredient, so we ask the LLM to pick, from a list of
candidate products (sent with their internal ids), which ones are truly that
product. The reply only returns ids, so results can be related back to the DB.
"""

from __future__ import annotations

from app.classification.canonical import (
    CANONICAL_CATEGORIES,
    department_seed,
    reject_token,
)

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
    "'Acém Bovino'/'Acém em Cubos'; use 'Peito de Frango' como padrão de frango).\n"
    "5) NÃO acrescente espécie nem atributo à categoria: escreva apenas o nome "
    "exato da lista (não 'Bacon Suíno Fatiado', 'Picanha Suína', 'Coxa de "
    "Frango Temperada', 'Lombo em Cubos' etc.). Se o item é fatiado/cubos/moído, "
    "use mesmo assim só o nome-base da categoria."
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


# --- Prompts genéricos por departamento (Mercearia, Bebidas, Frios, ...) -------

# Descrição do escopo por departamento, usada no prompt para a LLM saber o que
# "é deste departamento" (e o que deve ir para o token de rejeição).
DEPARTMENT_RULES: dict[str, str] = {
    "Açougue": (
        "produtos cárneos crus/embutidos/fatiados de açougue e frios de corte "
        "(carnes bovina/suína/aves, linguiças, salsicha, bacon, presunto...)"
    ),
    "Mercearia": (
        "alimentos secos, enlatados, conservas, grãos, massas, farinhas, café, "
        "chá, óleos, temperos, molhos, biscoitos, salgadinhos, açúcar e matinais"
    ),
    "Bebidas": (
        "bebidas em geral: refrigerantes, sucos, água, cervejas, vinhos, "
        "destilados, energéticos, isotônicos e chás prontos"
    ),
    "Frios e Laticínios": (
        "laticínios e frios resfriados: leite, iogurte, queijos, manteiga, "
        "margarina, requeijão, creme de leite, presuntos e embutidos frios"
    ),
    "Higiene": (
        "cuidados pessoais e higiene: sabonetes, shampoos, condicionadores, "
        "desodorantes, creme dental, escova dental, fraldas, absorventes, papel "
        "higiênico e cosméticos"
    ),
    "Limpeza": (
        "produtos de limpeza da casa e lavanderia: detergentes, sabão em pó, "
        "amaciante, água sanitária, desinfetantes, limpadores, esponjas e sacos de lixo"
    ),
    "Bazar e Utilidades": (
        "utilidades domésticas, descartáveis, papelaria, eletroportáteis, "
        "utensílios de cozinha, automotivo, jardinagem, brinquedos e vestuário básico"
    ),
    "Doces e Sobremesas": (
        "doces e sobremesas: chocolates, bombons, balas, chicletes, paçoca, "
        "doce de leite, goiabada, gelatina, pudim e sobremesas prontas"
    ),
    "Padaria": (
        "padaria e panificação: pães, bolos, torradas, panetone, biscoitos de "
        "padaria, pão de forma, pão de queijo e massas frescas de padaria"
    ),
    "Hortifruti": (
        "hortifrúti: frutas, verduras, legumes, tubérculos, hortaliças, temperos "
        "frescos e ovos de granja (perecíveis vendidos na seção de hortifrúti)"
    ),
    "Congelados": (
        "produtos congelados e ultracongelados: pizzas, lasanhas, sorvetes, "
        "picolés, nuggets, hambúrgueres congelados, polpas e vegetais congelados"
    ),
    "Pet Shop": (
        "produtos para animais de estimação: rações, petiscos, areia para gatos, "
        "higiene pet e acessórios para pets"
    ),
    "Saudáveis e Orgânicos": (
        "alimentos saudáveis, funcionais, orgânicos, veganos, sem glúten/lactose, "
        "grãos, sementes, castanhas, suplementos e snacks saudáveis"
    ),
    "Peixaria": (
        "peixes, frutos do mar e pescados: filés e peixes inteiros, camarão, "
        "lula, polvo, bacalhau, mariscos e sardinha"
    ),
}


def _department_scope(department: str) -> str:
    return DEPARTMENT_RULES.get(department) or f"produtos típicos do departamento de {department}"


def department_system_prompt(department: str) -> str:
    """System prompt genérico de classificação por departamento."""
    token = reject_token(department)
    scope = _department_scope(department)
    return (
        "Você é um especialista em classificação de produtos de supermercado, "
        f"responsável pelo departamento de {department}. Você recebe uma lista "
        "numerada de itens reais com IDs. Para cada item diga a CATEGORIA "
        "canônica mais adequada. Regras:\n"
        f"1) Este departamento cobre: {scope}. Se o item NÃO for um produto "
        "típico deste departamento (é de outro departamento, é industrializado/"
        "embalado de outra seção, ou usa o tema apenas como sabor/ingrediente), "
        f"use exatamente '{token}'.\n"
        "2) Seja CONSISTENTE: o mesmo produto em lojas, marcas e pesos "
        "diferentes deve cair na mesma categoria (não use marca/peso no nome).\n"
        "3) Não invente ids. Responda apenas com um objeto JSON válido no "
        'formato {"items": {"<id>": "<categoria>"}} — sem notas, sem texto '
        "fora do JSON, sem quebras de linha dentro das aspas.\n"
        "4) Use SEMPRE uma das CATEGORIAS CANÔNICAS listadas na mensagem "
        f"(ou '{token}'). Não crie sinônimos/variantes (ex.: 'Arroz Tipo 1' e "
        "'Arroz Branco' -> 'Arroz'; 'Café Pilão 500g' -> 'Café Torrado e Moído').\n"
        "5) NÃO acrescente marca, peso, sabor, embalagem, espécie ou atributo à "
        "categoria: escreva apenas o nome-base canônico exato da lista."
    )


def build_department_prompt(
    department: str,
    items: list[tuple[int, str]],
    canonical: list[str] | None = None,
    retailer_label: str | None = None,
) -> str:
    """User prompt genérico: lista de itens + vocabulário canônico do dept."""
    lines = [f"{pid} — {name}" for pid, name in items]
    scope = f"\nContexto: itens do supermercado {retailer_label}." if retailer_label else ""
    token = reject_token(department)
    categories = canonical or list(department_seed(department))
    canonical_text = "\n".join(f"- {c}" for c in categories)
    return (
        "Classifique cada item abaixo em UMA das CATEGORIAS CANÔNICAS listadas "
        f"(departamento de {department}). Use '{token}' para itens que não são "
        f"produtos típicos deste departamento. Seja consistente: mesmo produto = "
        "mesma categoria; não crie variações de nome, marca, peso ou sabor.\n\n"
        "CATEGORIAS CANÔNICAS:\n" + canonical_text + "\n\n"
        "Lista de itens (ID — nome):\n" + "\n".join(lines) + scope +
        '\n\nResponda APENAS com o JSON no formato exato {"items": {"<id>": '
        '"<categoria>"}}.'
    )
