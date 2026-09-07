"""Exibição de horários no fuso America/Sao_Paulo (dados gravados em UTC)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.timezone import SAO_PAULO, to_local


def test_aware_utc_converted_to_sao_paulo():
    value = datetime(2026, 9, 7, 9, 51, tzinfo=UTC)
    converted = to_local(value)
    assert converted.tzinfo is not None
    assert converted.utcoffset() == timedelta(hours=-3)
    assert converted.strftime("%d/%m às %H:%M") == "07/09 às 06:51"


def test_sao_paulo_is_used():
    value = datetime(2026, 9, 7, 9, 51, tzinfo=UTC)
    assert to_local(value).tzinfo == SAO_PAULO


def test_naive_datetime_left_unchanged():
    naive = datetime(2026, 9, 7, 6, 51)
    assert to_local(naive) is naive


def test_none_left_unchanged():
    assert to_local(None) is None
