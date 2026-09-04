"""Structured normalization for produce (hortifrúti) product names.

Goal: answer "where to buy product X cheaply" regardless of presentation. A
product identity is FRUIT + VARIETY (e.g. "Maçã Fuji"); the sale form
(kg / bandeja / pacote / caixa / unidade) and weight are separate attributes
used to normalize prices to R$/kg (or R$/L / per unit when there is no weight).

Extraction is deterministic and conservative: unknown tokens become a short
descriptor used only to disambiguate (origem/marca), never re-defining the fruit.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from app.enrichment.units import parse_quantity

# canonical fruit -> ascii synonyms (first matching token wins)
_FRUIT_SYNONYMS: dict[str, tuple[str, ...]] = {
    "Maçã": ("maca",),
    "Banana": ("banana",),
    "Laranja": ("laranja",),
    "Pêra": ("pera",),
    "Uva": ("uva",),
    "Melancia": ("melancia",),
    "Melão": ("melao",),
    "Mamão": ("mamao",),
    "Abacaxi": ("abacaxi",),
    "Manga": ("manga",),
    "Limão": ("limao",),
    "Tangerina": ("tangerina", "mexerica", "bergamota"),
    "Morango": ("morango",),
    "Goiaba": ("goiaba",),
    "Kiwi": ("kiwi",),
    "Coco": ("coco",),
    "Maracujá": ("maracuja",),
    "Abacate": ("abacate",),
    "Pêssego": ("pessego",),
    "Ameixa": ("ameixa",),
    "Caqui": ("caqui",),
    "Tomate": ("tomate",),
    "Cebola": ("cebola",),
    "Alho": ("alho",),
    "Batata": ("batata",),
    "Cenoura": ("cenoura",),
    "Alface": ("alface",),
    "Brócolis": ("brocolis",),
    "Couve": ("couve",),
}

# Known variety words per fruit (biological/cultivar), ascii-lower phrases.
# Only words that match these phrases become part of the product identity;
# anything else (marca/origem/cor) is folded away into the descriptor so that
# e.g. "Maçã Argentina", "Maçã Bulnez", "Maçã Importada Vermelha" all group
# under the canonical product "Maçã".
_VARIETIES: dict[str, tuple[str, ...]] = {
    "Maçã": ("fuji", "gala", "pink lady", "granny smith", "golden"),
    "Banana": ("prata", "nanica", "maca", "caturra", "terra", "ouro", "sao tome"),
    "Laranja": ("pera", "lima", "bahia", "valencia"),
    "Tomate": ("italiano", "salada", "carmen", "holandes", "cereja", "uva", "gaucho"),
}

# Tokens that are form/weight/packaging/prepositions — never part of identity.
_STOP = frozenset(
    "kg quilo quilos kilo kilos g gr grs grama gramas ml l lt litro litros mg "
    "un und unid uni unidade unidades bandeja band pacote pac pacote saco saco "
    "cx caixa fardo embalagem reserva in natura com de da do em e as os c x "
    "marca sem preço aprox aprox unidade".split()
)


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.lower()


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", _fold(text or "")) if w]


def _title(value: str) -> str:
    return " ".join(word[:1].upper() + word[1:] for word in value.split())


# Acents restored when a token is a known variety written ascii (maca -> Maçã)
_BEAUTY: dict[str, str] = {
    "maca": "Maçã",
    "pera": "Pêra",
    "melao": "Melão",
    "mamao": "Mamão",
    "limao": "Limão",
    "maracuja": "Maracujá",
    "abacaxi": "Abacaxi",
    "pessego": "Pêssego",
    "caqui": "Caqui",
    "laranja": "Laranja",
    "brocolis": "Brócolis",
    "pao": "Pão",
}


def _beautify(token: str) -> str:
    return _BEAUTY.get(token, _title(token))


def _detect_fruit(words: list[str]) -> tuple[str | None, int]:
    """Return (canonical fruit, index of the fruit token)."""
    for idx, word in enumerate(words):
        for fruit, synonyms in _FRUIT_SYNONYMS.items():
            candidates = (word,)
            if word.endswith("s") and len(word) > 3:
                candidates = (word, word[:-1])  # plurals: "macas" -> "maca"
            if any(candidate in synonyms for candidate in candidates):
                return fruit, idx
    return None, -1


def _sale_form(text: str) -> str:
    lower = _fold(text)
    if re.search(r"\b(quilos?|kilos?|kg)\b", lower):
        return "Kg"
    if re.search(r"\bbandejas?\b|band\.", lower):
        return "Bandeja"
    if re.search(r"\b(caixas?|fardos?|cx)\b", lower):
        return "Caixa"
    if re.search(r"\bpacotes?\b|pac\.", lower):
        return "Pacote"
    if re.search(r"\b(unidades?|unid|und|un)\b", lower):
        return "Unidade"
    # fallback by weight hints
    parsed = parse_quantity(text)
    if parsed is not None:
        if parsed.family == "mass":
            return "Kg" if parsed.amount_base >= 1 else "Pacote"
        if parsed.family == "vol":
            return "Unidade"
    return ""


@dataclass
class ProduceProduct:
    product: str  # identity: "Maçã Fuji" (fruit [+ variety/descriptor])
    fruit: str | None
    variety: str | None
    descriptor: str  # origem/marca/color kept to disambiguate (may be '')
    form: str  # Kg | Bandeja | Pacote | Caixa | Unidade | ''
    weight_g: float | None
    raw: str


def normalize_produce(name: str) -> ProduceProduct | None:
    """Extract structured fields from a raw produce product name."""
    if not name or not name.strip():
        return None
    words = _words(name)
    if not words:
        return None
    fruit, fruit_idx = _detect_fruit(words)
    if fruit is None:
        # not recognizably a fruit we model -> caller decides (skip)
        return None

    form = _sale_form(name)

    # weight in grams (from units parser)
    parsed = parse_quantity(name)
    weight_g: float | None = None
    if parsed is not None and parsed.family == "mass":
        weight_g = (
            round(parsed.amount_base * 1000.0, 1)
            if parsed.amount_base < 1000
            else parsed.amount_base
        )

    # remaining meaningful tokens (after fruit + stopwords) -> variety/descriptor
    tail = [
        w
        for w in words[fruit_idx + 1 :]
        if w not in _STOP
        and not re.match(r"^\d", w)  # never keep numbers/weights
        and not (fruit and w in _FRUIT_SYNONYMS.get(fruit, ()))
        and w != fruit
    ]

    # Identity = FRUIT + only known variety phrases, in original order.
    # Remaining tokens (origem/marca/cor) go to the descriptor only and do NOT
    # re-define the product, so all presentations of "Maçã" group together.
    var_phrases = _VARIETIES.get(fruit, ())
    matched_idx: set[int] = set()
    for phrase in sorted(var_phrases, key=lambda p: len(p.split()), reverse=True):
        phrase_tuple = tuple(phrase.split())
        length = len(phrase_tuple)
        for i in range(len(tail) - length + 1):
            if tuple(tail[i : i + length]) == phrase_tuple:
                matched_idx.update(range(i, i + length))
                break  # keep the first occurrence of this phrase only

    identity_words = [tail[i] for i in range(len(tail)) if i in matched_idx]
    desc_tokens = [tail[i] for i in range(len(tail)) if i not in matched_idx][:3]
    descriptor = " ".join(desc_tokens)

    if identity_words:
        identity = f"{fruit} {' '.join(_beautify(t) for t in identity_words)}"
        variety = _beautify(identity_words[0])
    else:
        identity = fruit
        variety = None

    return ProduceProduct(
        product=identity,
        fruit=fruit,
        variety=variety,
        descriptor=descriptor,
        form=form,
        weight_g=weight_g,
        raw=name,
    )


def product_key(name: str) -> str:
    """Stable lowercase key used to group a product across presentations."""
    parsed = normalize_produce(name)
    if parsed is None:
        return _fold(name or "").strip()
    return re.sub(r"[^a-z0-9]+", " ", _fold(parsed.product)).strip()
