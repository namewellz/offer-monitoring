"""Métricas da avaliação de interpretação e resolução (spec §18.6-18.8).

Funções puras e determinísticas: recebem golden e predições, devolvem dicionários
com métricas. Nenhuma função aqui chama a rede.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable
from typing import Any

from app.identity.schemas import (
    DEPARTMENT_CODES,
    department_code_of_label,
)

# Campos críticos medidos separadamente (spec §18.6).
CRITICAL_FIELDS = (
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

_STOPWORDS = {"de", "da", "do", "e", "em", "com", "para", "a", "o", "os", "as"}


def fold(text: Any) -> str:
    """Normalização de texto para comparação: NFKD, sem acento, minúsculo."""
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text.casefold()).strip()


def _tokens(text: Any) -> set[str]:
    words = re.findall(r"[a-z0-9]+", fold(text))
    return {w for w in words if w not in _STOPWORDS and len(w) > 1}


def token_overlap(a: Any, b: Any) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _numeric(value: Any) -> float | None:
    """Extrai valor numérico tolerando '2,5', '1/2', '5 kg', '350ml'."""
    text = fold(value)
    if not text:
        return None
    fraction = re.fullmatch(r"(\d+)\s*/\s*(\d+)", text)
    if fraction:
        numerator, denominator = fraction.groups()
        if int(denominator) != 0:
            return int(numerator) / int(denominator)
    match = re.search(r"\d+(?:[.,]\d+)?", text)
    if not match:
        return None
    return float(match.group(0).replace(",", "."))


def field_matches(golden: Any, predicted: Any, field: str) -> bool:
    """Comparação exata normalizada; quantidade compara numericamente."""
    if field == "net_quantity":
        g, p = _numeric(golden), _numeric(predicted)
        if g is None or p is None:
            return fold(golden) == fold(predicted)
        return abs(g - p) < 1e-9
    return fold(golden) == fold(predicted)


def _field_accuracy(
    golden_values: dict[str, Any],
    predicted_values: dict[str, Any],
) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for field in CRITICAL_FIELDS:
        g = golden_values.get(field)
        p = predicted_values.get(field)
        present = g is not None and str(g).strip() != ""
        if not present:
            metrics[field] = {"golden_present": False}
            continue
        exact = field_matches(g, p, field)
        metrics[field] = {
            "golden_present": True,
            "exact": exact,
            "soft_overlap": token_overlap(g, p),
        }
    return metrics


def department_accuracy(golden_codes: Iterable[str], predicted_codes: Iterable[str]) -> float:
    pairs = list(zip(golden_codes, predicted_codes, strict=False))
    if not pairs:
        return 0.0
    return sum(1 for g, p in pairs if g == p) / len(pairs)


def compute_interpretation_metrics(
    expected_by_id: dict[str, dict[str, Any]],
    predictions_by_id: dict[str, dict[str, Any]],
    errors_by_id: dict[str, list[str]],
) -> dict[str, Any]:
    """Métricas agregadas da interpretação LLM-first (spec §18.6).

    ``predictions_by_id`` mapeia id -> dict com os campos previstos (mesmos
    nomes de ``CRITICAL_FIELDS``). ``errors_by_id`` contém falhas de schema.
    """
    ids = list(expected_by_id)
    total = len(ids)

    schema_fail = {i for i in ids if errors_by_id.get(i)}
    dept_golden: list[str] = []
    dept_pred: list[str] = []
    per_field: dict[str, dict[str, int]] = {f: {"present": 0, "exact": 0} for f in CRITICAL_FIELDS}
    soft_sum: dict[str, float] = {f: 0.0 for f in CRITICAL_FIELDS}
    quantity_mae = 0.0
    quantity_count = 0
    invented: Counter[str] = Counter()
    omissions: Counter[str] = Counter()

    for source_id in ids:
        golden = expected_by_id[source_id]
        pred = predictions_by_id.get(source_id) or {}

        if "department_code" in golden:
            dept_golden.append(golden["department_code"])
            dept_pred.append(pred.get("department_code") or "outros")

        for field in CRITICAL_FIELDS:
            g = golden.get(field)
            present = g is not None and str(g).strip() != ""
            if present:
                per_field[field]["present"] += 1
                if field_matches(g, pred.get(field), field):
                    per_field[field]["exact"] += 1
                soft_sum[field] += token_overlap(g, pred.get(field))
                if field == "net_quantity":
                    gv, pv = _numeric(g), _numeric(pred.get(field))
                    if gv is not None and pv is not None:
                        quantity_mae += abs(gv - pv)
                        quantity_count += 1
            elif pred.get(field) not in (None, "", [], {}):
                # campo previsto onde o golden não o espera -> possível invenção
                if field in {"brand", "net_quantity", "unit", "package_type", "variant", "flavor"}:
                    invented[field] += 1

        # omissão: golden exige campo que a predição deixou vazio
        for field in ("brand", "net_quantity", "unit", "package_type"):
            g = golden.get(field)
            if g is not None and str(g).strip() != "" and not str(pred.get(field) or "").strip():
                omissions[field] += 1

    field_summary: dict[str, Any] = {}
    for field in CRITICAL_FIELDS:
        present = per_field[field]["present"]
        field_summary[field] = {
            "present": present,
            "exact": per_field[field]["exact"],
            "accuracy": (per_field[field]["exact"] / present) if present else None,
            "soft_overlap_mean": (soft_sum[field] / present) if present else None,
        }

    return {
        "total": total,
        "schema_invalid": len(schema_fail),
        "schema_valid": total - len(schema_fail),
        "schema_valid_rate": (total - len(schema_fail)) / total if total else 0.0,
        "department_accuracy": department_accuracy(dept_golden, dept_pred),
        "department_n": len(dept_golden),
        "fields": field_summary,
        "quantity_mae": (quantity_mae / quantity_count) if quantity_count else None,
        "quantity_n": quantity_count,
        "invented_fields": dict(invented),
        "omitted_fields": dict(omissions),
    }


def compute_baseline_metrics(
    dataset: Any,
    predictions_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Compara o pipeline atual (labels do dataset) e o LLM-first contra o golden.

    O golden é ``expected_interpretations[].department_code``; o baseline é
    ``source_products[].department`` mapeado para código; o LLM-first é a
    predição. Isso separa "o pipeline atual já acerta" de "a LLM-first acerta".
    """
    golden: list[str] = []
    baseline: list[str] = []
    llm: list[str] = []
    for source in dataset.source_products:
        source_id = str(source["id"])
        expected = dataset.interpretation_by_source.get(source_id)
        if not expected or not expected.get("department_code"):
            continue
        golden.append(expected["department_code"])
        baseline.append(department_code_of_label(source.get("department")))
        pred = predictions_by_id.get(source_id) or {}
        llm.append(pred.get("department_code") or "outros")

    return {
        "n": len(golden),
        "baseline_vs_golden_accuracy": department_accuracy(golden, baseline),
        "llm_first_vs_golden_accuracy": department_accuracy(golden, llm),
        "confusion_baseline": _confusion(golden, baseline),
        "confusion_llm": _confusion(golden, llm),
    }


