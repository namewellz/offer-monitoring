"""Fuso horário de exibição.

O banco e os coletores gravam horários em UTC (``DateTime(timezone=True)`` com
``datetime.now(UTC)``). As interfaces são em português e o agendamento usa
``America/Sao_Paulo``; por isso, antes de renderizar um horário na tela, ele
deve ser convertido para o fuso local de exibição com :func:`to_local`.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

SAO_PAULO = ZoneInfo("America/Sao_Paulo")


def to_local(value: datetime | date | None):
    """Converte um datetime *aware* (normalmente UTC) para America/Sao_Paulo.

    Valores *naive* (``tzinfo is None``) e datas simples são devolvidos
    inalterados, pois já representam o horário/calendário de exibição.
    """
    if isinstance(value, datetime) and value.tzinfo is not None:
        return value.astimezone(SAO_PAULO)
    return value
