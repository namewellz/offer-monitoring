# Deploy do modelo v2 de catálogo — runbook de execução

Última atualização: 2026-09-02.

Este documento registra o processo executado **localmente** para implementar o
modelo-alvo descrito em
[`CATALOG-COLLECTION-AND-ENRICHMENT.md`](CATALOG-COLLECTION-AND-ENRICHMENT.md)
e serve de roteiro para reproduzir a mesma operação em produção.

Status: **executado e validado localmente; não aplicado em produção.**

## 1. Escopo executado

- **Fase 1** do documento: `catalog_sources`, `collection_targets`,
  `collection_runs` e `collection_run_errors`.
- **Fase 2**: `source_products`, `source_product_versions`, `store_listings` e
  `price_periods` (histórico por mudança de estado).
- Schema completo da seção 16 (tabelas canônicas e de resolução criadas, ainda
  não populadas).
- **Dual-write**: cada coleta continua gravando o modelo legado **e** passa a
  gravar o modelo v2 na mesma transação.
- **Backfill** do histórico legado para o modelo v2 (ilhas de estado, seção 20.2).
- **Frontend/API** lendo o modelo v2 (painel `/catalog` + endpoints `/catalog/v2/*`).

## 2. Arquivos criados/alterados

Criados:

```text
app/db/models_v2.py
app/catalog/v2/__init__.py
app/catalog/v2/hashing.py
app/catalog/v2/registry.py
app/catalog/v2/ingest.py
app/catalog/v2/backfill.py
app/catalog/v2/read.py
alembic/versions/0008_catalog_v2_model.py
scripts/validate_v2.py
tests/test_catalog_v2.py
```

Alterados:

```text
app/catalog/persistence.py   # dual-write em _persist_catalog
app/core/config.py           # CATALOG_V2_ENABLED
app/cli.py                   # comando backfill-v2
app/main.py                  # /catalog lê v2 + endpoints /catalog/v2/*
.env.example                 # CATALOG_V2_ENABLED
```

## 3. Pré-requisitos

- PostgreSQL com as tabelas legadas (`catalog_products`,
  `catalog_price_observations`, `catalog_runs`, `retailers`, `stores`) já
  existentes — ou seja, a migração `0007` aplicada e, idealmente, histórico já
  coletado para o backfill.
- Docker Compose (imagem `api` com o código novo).

## 4. Passo a passo de produção

### 4.1 Backup e teste de restauração (obrigatório)

```bash
# fora do container, antes de qualquer mudança
docker compose exec -T postgres pg_dump -U flyer -d flyer -Fc -f /tmp/pre_v2.dump
docker compose cp postgres:/tmp/pre_v2.dump ./backup/pre_v2.dump
```

Teste a restauração em um banco descartável antes de prosseguir.

### 4.2 Subir a nova imagem

```bash
docker compose up -d --build
```

O container `api` já executa `alembic upgrade head` na subida. Se quiser
explicitar:

```bash
docker compose exec api alembic upgrade head
docker compose exec api alembic current   # esperado: 0008_catalog_v2_model (head)
```

A migração `0008` **não altera nem apaga** as tabelas legadas; ela cria as 19
tabelas v2 ao lado e semeia os 15 departamentos canônicos.

### 4.3 Backfill do histórico legado

Executar **uma única vez** (é idempotente, mas pesado):

```bash
docker compose exec api python -m app.cli backfill-v2
```

O comando imprime o progresso por fase e, ao final:

```text
backfill-v2: done
Backfilled v2 catalog model:
  sources: 9
  targets: 12
  source_products: 153324
  listings: 223566
  price_periods: 144934
```

Notas:

- Em Docker Desktop/Windows o backfill é lento (I/O do volume). Se precisar
  reiniciar após uma falha, **trunque** as tabelas v2 antes (não basta VACUUM):

  ```bash
  docker compose exec -T postgres psql -U flyer -d flyer -c \
    "TRUNCATE catalog_sources, collection_targets, collection_runs, collection_run_errors, source_products, source_product_versions, store_listings, price_periods CASCADE;"
  ```

