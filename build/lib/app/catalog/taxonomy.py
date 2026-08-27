"""Canonical product departments shared by every catalog source."""

import re
import unicodedata
from collections.abc import Iterable

CANONICAL_DEPARTMENTS = (
    "Açougue",
    "Bebidas",
    "Bazar e Utilidades",
    "Congelados",
    "Doces e Sobremesas",
    "Frios e Laticínios",
    "Higiene",
    "Hortifruti",
    "Limpeza",
    "Mercearia",
    "Padaria",
    "Peixaria",
    "Pet Shop",
    "Saudáveis e Orgânicos",
    "Outros",
)


def _key(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(character for character in value if not unicodedata.combining(character))
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


# Rules are ordered from the most specific to the broadest. Source departments
# are evaluated before the product-name fallback.
_SOURCE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Peixaria", ("peixaria", "pescados", "frutos do mar")),
    ("Açougue", ("acougue", "carnes aves", "carne bovina", "carne suina", "bovinos", "suinos", "aves")),
    ("Bebidas", ("bebidas", "bebida", "cervejas", "vinhos", "destilados", "coca cola")),
    ("Higiene", ("higiene", "beleza", "perfumaria", "cuidados pessoais", "fraldas", "bebe")),
    ("Limpeza", ("limpeza", "lavanderia")),
    ("Hortifruti", ("hortifruti", "hortifrutigranjeiro", "frutas", "verduras", "legumes")),
    ("Frios e Laticínios", ("frios", "laticinios", "laticinio", "queijos", "iogurtes")),
    ("Congelados", ("congelados", "congelado", "perecivel industrializado", "swift")),
    ("Padaria", ("padaria", "panificacao", "confeitaria", "paes e bolos")),
    ("Pet Shop", ("pet shop", "mundo pet", "animais")),
    (
        "Saudáveis e Orgânicos",
        ("saudaveis", "saudavel", "organicos", "natural e organico", "fit e saudavel"),
    ),
    ("Doces e Sobremesas", ("doces", "sobremesas", "chocolates", "sorvetes", "bomboniere")),
    (
        "Bazar e Utilidades",
        (
            "bazar", "utilidades", "magazine", "eletro", "papelaria", "esporte e lazer",
            "brinquedos", "vestuario", "roupas e calcados", "descartaveis e embalagens",
            "automotivo", "jardinagem", "flores e plantas",
        ),
    ),
    (
        "Mercearia",
        (
            "mercearia", "alimentos", "biscoitos", "salgadinhos", "massas", "graos",
            "cereais", "matinais", "molhos", "temperos", "enlatados", "conservas",
        ),
    ),
)

_PRODUCT_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Peixaria", ("peixe", "tilapia", "sardinha", "atum", "salmao", "camarao", "bacalhau", "pescada")),
    (
        "Açougue",
        (
            "carne", "bovino", "bovina", "suino", "suina", "frango", "linguica", "cupim",
            "picanha", "alcatra", "costela", "fraldinha", "patinho", "coxao", "contra file",
            "car bov", "car su", "p fgo", "ling t", "bacon", "hamb bov", "banha",
        ),
    ),
    (
        "Bebidas",
        (
            "cerveja", "refrigerante", "suco", "agua mineral", "vinho", "whisky", "vodka",
            "energetico", "isotonico", "cachaca", "espumante", "agua min", "agua de coco",
            "refrig", "beb alc", "cha ice",
        ),
    ),
    (
        "Higiene",
        (
            "shampoo", "condicionador", "sabonete", "desodorante", "creme dental", "pasta dental",
            "escova dental", "papel higienico", "fralda", "absorvente", "barbeador", "enxaguante bucal",
            "sh ", "cond ", "desod ", "coloracao", "cr p pentear", "fita dental",
        ),
    ),
    (
        "Limpeza",
        (
            "detergente", "desinfetante", "amaciante", "sabao em po", "lava roupas", "agua sanitaria",
            "limpador", "esponja", "saco para lixo", "inseticida", "limp ", "amac ",
            "det liq", "desinf ", "lava roupa", "tira manchas", "odorizante", "alcool sol",
        ),
    ),
    ("Hortifruti", ("banana", "maca", "laranja", "mamao", "abacaxi", "tomate", "batata", "cebola", "alface", "cenoura")),
    (
        "Frios e Laticínios",
        (
            "leite", "queijo", "iogurte", "requeijao", "manteiga", "margarina", "presunto",
            "mortadela", "qj ", "iog ", "req ", "cr leite", "mant ", "marg ", "beb lactea",
            "salame", "pres coz",
        ),
    ),
    ("Congelados", ("congelado", "pizza", "lasanha", "nuggets", "hamburguer", "sorvete", "sorv ", "polpa f cong", "fruta cong")),
    ("Padaria", ("pao", "bolo", "torrada", "croissant", "panettone", "baguete")),
    ("Pet Shop", ("racao", "petisco para cao", "petisco para gato", "areia para gato")),
    ("Doces e Sobremesas", ("chocolate", "bombom", "bala", "doce", "pudim", "gelatina", "choc ", "pacoca")),
    (
        "Mercearia",
        (
            "arroz", "feijao", "macarrao", "farinha", "acucar", "cafe", "oleo", "azeite",
            "biscoito", "molho", "bisc ", "mac ", "salg ", "azeitona", "tempero", "flocao",
            "polvilho", "maionese", "catchup", "caldo", "amido", "vinagre", "milho canjica",
        ),
    ),
)


def _match(value: str, rules: tuple[tuple[str, tuple[str, ...]], ...]) -> str | None:
    normalized = f" {_key(value)} "
    for department, terms in rules:
        if any(f" {_key(term)} " in normalized for term in terms):
            return department
    return None


def canonical_department(categories: Iterable[str] | None, product_name: str = "") -> str:
    """Return one stable department while retaining source categories separately."""
    category_text = " ".join(str(value) for value in categories or () if value)
    return _match(category_text, _SOURCE_RULES) or _match(product_name, _PRODUCT_RULES) or "Outros"


def canonical_offer_category(category: str | None, product_name: str) -> str:
    return canonical_department([category] if category else [], product_name)
