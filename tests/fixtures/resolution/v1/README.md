# Dataset dourado de resolução — v1 (congelado)

Dataset inicial para a Fase 0 da especificação
[`V2-LLM-FIRST-CANONICAL-SPEC.md`](../../../docs/V2-LLM-FIRST-CANONICAL-SPEC.md)
(seção 18.2).

## Origem e metodologia

- Os `raw_name` são **nomes reais** coletados dos arquivos `outputs/llm_*.json`
  (classificação atual) e da POC `offer-classifier-poc`.
- O campo `department`/`category` de `source_products.jsonl` é o **label do
  pipeline atual** (baseline) — não é o golden.
- O golden fica em `expected_interpretations.jsonl` (interpretação revisada por
  humano) e `expected_resolutions.jsonl` (decisão esperada).
- As entidades canônicas (`canonical_entities.jsonl`) são um subconjunto
  ilustrativo do piloto **cerveja/arroz**, conforme recomendação da spec.

## Conteúdo

- 25 `source_products` (9 cervejas, 8 arrozes, 4 bebidas, 4 carnes/congelados).
- 12 `canonical_entities` (2 conceitos, 2 variantes, 8 itens comerciais).
- 9 `candidate_sets` (apenas o subconjunto com resolução rotulada).
- 9 `expected_resolutions` (pares MATCH_EXACT + entidade alvo).
- 9 `pair_labels` (relações entre entidades canônicas).

## Estratificação (meta da spec §18.2)

- descrições abreviadas/siglas: `brahma dm la 269`, `camil lf t1 5kg`,
  `pizza lomb/catup/muss`, `p fgo cong aurora iqf zip`;
- tamanho ausente/ambíguo: `bud 350ml` e `amstel 269ml` (sem embalagem);
- embalagens diferentes do mesmo produto: Heineken 600 × Bud 350;
- pares negativos difíceis: `pair_labels.jsonl` (arroz × cerveja);
- carnes: coxa, lagarto, bacon.

## Limitações conhecidas

- O subconjunto com resolução rotulada é pequeno (9 itens) e serve para validar
  o formato e o harness; **não** é suficiente para medir precisão de produção.
- O dataset é curado manualmente; não compartilhe itens entre este conjunto e
  exemplos de prompt (contaminação de avaliação).
- Campos `sale_mode`/`max_level` são julgamento editorial e não são pontuados
  pelas métricas de interpretação (apenas documentação).

## Expansão

Use `python -m scripts.build_resolution_dataset.py` para extrair mais produtos
reais de `outputs/llm_*.json` como rascunho; a curadoria dos campos de
identidade permanece manual.