- Preço zero/nulo **não** gera período (seção 9.4); por isso o total de períodos
  é menor que a contagem ingênua de ilhas.

### 4.4 Validação

End-to-end (preço igual só confirma; mudança fecha e abre período; rollback no
final, sem sujar dados):

```bash
docker compose exec api python -m scripts.validate_v2
```

Checagens SQL:

```sql
-- migration no head
SELECT version_num FROM alembic_version;

-- redução do histórico
SELECT (SELECT count(*) FROM catalog_price_observations) AS legacy_obs,
       (SELECT count(*) FROM price_periods)              AS periods,
       (SELECT count(*) FROM price_periods WHERE ended_at IS NULL) AS open_periods;

-- departamentos canônicos semeados
SELECT count(*) FROM departments;

-- trigger append-only presente
SELECT tgname, tgenabled FROM pg_trigger
 WHERE tgname = 'trg_product_resolutions_append_only';
```

### 4.5 Dual-write

Já vem habilitado por padrão (`CATALOG_V2_ENABLED=true`). Toda coleta nova grava
legado + v2 na mesma transação; se o v2 falhar, a transação inteira é revertida
(nenhum merge parcial fica visível).

Para desligar o v2 sem reverter código:

```bash
CATALOG_V2_ENABLED=false
```

### 4.6 Shadow reads (validação de paridade)

Antes de declarar o cutover:

- `/catalog` (v2) versus `/catalog/legacy` (legado).
- `/catalog/v2/prices` versus `/catalog/prices`.
- `/catalog/v2/price-history` versus `/catalog/price-history`.

Endpoints legados continuam no ar em paralelo:

| Recurso | Endpoint |
|---|---|
| Painel v2 | `/catalog` |
| Painel legado | `/catalog/legacy` |
| Preços v2 | `/catalog/v2/prices` |
| Variações v2 | `/catalog/v2/price-changes` |
| Ofertas v2 | `/catalog/v2/offers` |
| Histórico v2 | `/catalog/v2/price-history` |
| Departamentos v2 | `/catalog/v2/departments` |

## 5. Rollback

**Interromper o v2 sem apagar nada:**

```bash
CATALOG_V2_ENABLED=false
docker compose up -d api
```

**Remover o modelo v2 (reversão total):**

```bash
docker compose exec api alembic downgrade 0007
```

Isso derruba as tabelas v2 e o trigger; as tabelas legadas permanecem intactas.

## 6. Resultados locais (referência)

| Medida | Valor |
|---|---|
| Migração | `0008_catalog_v2_model` (head) |
| `catalog_sources` | 9 |
| `collection_targets` | 12 |
| `source_products` | 153.324 |
| `store_listings` | 223.566 |
| `price_periods` | 144.934 |
| Redução vs. 3.553.195 observações legadas | ~95,9% |
| Períodos abertos (preço atual conhecido) | 99.044 |

## 7. Caveats conhecidos

- **Dado legado com preço sentinela** (ex.: Assaí `regular=999,0`): infla a
  variação em casos isolados. É problema de dado da fonte, não do modelo v2.
- **Nomes sem acento / prefixo de quantidade** (ex.: `1café`, `2 DESODORIZADOR`)
  vêm assim da própria API da rede — o pipeline grava verbatim.
- **Departamento ainda derivado em leitura**: o front calcula o departamento por
  `canonical_department()` em tempo de consulta. O vínculo canônico
  `departments.id` será materializado no normalizador (próxima fase).
- **Resolução entre redes ainda não implementada**: as tabelas
  `product_concepts`, `product_variants`, `trade_items`, `normalized_product_versions`,
  `resolution_cases`, `match_candidates`, `product_resolutions` e
  `current_product_resolutions` já existem, mas ainda não são populadas.

## 8. Próximos passos (fora deste deploy)

1. Motor de normalização determinística por departamento (Açougue primeiro).
2. Resolução por GTIN (embalados) e por regras (carnes/hortifruti).
3. Tela de revisão de resoluções.
4. Consulta de comparação nos 3 modos (item exato / variante / conceito).