def _confusion(golden: list[str], predicted: list[str]) -> list[dict[str, Any]]:
    counter = Counter((g, p) for g, p in zip(golden, predicted, strict=False) if g != p)
    return [
        {"golden": g, "predicted": p, "count": count}
        for (g, p), count in counter.most_common()
    ]


def compute_resolution_metrics(
    expected_by_id: dict[str, dict[str, Any]],
    predicted_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Métricas da resolução (spec §18.7), em sua forma mínima para a Fase 0."""
    ids = list(expected_by_id)
    if not ids:
        return {"n": 0}

    action_correct = 0
    canonical_correct = 0
    exact_precision = 0
    exact_n = 0
    false_union = 0

    for source_id in ids:
        expected = expected_by_id[source_id]
        pred = predicted_by_id.get(source_id) or {}
        if pred.get("action") == expected.get("action"):
            action_correct += 1
        if pred.get("canonical_id") == expected.get("canonical_id"):
            canonical_correct += 1
        if expected.get("action") == "MATCH_EXACT":
            exact_n += 1
            if pred.get("action") == "MATCH_EXACT":
                exact_precision += 1
            elif pred.get("action") == "MATCH_VARIANT":
                false_union += 1

    n = len(ids)
    return {
        "n": n,
        "action_accuracy": action_correct / n,
        "canonical_accuracy": canonical_correct / n,
        "exact_precision": (exact_precision / exact_n) if exact_n else None,
        "exact_n": exact_n,
        "false_union_rate": (false_union / exact_n) if exact_n else None,
    }


def render_markdown_report(
    interpretation: dict[str, Any],
    baseline: dict[str, Any],
    run_meta: dict[str, Any],
) -> str:
    """Relatório Markdown comparável entre execuções (spec §18.9)."""
    lines: list[str] = []
    lines.append("# Relatório de avaliação — resolução V2 (Fase 0)")
    lines.append("")
    lines.append("## Execução")
    lines.append("")
    for key, value in run_meta.items():
        lines.append(f"- **{key}**: {value}")
    lines.append("")

    lines.append("## Schema")
    lines.append("")
    total = interpretation["total"]
    lines.append(
        f"- Válidos: **{interpretation['schema_valid']}/{total}** "
        f"({100 * interpretation['schema_valid_rate']:.1f}%)"
    )
    lines.append(f"- Inválidos: {interpretation['schema_invalid']}")
    lines.append("")

    lines.append("## Roteamento de departamento")
    lines.append("")
    lines.append(
        f"- Baseline (pipeline atual) vs golden: "
        f"**{100 * baseline['baseline_vs_golden_accuracy']:.1f}%** "
        f"({baseline['n']} itens)"
    )
    lines.append(
        f"- LLM-first vs golden: "
        f"**{100 * baseline['llm_first_vs_golden_accuracy']:.1f}%**"
    )
    for name, confusion in (("baseline", baseline["confusion_baseline"]), ("llm", baseline["confusion_llm"])):
        if confusion:
            lines.append("")
            lines.append(f"Confusões ({name}):")
            lines.append("")
            lines.append("| golden → predito | ocorrências |")
            lines.append("| --- | --- |")
            for row in confusion:
                lines.append(
                    f"| {DEPARTMENT_CODES.get(row['golden'], row['golden'])} → "
                    f"{DEPARTMENT_CODES.get(row['predicted'], row['predicted'])} | {row['count']} |"
                )
    lines.append("")

    lines.append("## Campos críticos")
    lines.append("")
    lines.append("| campo | acurácia exata | overlap médio | presentes |")
    lines.append("| --- | --- | --- | --- |")
    for field, summary in interpretation["fields"].items():
        accuracy = summary["accuracy"]
        accuracy_text = f"{100 * accuracy:.1f}%" if accuracy is not None else "—"
        overlap = summary["soft_overlap_mean"]
        overlap_text = f"{overlap:.2f}" if overlap is not None else "—"
        lines.append(f"| {field} | {accuracy_text} | {overlap_text} | {summary['present']} |")
    lines.append("")

    if interpretation["quantity_n"]:
        lines.append(
            f"- MAE de quantidade: {interpretation['quantity_mae']:.2f} "
            f"(n={interpretation['quantity_n']})"
        )
        lines.append("")

    if interpretation["invented_fields"]:
        lines.append("## Campos inventados (golden não esperava)")
        lines.append("")
        lines.append("| campo | ocorrências |")
        lines.append("| --- | --- |")
        for field, count in interpretation["invented_fields"].items():
            lines.append(f"| {field} | {count} |")
        lines.append("")

    if interpretation["omitted_fields"]:
        lines.append("## Campos omitidos (golden exigia)")
        lines.append("")
        lines.append("| campo | ocorrências |")
        lines.append("| --- | --- |")
        for field, count in interpretation["omitted_fields"].items():
            lines.append(f"| {field} | {count} |")
        lines.append("")

    return "\n".join(lines)
