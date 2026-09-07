"""Canonical product naming across every department (generic + specific).

Two-layer identity used for search and for grouping "same product" across
retailers:

- ``generic``  — brand-free identity/class, e.g. ``Cerveja``, ``Arroz``,
  ``Maçã Fuji``, ``Picanha``. It is what "buscar cerveja / arroz" should match.
- ``specific`` — canonical with the specificities that matter, e.g.
  ``Cerveja Heineken 350ml``, ``Arroz Tio João 5kg``, ``Maçã Fuji``.

Brand binding is decided by the department and by a curated class lexicon:

- Brand-RELEVANT (cerveja, refrigerante, arroz, café, iogurte, chocolate,
  shampoo, detergente, ...): the canonical specific carries brand + size.
- Brand-IRRELEVANT (Hortifrúti produce, Açougue/Peixaria cuts and pure
  commodities like sal/açúcar/farinha): brand never enters the identity;
  ``specific == generic``.

The extraction is deterministic and conservative: unknown names degrade
gracefully to a cleaned form (never crash, never invent a brand). This is the
foundation; deeper per-category lexicons can be added in ``_CLASSES``.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from app.enrichment.produce import normalize_produce

# Departments where the identity never includes the brand.
BRAND_IRRELEVANT_DEPARTMENTS = frozenset(
    {"Açougue", "Peixaria", "Hortifruti"}
)

# Canonical class (ascii) -> display. First matching token/phrase wins and the
# class decides brand binding. Extend here to cover more families.

# brand-relevant classes (display kept, generic = class)
_BRAND_RELEVANT: dict[str, tuple[str, ...]] = {
    "Cerveja": ("cerveja",),
    "Chopp": ("chopp",),
    "Refrigerante": ("refrigerante", "refri", "coca cola", "guarana"),
    "Suco": ("suco",),
    "Água de Coco": ("agua de coco",),
    "Água Mineral": ("agua mineral",),
    "Água": ("agua",),
    "Vinho": ("vinho",),
    "Espumante": ("espumante", "prosecco", "champagne"),
    "Whisky": ("whisky", "whiskey", "escoces"),
    "Vodka": ("vodka",),
    "Cachaça": ("cachaca", "pinga"),
    "Gin": ("gin",),
    "Energético": ("energetico",),
    "Isotônico": ("isotonic",),
    "Arroz": ("arroz",),
    "Feijão": ("feijao",),
    "Café": ("cafe",),
    "Chá": ("cha",),
    "Achocolatado": ("achocolatado",),
    "Leite em Pó": ("leite em po",),
    "Óleo": ("oleo de soja", "oleo vegetal", "oleo"),
    "Azeite": ("azeite",),
    "Vinagre": ("vinagre",),
    "Molho de Tomate": ("molho de tomate", "extrato de tomate", "polpa de tomate"),
    "Maionese": ("maionese",),
    "Ketchup": ("ketchup", "catchup"),
    "Mostarda": ("mostarda",),
    "Macarrão": ("macarrao", "espaguete", "parafuso", "penne", "talharim", "massa seca"),
    "Lasanha": ("lasanha",),
    "Biscoito": ("biscoito", "bolacha", "cookies"),
    "Salgadinho": ("salgadinho", "chips", "batata palha"),
    "Cereal Matinal": ("cereal matinal", "cereal"),
    "Aveia": ("aveia",),
    "Granola": ("granola",),
    "Leite": ("leite",),
    "Iogurte": ("iogurte", "yogurte"),
    "Queijo": ("queijo", "mussarela", "mucarela", "prato", "parmesao", "minas"),
    "Requeijão": ("requeijao",),
    "Manteiga": ("manteiga",),
    "Margarina": ("margarina", "creme vegetal"),
    "Creme de Leite": ("creme de leite",),
    "Leite Condensado": ("leite condensado",),
    "Presunto": ("presunto",),
    "Mortadela": ("mortadela",),
    "Salame": ("salame",),
    "Peito de Peru": ("peito de peru",),
    "Chocolate": ("chocolate",),
    "Sorvete": ("sorvete", "picole", "picolé"),
    "Bala": ("bala",),
    "Bombom": ("bombom",),
    "Pão de Forma": ("pao de forma",),
    "Pão de Queijo": ("pao de queijo",),
    "Pizza": ("pizza",),
    "Hambúrguer": ("hamburguer",),
    "Shampoo": ("shampoo", "xampu"),
    "Condicionador": ("condicionador",),
    "Sabonete": ("sabonete",),
    "Creme Dental": ("creme dental", "pasta de dente"),
    "Desodorante": ("desodorante", "antitranspirante"),
    "Sabão Líquido": (
        "sabao liquido",
        "sabao liquida",
        "lava roupa liquido",
        "lava roupas liquido",
        "lava-roupa liquido",
        "lava-roupas liquido",
    ),
    "Sabão em Pó": ("sabao em po", "sabao po", "sabao em pó"),
    "Sabão em Barra": (
        "sabao em barra",
        "sabao de barra",
        "sabao barra",
        "sabao em pedra",
        "sabao glicerina",
    ),
    "Detergente": ("detergente",),
    "Amaciante": ("amaciante",),
    "Água Sanitária": ("agua sanitaria",),
    "Limpador Multiuso": ("limpador multiuso", "multiuso"),
    "Esponja": ("esponja",),
    "Fralda": ("fralda",),
    "Papel Higiênico": ("papel higienico",),
    "Papel Toalha": ("papel toalha",),
    "Atum": ("atum",),
    "Sardinha": ("sardinha",),
}

# Pure commodities where brand does NOT define the identity.
_BRAND_IRRELEVANT: dict[str, tuple[str, ...]] = {
    "Sal": ("sal",),
    "Açúcar": ("acucar", "açúcar"),
    "Farinha de Trigo": ("farinha de trigo",),
    "Farinha de Mandioca": ("farinha de mandioca",),
}

# Tokens never part of identity/brand (forms, sizes, preps, flavors of no
# identity value that appear before the brand).
_STOP = frozenset(
    """
    com de da do das dos em e o a as um uma sem com sabor tipo tradicional
    premium pilsen lager stout ale long neck lata garrafa unidade unidades
    pacote bandeja caixa pack fardo refil recarga mini max zero diet light
    classico classica original integral parboilizado branco
    """.split()
)

# Well-known brands per family, used as a safe brand fallback when the raw name
# has no separate ``brand`` field. Extend over time.
_BRAND_TOKENS: tuple[str, ...] = (
    "heineken", "brahma", "antarctica", "skol", "stella artois", "budweiser",
    "amstel", "corona", "colorado", "eisenbahn", "bohemia", "patagonia",
    "crystal", "petra", "itaipava", "original",
    "tio joao", "camil", "urbano", "prato fino", "zaeli", "namorado",
    "pilao", "3 coracoes", "tres coracoes", "melitta", "nescafe", "cafe do ponto",
    "bom dia", "mimosa", "italac", "piracanjuba", "paulinia", "coca-cola", "pepsi",
    "fanta", "sprite", "guarana antarctica", "del valle", "maguary", "natura",
    "adiril", "clight", "tang", "malt", "red bull", "monster", "gaia", "purity",
    "vigor", "danone", "nestle", "garoto", "lacta", "hersheys", "ferrero",
    "oreo", "toddynho", "quaker", "nestum", "muira", "yelmo",
    "omo", "ariel", "brilhante", "ypê", "ype", "limpol", "veja", "minuano",
    "assolan", "bombril", "lysoform", "pinho sol", "cif", "vanish", "downy",
    "comfort", "omo lavagem", "seda", "elseve", "pantene", "dove", "l'oreal",
    "johnsons", "johnson's", "nivea", "colgate", "sensodyne", "oral-b", "closeup",
    "rexona", "dove men", "axé", "axe", "old spice", "gillette", "bic",
    "pampers", "huggies", "turma da monica", "baby soft",
    "friboi", "minerva", "swift", "frigol", "masterboi",
    "pullman", "wickbold", "visconti", "bauducco", "plusvita", "seven boys",
    "gold boys", "vitta natural", "nutrella", "biovale", "casa do pao de queijo", "forno de minas",
    "parmalat", "italac", "piracanjuba", "lacta", "fugini", "pomarola",
    "elefante", "unicorn", "campos do jordao", "vitarella", "bom sucesso",
    "padova", "galo", "dona benta", "renal" , "marca boa",
    "cocoricó", "frimesa", "sadia", "perdigão", "perdigao", "seara", "aurora",
    "predilecta", "hemmer", "quero", "pomarola", "elefante", "arisco", "sachê",
    "sacha", "knorr", "maggi", "ajinomoto", "sazon", "qualitá", "qualita",
    "delicata", "piraquê", "piraque", "parati", "itaipava", "schincariol",
)

# measure aliases -> normalized suffix
_UNIT_SUFFIX = {
    "ml": "ml", "l": "l", "litro": "l", "litros": "l",
    "kg": "kg", "quilo": "kg", "quilos": "kg", "kilo": "kg", "kilos": "kg",
    "g": "g", "gr": "g", "grama": "g", "gramas": "g",
    "un": "un", "und": "un", "unid": "un", "unidade": "un", "unidades": "un",
}


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.casefold()


def _title(value: str) -> str:
    return " ".join(word[:1].upper() + word[1:] for word in value.split())


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", _fold(text or "")) if w]


def _extract_size(words: list[str]) -> tuple[str | None, list[int]]:
    """Return (normalized size, indices consumed) for the first real measure."""
    for idx, word in enumerate(words):
        number = None
        unit = None
        match = re.fullmatch(r"(\d+(?:[.,]\d+)?)([a-z]+)", word)
        if match:
            number, unit = match.group(1), match.group(2)
        elif re.fullmatch(r"\d+(?:[.,]\d+)?", word) and idx + 1 < len(words):
            candidate = words[idx + 1]
            if candidate in _UNIT_SUFFIX and len(candidate) > 1:
                number, unit = word, candidate
        if number is None or unit not in _UNIT_SUFFIX:
            continue
        cleaned = number.replace(",", ".")
        num = float(cleaned)
        if num == 0:
            continue
        suffix = _UNIT_SUFFIX[unit]
        if suffix in ("ml", "g") and num >= 1000:
            # 1500ml -> 1.5l ; 1000g -> 1kg
            text = f"{num / 1000:g}{'l' if suffix == 'ml' else 'kg'}"
        else:
            text = f"{num:g}{suffix}"
        return text, [idx] + ([idx + 1] if unit != word and idx + 1 < len(words) and words[idx + 1] == unit else [])
    return None, []


def _class_of(words: list[str], text: str, department: str | None) -> tuple[str | None, bool]:
    """Return (display class, brand_relevant) scanning the folded name+category text.

    Synonyms are matched as whole words (word boundaries), never as raw
    substrings, so a short synonym such as ``gin`` cannot match inside
    ``original`` nor ``sal`` inside ``salgado``.
    """
    folded = _fold(text)

    def phrase(synonym: str) -> bool:
        tokens = [re.escape(word) for word in _fold(synonym).split()]
        if not tokens:
            return False
        # tokens casam por palavra; o último aceita plural simples (+s) porque
        # categorias/sites costumam pluralizar ("cervejas", "aguas").
        head = r"\s+".join(tokens[:-1])
        if head:
            head += r"\s+"
        pattern = r"(?<![a-z0-9])" + head + tokens[-1] + r"s?(?![a-z0-9])"
        return re.search(pattern, folded) is not None

    for display, synonyms in _BRAND_RELEVANT.items():
        for synonym in synonyms:
            if phrase(synonym):
                return display, True
    for display, synonyms in _BRAND_IRRELEVANT.items():
        for synonym in synonyms:
            if phrase(synonym):
                return display, False
    # department-level fallback for obvious grocery depts
    if department in ("Bebidas", "Mercearia", "Frios e Laticínios", "Doces e Sobremesas",
                      "Higiene", "Limpeza", "Padaria", "Congelados", "Saudáveis e Orgânicos"):
        return None, True
    return None, False


# ascii brand (as written in the lexicon) -> pretty display with accents
_BRAND_BEAUTY = {
    "tio joao": "Tio João",
    "pilao": "Pilão",
    "3 coracoes": "3 Corações",
    "tres coracoes": "3 Corações",
    "cafe do ponto": "Café do Ponto",
    "perdigao": "Perdigão",
    "ype": "Ypê",
    "pao": "Pão",
    "l'oreal": "L'Oréal",
    "johnson's": "Johnson's",
    "guarana antarctica": "Guaraná Antarctica",
    "oleo": "Óleo",
}


def _detect_brand(words: list[str], raw: str, class_words: set[str]) -> str | None:
    """Best-effort brand from the folded raw name using known-brand tokens."""
    folded = _fold(raw)
    for brand in _BRAND_TOKENS:
        if f" {brand} " in f" {folded} " or folded.startswith(brand + " "):
            return _BRAND_BEAUTY.get(brand, _title(brand))
    return None


@dataclass(frozen=True)
class CanonicalName:
    generic: str
    specific: str
    brand: str | None = None
    size: str | None = None
    brand_relevant: bool = False
    class_name: str | None = None


def canonical_name(
    name: str,
    *,
    brand: str | None = None,
    department: str | None = None,
    categories: list[str] | None = None,
    measure: str | None = None,
) -> CanonicalName:
    """Compute generic + specific canonical names for one catalog product."""
    raw = (name or "").strip()
    if not raw:
        return CanonicalName(generic="", specific="")

    # --- Hortifrúti: reuse the produce identity (fruit [+ variety]) --------
    if department == "Hortifruti":
        produce = normalize_produce(raw)
        if produce is not None:
            identity = produce.product or ""
            fruit = identity.split(" ", 1)[0] if identity else ""
            return CanonicalName(
                generic=fruit or identity,
                specific=identity,
                brand=None,
                size=produce.size_label if hasattr(produce, "size_label") else None,
                brand_relevant=False,
                class_name="Hortifruti",
            )
        return CanonicalName(
            generic=raw, specific=raw, brand=None, brand_relevant=False
        )

    # --- Açougue/Peixaria: brand never defines the identity -----------------
    if department in BRAND_IRRELEVANT_DEPARTMENTS:
        words = _words(raw)
        size, consumed = _extract_size(words)
        meaningful = [w for i, w in enumerate(words) if i not in consumed]
        brand_detected = _clean_brand(brand) or _detect_brand(words, raw, set())
        if brand_detected:
            phrase = {w for w in _words(brand_detected)}
            meaningful = [w for w in meaningful if w not in phrase]
        base = _title(" ".join(meaningful))
        generic = base or raw
        return CanonicalName(
            generic=generic,
            specific=generic,
            brand=brand_detected,
            size=size,
            brand_relevant=False,
        )

    words = _words(raw)
    size, consumed = _extract_size(words)
    meaningful = [w for i, w in enumerate(words) if i not in consumed]
    detect_parts = [" ".join(words)]
    for category in categories or []:
        detect_parts.append(" ".join(_words(category)))
    class_display, relevant = _class_of(meaningful, " ".join(detect_parts), department)

    cleaned_brand = _clean_brand(brand)
    if cleaned_brand is None:
        cleaned_brand = _detect_brand(words, raw, set())

    if class_display is None:
        # fallback: cleaned base name (size removed), no invented brand
        base = _clean_base(raw, words, consumed)
        generic = base or _title(" ".join(meaningful)) or raw
        specific = generic
        return CanonicalName(
            generic=generic,
            specific=specific,
            brand=cleaned_brand,
            size=size,
            brand_relevant=relevant,
        )

    generic = class_display
    if relevant and cleaned_brand:
        parts = [generic, cleaned_brand]
        if size:
            parts.append(size)
        specific = " ".join(parts)
    elif relevant and size:
        specific = f"{generic} {size}"
    else:
        specific = generic
    return CanonicalName(
        generic=generic,
        specific=specific,
        brand=cleaned_brand,
        size=size,
        brand_relevant=relevant,
        class_name=generic,
    )


def _clean_brand(brand: str | None) -> str | None:
    if not brand:
        return None
    text = re.sub(r"\s+", " ", brand.strip())
    return _title(text) or None


def _clean_base(raw: str, words: list[str], consumed: list[int]) -> str | None:
    """Cleaned title-cased base without measure tokens, for unknown classes."""
    kept = [w for i, w in enumerate(words) if i not in consumed and w not in _STOP]
    if not kept:
        return None
    return _title(" ".join(kept))


def search_terms(canonical: CanonicalName, raw: str | None = None) -> list[str]:
    """Tokens/names the search should match (generic, specific, brand, size)."""
    terms = []
    for value in (canonical.specific, canonical.generic, canonical.brand,
                  canonical.class_name):
        if value:
            terms.append(value)
    if canonical.size:
        terms.append(canonical.size)
    if raw:
        terms.append(raw)
    return terms
