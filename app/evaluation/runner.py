"""Runner de avaliação da interpretação LLM-first (Fase 0, spec §18/§21).

Executa a interpretação sobre o dataset dourado, valida o schema, calcula as
métricas contra o golden e contra o pipeline atual (baseline), e grava um
JSONL de resultados + um relatório Markdown comparável entre execuções.

Provedores:

- ``mock``: devolve uma interpretação mínima válida (sem rede). Serve apenas
  para validar o harness de ponta a ponta.
- ``deepseek``: usa ``app.classification.deepseek.DeepSeekClient`` (requer
  ``DEEPSEEK_API_KEY`` no ambiente).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.evaluation.datasets import ResolutionDataset, source_ids
from app.evaluation.metrics import (
    compute_baseline_metrics,
    compute_interpretation_metrics,
    render_markdown_report,
)
from app.evaluation.prompts import SYSTEM_PROMPT, build_user_prompt
from app.identity.fingerprints import request_hash
from app.identity.schemas import InterpretationItem, parse_batch

PROMPT_VERSION = "interpretation-v1"
SCHEMA_VERSION = "interpretation-1"
POLICY_VERSION = "default-1"

CRITICAL_FLAT_FIELDS = (
    "department_code",
    "family_code",
    "product_type",
    "brand",
    "net_quantity",
    "unit",
    "package_type",
    "variant",
    "flavor",
)


class Provider(Protocol):
    model: str

    def chat_json(self, system: str, user: str) -> dict[str, Any]: ...


class MockProvider:
    """Provedor determinístico sem rede (somente para smoke test do harness)."""

    model = "mock"

    def chat_json(self, system: str, user: str) -> dict[str, Any]:
        # Reconstrói os ids a partir do prompt para devolver um objeto válido.
        ids: list[str] = []
        for line in user.splitlines():
            if "—" in line:
                ids.append(line.split("—", 1)[0].strip())
        items = {
            pid: {
                "id": pid,
                "classification": {
                    "department_code": "outros",
                    "family_code": None,
                    "product_type": None,
                },
                "identity": {},
                "canonical_display_suggestion": None,
            }
            for pid in ids
        }
        return {"items": items}


class DeepSeekProvider:
    """Envolve o cliente existente do repositório."""

    def __init__(self, model: str | None = None) -> None:
        from app.classification.deepseek import DeepSeekClient, DeepSeekError

        self._client = DeepSeekClient()
        self._DeepSeekError = DeepSeekError
        self.model = model or self._client.model

    def chat_json(self, system: str, user: str) -> dict[str, Any]:
        content = self._client.chat_json(system, user)
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise self._DeepSeekError(f"resposta da LLM não é JSON: {content[:200]}") from exc
        if not isinstance(payload, dict):
            raise self._DeepSeekError("resposta da LLM não é um objeto JSON")
        return payload


@dataclass
class RunMeta:
    model: str
    provider: str
    prompt_version: str
    schema_version: str
    policy_version: str
    batch_size: int
    total_items: int
    batches: int
    duration_s: float
    failed_batches: int = 0


def _flat_prediction(item: InterpretationItem) -> dict[str, Any]:
    identity = item.identity
    return {
        "department_code": item.classification.department_code,
        "family_code": item.classification.family_code,
        "product_type": item.classification.product_type,
        "brand": identity.brand,
        "net_quantity": identity.net_quantity,
        "unit": identity.unit,
        "package_type": identity.package_type,
        "variant": identity.variant,
        "flavor": identity.flavor,
        "sale_mode": identity.sale_mode,
        "package_count": identity.package_count,
        "canonical_display_suggestion": item.canonical_display_suggestion,
        "quality_flags": item.quality_flags,
    }


def run_interpretation(
    dataset: ResolutionDataset,
    provider: Provider,
    *,
    batch_size: int = 16,
    max_items: int | None = None,
    prompt_version: str = PROMPT_VERSION,
    schema_version: str = SCHEMA_VERSION,
    policy_version: str = POLICY_VERSION,
) -> tuple[list[dict[str, Any]], RunMeta]:
    ids = source_ids(dataset)
    if max_items is not None:
        ids = ids[:max_items]

    started = time.perf_counter()
    records: list[dict[str, Any]] = []
    failed_batches = 0

    for batch_index, start in enumerate(range(0, len(ids), batch_size), start=1):
        batch_ids = ids[start : start + batch_size]
        items = [(pid, dataset.source_by_id[pid]["raw_name"]) for pid in batch_ids]
        user = build_user_prompt(items)

        try:
            payload = provider.chat_json(SYSTEM_PROMPT, user)
            parsed, errors = parse_batch(payload, batch_ids)
        except Exception as exc:  # noqa: BLE001 - registrar e continuar o lote
            failed_batches += 1
            for pid in batch_ids:
                records.append(_error_record(dataset, pid, str(exc), batch_index, provider))
            continue

        for pid in batch_ids:
            item = parsed.get(pid)
            item_errors = errors.get(pid) or []
            prediction = _flat_prediction(item) if item else None
            records.append(
                {
                    "id": pid,
                    "raw_name": dataset.source_by_id[pid]["raw_name"],
                    "model": provider.model,
                    "prompt_version": prompt_version,
                    "schema_version": schema_version,
                    "policy_version": policy_version,
                    "batch": batch_index,
                    "schema_ok": item is not None and not item_errors,
                    "schema_errors": item_errors,
                    "request_hash": request_hash(
                        dataset.source_by_id[pid].get("identity_fingerprint", ""),
                        model=provider.model,
                        prompt_version=prompt_version,
                        schema_version=schema_version,
                        policy_version=policy_version,
                        candidates=dataset.candidates_by_source.get(pid, []),
                    ),
                    "prediction": prediction,
                    "error": None,
                }
            )

    duration = time.perf_counter() - started
    meta = RunMeta(
        model=provider.model,
        provider=type(provider).__name__,
        prompt_version=prompt_version,
        schema_version=schema_version,
        policy_version=policy_version,
        batch_size=batch_size,
        total_items=len(ids),
        batches=(len(ids) + batch_size - 1) // batch_size if ids else 0,
        duration_s=round(duration, 2),
        failed_batches=failed_batches,
    )
    return records, meta


def _error_record(
    dataset: ResolutionDataset,
    pid: str,
    message: str,
    batch_index: int,
    provider: Provider,
) -> dict[str, Any]:
    return {
        "id": pid,
        "raw_name": dataset.source_by_id[pid]["raw_name"],
        "model": provider.model,
        "batch": batch_index,
        "schema_ok": False,
        "schema_errors": [message],
        "prediction": None,
        "error": message,
    }


def evaluate(
    dataset: ResolutionDataset,
    records: list[dict[str, Any]],
    meta: RunMeta,
) -> dict[str, Any]:
    """Agrega métricas a partir dos registros de uma execução."""
    predictions_by_id: dict[str, dict[str, Any]] = {}
    errors_by_id: dict[str, list[str]] = {}
    for record in records:
        pid = record["id"]
        if record.get("error"):
            errors_by_id[pid] = record["schema_errors"]
            continue
        if record.get("prediction"):
            predictions_by_id[pid] = record["prediction"]
        if record.get("schema_errors"):
            errors_by_id[pid] = record["schema_errors"]

    interpretation = compute_interpretation_metrics(
        dataset.interpretation_by_source,
        predictions_by_id,
        errors_by_id,
    )
    baseline = compute_baseline_metrics(dataset, predictions_by_id)
    return {
        "interpretation": interpretation,
        "baseline": baseline,
        "run_meta": {
            "model": meta.model,
            "provider": meta.provider,
            "prompt_version": meta.prompt_version,
            "schema_version": meta.schema_version,
            "policy_version": meta.policy_version,
            "batch_size": meta.batch_size,
            "total_items": meta.total_items,
            "batches": meta.batches,
            "failed_batches": meta.failed_batches,
            "duration_s": meta.duration_s,
        },
    }


def write_results(
    output_dir: str | Path,
    records: list[dict[str, Any]],
    report: dict[str, Any],
) -> tuple[Path, Path]:
    """Grava ``results.jsonl`` e ``report.md`` em ``output_dir``."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    results_path = out / "results.jsonl"
    with results_path.open("w", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")

    report_path = out / "report.md"
    markdown = render_markdown_report(
        report["interpretation"],
        report["baseline"],
        report["run_meta"],
    )
    report_path.write_text(markdown, encoding="utf-8")

    return results_path, report_path
