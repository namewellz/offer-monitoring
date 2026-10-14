"""Executa a avaliação da interpretação LLM-first sobre o dataset dourado.

Uso (do repositório):
    python -m scripts.run_resolution_eval \
        --dataset tests/fixtures/resolution/v1 \
        --provider deepseek --batch-size 16 --out-dir outputs/eval

Sem ``DEEPSEEK_API_KEY``, use ``--provider mock`` para validar o harness.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

# Permite rodar como ``python scripts/run_resolution_eval.py`` sem -m.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.evaluation.datasets import load_resolution_dataset  # noqa: E402
from app.evaluation.runner import (  # noqa: E402
    DeepSeekProvider,
    MockProvider,
    evaluate,
    run_interpretation,
    write_results,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Avalia a interpretação LLM-first (Fase 0)")
    parser.add_argument("--dataset", default="tests/fixtures/resolution/v1")
    parser.add_argument("--provider", choices=["mock", "deepseek"], default="mock")
    parser.add_argument("--model", default=None, help="override do modelo (deepseek)")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--max-items", type=int, default=None)
    parser.add_argument("--out-dir", default="outputs/eval")
    args = parser.parse_args()

    dataset = load_resolution_dataset(args.dataset)

    if args.provider == "deepseek":
        provider = DeepSeekProvider(model=args.model)
    else:
        provider = MockProvider()

    print(f"Dataset: {args.dataset} ({len(dataset.source_products)} itens)")
    print(f"Provedor: {args.provider} | modelo: {provider.model} | lote: {args.batch_size}")

    records, meta = run_interpretation(
        dataset,
        provider,
        batch_size=args.batch_size,
        max_items=args.max_items,
    )

    report = evaluate(dataset, records, meta)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    out_dir = Path(args.out_dir) / f"{provider.model}-{stamp}"
    results_path, report_path = write_results(out_dir, records, report)

    interp = report["interpretation"]
    print(f"\nResultados gravados em {out_dir}")
    print(f"  schema válido: {interp['schema_valid']}/{interp['total']}")
    print(f"  acurácia dept (LLM vs golden): "
          f"{100 * report['baseline']['llm_first_vs_golden_accuracy']:.1f}%")
    print(f"  baseline (pipeline atual) vs golden: "
          f"{100 * report['baseline']['baseline_vs_golden_accuracy']:.1f}%")
    print(f"  relatório: {report_path}")


if __name__ == "__main__":
    sys.exit(main())
