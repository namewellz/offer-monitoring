"""Estados operacionais explícitos de um produto (spec §10/§6.6).

Um produto nunca deve ser representado pela *ausência* de linha no banco:
ausência é ambígua (não processado? erro? inválido?). Este enum garante que
todo produto viva em algum estado observável.
"""

from __future__ import annotations

from enum import StrEnum


class ProductState(StrEnum):
    NEW = "NEW"
    NORMALIZED = "NORMALIZED"
    AUTO_RESOLVED = "AUTO_RESOLVED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    NEEDS_TAXONOMY = "NEEDS_TAXONOMY"
    REJECTED = "REJECTED"
    LOCKED = "LOCKED"
    STALE = "STALE"
    ERROR = "ERROR"


# Estados considerados "processados" para fins de cobertura operacional.
SETTLED_STATES = frozenset(
    {
        ProductState.AUTO_RESOLVED,
        ProductState.NEEDS_REVIEW,
        ProductState.NEEDS_TAXONOMY,
        ProductState.REJECTED,
        ProductState.LOCKED,
    }
)
