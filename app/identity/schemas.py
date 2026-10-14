"""Schemas estruturados da interpretação e resolução de identidade (spec §7).

Estes modelos Pydantic são a fonte da verdade para o *formato* que a LLM deve
devolver. Eles têm dois modos de uso:

- ``parse_item`` / ``parse_batch``: validação leniente de uma resposta real
  (a LLM costuma trocar ``int`` por ``str`` no id e omitir campos opcionais;
  isso não deve derrubar o item inteiro).
- ``to_json_schema``: gera o JSON Schema do contrato (draft-07), usado para
  documentar o prompt e, no futuro, para validadores estritos.

Lição documentada da POC (``/memories/repo/llm-first-poc-findings.md``): o
DeepSeek não suporta ``response_format=json_schema``; o contrato é garantido
por ``json_object`` + validação pós-resposta, exatamente o que ``parse_*`` faz.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Vocabulário fechado de departamento
# ---------------------------------------------------------------------------

# Slugs estáveis (compatíveis com app.classification.canonical.department_code).
DEPARTMENT_CODES: dict[str, str] = {
    "acougue": "Açougue",
    "bebidas": "Bebidas",
    "bazar_e_utilidades": "Bazar e Utilidades",
    "congelados": "Congelados",
    "doces_e_sobremesas": "Doces e Sobremesas",
    "frios_e_laticinios": "Frios e Laticínios",
    "higiene": "Higiene",
    "hortifruti": "Hortifruti",
    "limpeza": "Limpeza",
    "mercearia": "Mercearia",
    "padaria": "Padaria",
    "peixaria": "Peixaria",
    "pet_shop": "Pet Shop",
    "saudaveis_e_organicos": "Saudáveis e Orgânicos",
    "outros": "Outros",
}

LABEL_TO_CODE: dict[str, str] = {label: code for code, label in DEPARTMENT_CODES.items()}

SALE_MODES = ("kg", "package", "unit")
QUALITY_FLAGS = (
    "low_confidence",
    "missing_brand",
    "missing_quantity",
    "pack_ambiguity",
    "abbrev_unresolved",
    "contradictory_name",
    "invalid_product",
)


def department_code_of_label(label: str | None) -> str:
    """Rótulo português -> código fechado (fallback ``outros``)."""
    return LABEL_TO_CODE.get((label or "").strip()) or "outros"


def department_label_of_code(code: str) -> str:
    """Código fechado -> rótulo português (fallback ``Outros``)."""
    return DEPARTMENT_CODES.get(code or "", "Outros")


# ---------------------------------------------------------------------------
# Relações e ações de resolução
# ---------------------------------------------------------------------------


class Relation(StrEnum):
    EXACT = "EXACT"
    VARIANT_EQUIVALENT = "VARIANT_EQUIVALENT"
    CONCEPT_RELATED = "CONCEPT_RELATED"
    SUBSTITUTE = "SUBSTITUTE"
    NOT_COMPARABLE = "NOT_COMPARABLE"
    INSUFFICIENT_INFORMATION = "INSUFFICIENT_INFORMATION"


class ResolutionAction(StrEnum):
    MATCH_EXACT = "MATCH_EXACT"
    MATCH_VARIANT = "MATCH_VARIANT"
    MATCH_CONCEPT = "MATCH_CONCEPT"
    CREATE_PROPOSAL = "CREATE_PROPOSAL"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    INVALID = "INVALID"


class IdentityLevel(StrEnum):
    CONCEPT = "CONCEPT"
    VARIANT = "VARIANT"
    TRADE_ITEM = "TRADE_ITEM"


# ---------------------------------------------------------------------------
# Interpretação estruturada (saída da LLM)
# ---------------------------------------------------------------------------


class Confidence(BaseModel):
    """Confiança por campo crítico (declarada pela LLM, não decisiva)."""

    model_config = ConfigDict(extra="ignore")

    family: float | None = None
    brand: float | None = None
    quantity: float | None = None
    package_type: float | None = None


class Classification(BaseModel):
    model_config = ConfigDict(extra="ignore")

    department_code: str = "outros"
    family_code: str | None = None
    product_type: str | None = None


class Identity(BaseModel):
    model_config = ConfigDict(extra="ignore")

    brand: str | None = None
    manufacturer: str | None = None
    variant: str | None = None
    flavor: str | None = None
    species: str | None = None
    cut: str | None = None
    variety: str | None = None
    presentation: str | None = None
    conservation: str | None = None
    package_type: str | None = None
    package_count: int | None = None
    net_quantity: str | None = None  # mantido string: "2,5", "1/2" são reais
    unit: str | None = None
    sale_mode: Literal["kg", "package", "unit"] | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class Abbreviation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    token: str
    meaning: str


class Evidence(BaseModel):
    """Substrings do nome original que justificam cada campo (spec §7.7)."""

    model_config = ConfigDict(extra="ignore")

    brand: list[str] = Field(default_factory=list)
    quantity: list[str] = Field(default_factory=list)
    unit: list[str] = Field(default_factory=list)
    package_type: list[str] = Field(default_factory=list)
    variant: list[str] = Field(default_factory=list)
    flavor: list[str] = Field(default_factory=list)


class InterpretationItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str  # normalizado para string; aceita int na entrada
    classification: Classification = Field(default_factory=Classification)
    identity: Identity = Field(default_factory=Identity)
    canonical_display_suggestion: str | None = None
    abbreviations_expanded: list[Abbreviation] = Field(default_factory=list)
    evidence: Evidence = Field(default_factory=Evidence)
    ambiguities: list[str] = Field(default_factory=list)
    quality_flags: list[str] = Field(default_factory=list)
    confidence: Confidence | None = None

    @classmethod
    def model_validate_lenient(cls, obj: Any, expected_id: str) -> InterpretationItem:
        """Valida um item de resposta, coercendo o id para string.

        Retorna ``(item, errors)`` em vez de lançar: o chamador decide se a
        falha derruba o item ou apenas o marca com ``quality_flags``.
        """
        errors: list[str] = []
        if not isinstance(obj, dict):
            raise ValueError("item não é um objeto JSON")

        normalized: dict[str, Any] = dict(obj)
        received = normalized.get("id")
        if str(received) != str(expected_id):
            errors.append(f"id divergente: esperado {expected_id}, recebido {received!r}")
        normalized["id"] = str(received) if received is not None else expected_id

        try:
            item = cls.model_validate(normalized)
        except Exception as exc:  # pydantic.ValidationError
            raise ValueError(f"item inválido: {exc}") from exc

        if item.classification.department_code not in DEPARTMENT_CODES:
            errors.append(
                f"department_code fora da lista fechada: "
                f"{item.classification.department_code!r}"
            )
        return item, errors


class InterpretationBatch(BaseModel):
    model_config = ConfigDict(extra="ignore")

    items: dict[str, InterpretationItem] = Field(default_factory=dict)


def parse_batch(
    payload: dict[str, Any],
    expected_ids: list[str],
) -> tuple[dict[str, InterpretationItem], dict[str, list[str]]]:
    """Interpreta ``{"items": {"<id>": {...}}}`` retornado pela LLM.

    Retorna ``(items, errors)``; ``errors`` é mapeado por id. IDs ausentes na
    resposta aparecem em ``errors`` com motivo ``ausente``; itens com id
    divergente são associados ao id esperado quando possível.
    """
    raw_items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(raw_items, dict):
        raise ValueError("resposta sem o campo 'items' (objeto id→item)")

    items: dict[str, InterpretationItem] = {}
    errors: dict[str, list[str]] = {}

    # índice por chave string para permitir ids como int na resposta
    by_key: dict[str, Any] = {}
    for key, value in raw_items.items():
        by_key[str(key)] = value

    for expected in expected_ids:
        value = by_key.get(expected)
        if value is None and expected in raw_items:
            value = raw_items[expected]
        if value is None:
            errors[expected] = ["ausente na resposta"]
            continue
        try:
            item, item_errors = InterpretationItem.model_validate_lenient(value, expected)
        except ValueError as exc:
            errors[expected] = [str(exc)]
            continue
        items[expected] = item
        if item_errors:
            errors[expected] = item_errors

    return items, errors


# ---------------------------------------------------------------------------
# JSON Schema do contrato (documentação / validação externa)
# ---------------------------------------------------------------------------


def to_json_schema() -> dict[str, Any]:
    """JSON Schema draft-07 do objeto de interpretação.

    Não é usado como ``response_format`` no DeepSeek (não suportado); serve
    para documentar o contrato no prompt e validar respostas gravadas.
    """
    identity_props: dict[str, Any] = {}
    for field in (
        "brand", "manufacturer", "variant", "flavor", "species", "cut",
        "variety", "presentation", "conservation", "package_type", "unit",
        "net_quantity",
    ):
        identity_props[field] = {"type": ["string", "null"]}
    identity_props["package_count"] = {"type": ["integer", "null"]}
    identity_props["sale_mode"] = {
        "type": ["string", "null"],
        "enum": [*SALE_MODES, None],
    }
    identity_props["attributes"] = {"type": "object"}

    item_schema: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "id",
            "classification",
            "identity",
            "canonical_display_suggestion",
        ],
        "properties": {
            "id": {"type": ["integer", "string"]},
            "classification": {
                "type": "object",
                "required": ["department_code", "family_code", "product_type"],
                "properties": {
                    "department_code": {
                        "type": "string",
                        "enum": sorted(DEPARTMENT_CODES),
                    },
                    "family_code": {"type": ["string", "null"]},
                    "product_type": {"type": ["string", "null"]},
                },
                "additionalProperties": False,
            },
            "identity": {
                "type": "object",
                "properties": identity_props,
                "additionalProperties": False,
            },
            "canonical_display_suggestion": {"type": ["string", "null"]},
            "abbreviations_expanded": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["token", "meaning"],
                    "properties": {
                        "token": {"type": "string"},
                        "meaning": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
            },
            "evidence": {"type": "object"},
            "ambiguities": {"type": "array", "items": {"type": "string"}},
            "quality_flags": {"type": "array", "items": {"type": "string"}},
            "confidence": {
                "type": ["object", "null"],
                "properties": {
                    "family": {"type": ["number", "null"]},
                    "brand": {"type": ["number", "null"]},
                    "quantity": {"type": ["number", "null"]},
                    "package_type": {"type": ["number", "null"]},
                },
                "additionalProperties": False,
            },
        },
    }

    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "ProductInterpretation",
        "type": "object",
        "required": ["items"],
        "additionalProperties": False,
        "properties": {
            "items": {
                "type": "object",
                "additionalProperties": item_schema,
            }
        },
    }


# ---------------------------------------------------------------------------
# Resolução (decisão do resolvedor, não da LLM)
# ---------------------------------------------------------------------------


class ResolutionDecision(BaseModel):
    """Decisão versionada ligando uma versão de origem ao catálogo canônico."""

    model_config = ConfigDict(extra="ignore")

    source_product_id: str
    action: ResolutionAction
    canonical_id: str | None = None
    relation: Relation = Relation.EXACT
    confidence: float | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    method: str | None = None  # ex.: "GTIN", "llm", "alias", "human"
    locked: bool = False
