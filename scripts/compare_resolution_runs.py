"""Compara duas execuções de avaliação (spec §18.9/§23).

Uso:
    python -m scripts.compare_resolution_runs \
        --base outputs/eval/run-a/results.jsonl \
        --candidate outputs/eval/run-b/results.jsonl \
        --dataset tests/fixtures/resolution/v1 \
        --out outputs/eval/diff.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Permite rodar como ``python scripts/compare_resolution_runs.py`` sem -m.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.evaluation.datasets import load_resolution_dataset  # noqa: E402
from app.evaluation.metrics import (
    compute_baseline_metrics,  # noqa: E402
    compute_interpretation_metrics,  # noqa: E402
)


def _load(path: Path) -> list[dict]:
    records = []
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _predictions_and_errors(records: list[dict]) -> tuple[dict, dict]:
    predictions: dict[str, dict] = {}
    errors: dict[str, list[str]] = {}
    for record in records:
        pid = record["id"]
        if record.get("error"):
            errors[pid] = record["schema_errors"]
            continue
        if record.get("prediction"):
            predictions[pid] = record["prediction"]
        if record.get("schema_errors"):
            errors[pid] = record["schema_errors"]
    return predictions, errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Compara duas execuções de avaliação")
    parser.add_argument("--base", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--dataset", default="tests/fixtures/resolution/v1")
    parser.add_argument("--out", default="outputs/eval/diff.md")
    args = parser.parse_args()

    dataset = load_resolution_dataset(args.dataset)

    base_p, base_e = _predictions_and_errors(_load(Path(args.base)))
    cand_p, cand_e = _predictions_and_errors(_load(Path(args.candidate)))

    base_m = compute_interpretation_metrics(dataset.interpretation_by_source, base_p, base_e)
    cand_m = compute_interpretation_metrics(dataset.interpretation_by_source, cand_p, cand_e)
    base_b = compute_baseline_metrics(dataset, base_p)
    cand_b = compute_baseline_metrics(dataset, cand_p)

    lines: list[str] = []
    lines.append("# Comparação entre execuções de avaliação")
    lines.append("")
    lines.append(f"- Base: `{args.base}`")
    lines.append(f"- Candidata: `{args.candidate}`")
    lines.append("")
    lines.append("## Roteamento de departamento (vs golden)")
    lines.append("")
    lines.append(
        "| execução | acurácia |"
    )
    lines.append("| --- | --- |")
    lines.append(
        f"| base | {100 * base_b['llm_first_vs_golden_accuracy']:.1f}% |"
    )
    lines.append(
        f"| candidata | {100 * cand_b['llm_first_vs_golden_accuracy']:.1f}% |"
    )
    lines.append("")

    lines.append("## Campos críticos (acurácia exata)")
    lines.append("")
    lines.append("| campo | base | candidata | delta |")
    lines.append("| --- | --- | --- | --- |")
    for field in base_m["fields"]:
        b = base_m["fields"][field]["accuracy"]
        c = cand_m["fields"][field]["accuracy"]
        b_text = f"{100 * b:.1f}%" if b is not None else "—"
        c_text = f"{100 * c:.1f}%" if c is not None else "—"
        delta = "—"
        if b is not None and c is not None:
            delta = f"{100 * (c - b):+.1f}pp"
        lines.append(f"| {field} | {b_text} | {c_text} | {delta} |")
    lines.append("")

    lines.append("## Itens que mudaram de veredito de schema")
    lines.append("")
    base_ids = {r["id"] for r in _load(Path(args.base))}
    cand_ids = {r["id"] for r in _load(Path(args.candidate))}
    fixed = sorted(base_ids - cand_ids)
    broken = sorted(cand_ids - base_ids)
    if fixed:
        lines.append(f"- Corrigidos: {', '.join(f'`{i}`' for i in fixed)}")
    if broken:
        lines.append(f"- Regredidos: {', '.join(f'`{i}`' for i in broken)}")
    if not fixed and not broken:
        lines.append("- Nenhum item mudou de veredito.")
    lines.append("")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join(lines), encoding="utf-8")
    print(f"Comparação gravada em {args.out}")


if __name__ == "__main__":
    sys.exit(main())
