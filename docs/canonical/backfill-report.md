# Backfill canônico — relatório de cobertura

Gerado em 16/10/2026 00:39 (America/Sao_Paulo). normalizer_version `canon-3.0`, pipeline_version `canonical-v1`.

Base: 228,892 versões atuais de produtos ativos (protótipo: 228,019).

| Grupo | Backfill | % | Protótipo v3 | % | Δ |
|---|---|---|---|---|---|
| A1 | 121,809 | 53.2% | 121,420 | 53.2% | +389 |
| A2 | 80,370 | 35.1% | 79,882 | 35.0% | +488 |
| B1 | 13,452 | 5.9% | 13,417 | 5.9% | +35 |
| B2 | 302 | 0.1% | 304 | 0.1% | -2 |
| B3 | 7,851 | 3.4% | 7,858 | 3.4% | -7 |
| B4 | 3,838 | 1.7% | 3,862 | 1.7% | -24 |
| C | 249 | 0.1% | 255 | 0.1% | -6 |
| R | 1,021 | 0.4% | 1,021 | 0.4% | +0 |
| **A1+A2** | 202,179 | 88.3% | 201,302 | 88.3% | +877 |

## Flags de qualidade

- `retailer_no_brand_field`: 19,604
- `gtin_bad_checksum`: 7,307
- `dept_noise`: 3,603
- `kit_multi_brand`: 41

## Por rede (A1+A2 %)

| rede | N | A1+A2 |
|---|---|---|
| atacadao | 88,538 | 87.6% |
| assai | 42,977 | 95.0% |
| dalben | 18,120 | 59.9% |
| savegnago | 16,730 | 93.9% |
| pague-menos | 14,041 | 94.0% |
| sao-vicente | 11,481 | 95.6% |
| goodbom | 10,493 | 77.4% |
| tenda | 10,242 | 96.8% |
| arena-atacado | 8,393 | 97.4% |
| spani | 5,699 | 89.0% |
| davitta | 1,484 | 68.9% |
| max-atacadista | 694 | 99.6% |

## Divergências em relação ao protótipo v3 (esperado: A1 121.420 / A2 79.882 / …)

1. **Base maior**: o protótipo usou o export de 15/10 (228.019 produtos); o banco local hoje tem 228.892 versões atuais ativas (o coletor continuou rodando). Os números absolutos sobem; os percentuais ficam iguais (A1+A2 = 88,3%).
2. **Paridade exata**: com as regras do protótipo (r1–r5, q1–q10) e sem as correções, o módulo `app/canonical/normalize.py` reproduz **exatamente** os grupos do protótipo no mesmo CSV (A1 121.420, A2 79.882, B1 13.417, B2 304, B3 7.858, B4 3.862, C 255, R 1.021; 0 linhas divergentes).
3. **Correções pedidas (c1–c7)** movem 108 linhas do mesmo CSV entre grupos (A+B/C líquido +44 em A):
   - c1 `Original` e `Flores e Vegetais` deixam de ser marcas inválidas (B4/A2 → A2/A1);
   - c2 parser `YOPRO`/`PRO+` (ignora 15G/17G de proteína), `gts`, intervalo `350g-370g`, `30CP + 30CP` = 60 comprimidos;
   - c3 kits com 2 marcas (`Yoki` + `Scott`) ficam **sem marca** e vão a B2 (41 itens, flag `kit_multi_brand`);
   - c4 `Porta Ovos Dúzia` = 1 un (não é dúzia nem ovo);
   - c5 `Lo'r` ⇒ `L'Or`;
   - c6 ruído de departamento (marca com >=60% dos itens em um departamento aparecendo em outro com <5%): apenas **flag** `dept_noise`; não muda grupo nem departamento;
   - c7 Dalben/Davitta sem campo marca: flag `retailer_no_brand_field` (a marca continua sendo inferida do título).
4. `mais dog` continua na lista de marcas inválidas (só `Original` e `Flores e Vegetais` foram retiradas, como pedido). Pendência para você decidir.
5. `validated_gtin` só é preenchido quando o dígito verificador GTIN confere (7.307 linhas com `gtin_bad_checksum` ficam sem `validated_gtin`); o grupo A1 por GTIN usa só o formato `^\d{8,14}$`, como o protótipo.
6. Nada foi escrito em `brands`, `brand_aliases`, `invalid_brands` (vazias), em `product_resolutions` nem em qualquer outra tabela.

## Como reverter

- Dados: `DELETE FROM normalized_product_versions WHERE normalizer_version = 'canon-3.0';` (só as linhas novas; a tabela tinha 0 linhas antes).
- Schema: `docker compose run --rm --no-deps api alembic downgrade 0015_store_enrichment` (remove as colunas novas e as 3 tabelas; testado).
- Dump completo pré-mudança: `backups/pre_canonical_20261015_2128.dump` (`pg_restore`).
- Código: branch local `feature/canonical-normalizer`; `git checkout main` volta ao estado anterior (nada foi enviado ao remoto).

## Como validar

```
python -m pytest tests/test_canonical_normalize.py -q
docker compose run --rm --no-deps api python -m app.cli canonical-backfill --dry-run      # recalcula sem gravar
SELECT coverage_group, count(*) FROM normalized_product_versions GROUP BY 1 ORDER BY 1;
SELECT normalized_name, normalized_brand, coverage_group, size_label, pack_qty, unit_count, unit_type, quality_flags
  FROM normalized_product_versions WHERE coverage_group = 'R' ORDER BY random() LIMIT 30;
```
