# Catálogo — arquitetura definitiva (v3)

> Design de referência para discussão. Não implementa nada.
> Data: 2026-11-02.
>
> **Resposta direta à pergunta:** a proposta anterior era um remendo incremental
> (colunas soltas + manter os joins). Esta é a versão definitiva. O princípio é
> um só, e resolve performance e histórico **por construção**, sem camadas de
> cache.

---

## 0. O princípio (uma frase)

> **Toda leitura lê estado corrente denormalizado; todo histórico é append-only e
> imutável; tudo é derivado no momento da escrita, nunca no momento da leitura.**

Não há cache, não há materialized view, não há recomputação sob demanda. O que a
tela precisa já está materializado na linha corrente; o que é histórico fica numa
tabela que só recebe INSERT.

---

## 1. O que está errado hoje (medido em produção)

| Sintoma | Causa raiz |
|---|---|
| Filtro de departamento = 86 s | departamento é calculado em Python **depois** de carregar as 44.616 ofertas (8 joins) |
| COUNT = `len(lista)` | a contagem carrega a lista inteira |
| 30,4 M linhas legadas | dual-write: o legado duplica o v2 e cresce 600 mil/dia |
| `idle in transaction` de 20 min | leituras não fecham a transação |
| I/O de 470 MB por page load | leitura varre tabelas com JSONB sem LIMIT na origem |

A raiz comum: **derivação no momento da leitura** em vez de **no momento da
escrita**.

---

## 2. O modelo de dados definitivo

Sobre o schema v2 (que já tem o essencial), três papéis bem definidos:

### 2.1 `store_listings` — o read model (linha corrente)

Uma linha por `(produto, loja)` ativa. **É o que a tela lê.** Passa a carregar,
preenchidos na escrita, todos os campos derivados:

```
store_listings
  id
  target_id / source_product_id            (FK, mantêm)
  active
  -- ==== campos derivados na escrita ====
  department            TEXT               (canônico, vindo do produto)
  product_name          TEXT               (nome vigente — denormalizado p/ busca)
  product_brand         TEXT
  product_gtin          TEXT
  retailer_name         TEXT               (dimensões lentas, copiadas)
  retailer_slug         TEXT
  store_name            TEXT
  regular_price_cents   INT
  effective_price_cents INT
  best_conditional_cents INT
  is_offer              BOOLEAN
  offer_kind            TEXT               ('price_drop'|'club'|'app'|'quantity'|'promotion')
  previous_cents        INT                (baseline da variação, ver 3.1)
  change_amount_cents   INT
  change_percent        NUMERIC
  last_confirmed_at     TIMESTAMPTZ
  last_run_id           BIGINT
```

Índices (poucos e cirúrgicos):

- `(department, is_offer, effective_price_cents)` — filtro "Em oferta" + depto
- `(retailer_slug, is_offer)`
- `(change_percent)` para a view "Variações"
- GIN em `(product_name)` (pg_trgm) para busca `ILIKE`
- `(active) WHERE active` parcial

A tela faz `SELECT ... FROM store_listings WHERE ... ORDER BY ... LIMIT 100`:
**uma tabela, sem joins, sem Python.**

### 2.2 `price_periods` — o histórico imutável (append-only)

Histórico completo, para sempre. Só `INSERT` e, ao mudar o preço, `UPDATE` do
`ended_at` do período anterior (fechamento). **Nunca DELETE.**

- Crescimento é **por mudança real de preço**, não por coleta: preço igual só
  incrementa `confirmation_count` (já é assim hoje).
- Particionada por **`HASH (store_listing_id)`** em 16 partições. O histórico de
  um produto/loja cai inteiro em **uma** partição (um índice em vez de N);
  agregados por período varrem as 16, e isso é raro.
  > Particionar por mês (`RANGE (started_at)`) foi descartado: no Postgres a
  > chave de partição precisa fazer parte de todo índice único, o que exigiria
  > abandonar `UNIQUE (store_listing_id, version)` e o índice parcial do período
  > aberto — as duas invariantes que o ingest usa.
- Histórico por produto = `SELECT * FROM price_periods WHERE store_listing_id=:id
  ORDER BY version` — indexado por `(store_listing_id, version)` (já existe).

### 2.3 Dimensões — imutáveis e pequenas

`source_products`, `source_product_versions` (com `department` derivado na
criação), `catalog_sources`, `collection_targets`, `retailers`, `stores`.
Usadas apenas na **escrita** e em telas de auditoria — não no caminho quente.

### 2.4 Legado — parar de escrever, não apagar

`catalog_price_observations` (30 M linhas): **parar o dual-write**. O histórico
que ele guarda já está (ou passa a estar) em `price_periods`. Os dados existentes
**ficam** como arquivo de auditoria (congelado); nada é apagado. Opcional:
exportar para parquet e remover do Postgres quente depois de validado.

---

## 3. Escrita — onde tudo é derivado

No `ingest` (mesma transação, por loja):

1. **Produto**: se `raw_hash` mudou, nova `source_product_versions` com
   `department = canonical_department(raw_categories, raw_name)` (uma vez).
2. **Preço**: compara com o período aberto.
   - igual → `confirmation_count += 1`, `last_confirmed_at = now`.
   - mudou → fecha o período (`ended_at`) e abre versão nova em `price_periods`.
3. **Linha corrente**: `upsert` em `store_listings` copiando department, nome,
   marca, GTIN, retailer/store, preços, `is_offer`, `offer_kind` e a **variação**
   (3.1). Tudo computado aqui, nunca na leitura.
4. `COMMIT` curto — **nenhuma transação aberta durante processamento**.

### 3.1 Variação calculada na escrita

`change_percent` usa a mesma regra de hoje (`shelf_previous_cents`: quando o
preço atual é o de prateleira e o anterior era desconto, a base é a prateleira
anterior). Como no momento da escrita o período anterior está na mão, o cálculo
é exato e acontece uma única vez por mudança.

### 3.2 Persistir loja a loja

Coletar uma loja → persistir → liberar. Pico de memória cai de ~1,1 GB para
~100 MB e cada transação dura segundos.

---

## 4. Leitura — trivial por construção

| Tela/endpoint | Query |
|---|---|
| Catálogo filtrado | `store_listings` com WHERE + ORDER BY + `LIMIT/OFFSET` |
| Contagem | `SELECT count(*) FROM store_listings WHERE ...` (indexado) |
| Histórico de um produto | `price_periods` por listing (indexado) |
| CSV | streaming da mesma query (OFFSET por lotes) |

- A paginação acontece **no banco** (LIMIT/OFFSET; keyset se precisar ir fundo).
- O cache por geração em memória **deixa de existir** para a tela — a leitura é
  barata o suficiente. (Pode sobrar só para agregados tipo "cobertura por rede",
  que são um `GROUP BY` em tabela pequena.)
- Transação de leitura: `autocommit`/`rollback` imediato — sem `idle in
  transaction`.

---

## 5. Por que isso é performático **por design** (e não por cache)

1. **Leitura = uma tabela indexada**, limitada a 100 linhas. O custo não cresce
   com o volume de ofertas: cresce com o tamanho da página, que é fixo.
2. **Derivação paga uma vez, na escrita**, que já acontece 3×/dia, e nunca no
   caminho do usuário.
3. **Histórico imutável e compacto** (só muda o que mudou). Escala por
   particionamento, não por reescrita.
4. **Sem invalidação de cache**: a linha corrente é atualizada na mesma
   transação que grava o fato. Não existe estado "desatualizado" possível.

Ordem de grandeza esperada (mesma VM, sem upgrade):

| Operação | Antes | Depois (medido em banco local, 496 mil listings) |
|---|---|---|
| Página filtrada (100) | 13 s | **0,5 ms** |
| Contagem (depto + ofertas) | 86 s | **3 ms** |
| Página de ofertas (100) | 13 s | **121 ms** |
| Página de variações (100) | 13 s | **129 ms** |
| Busca por nome (`ILIKE`) | — | **14 ms** |
| Memória por coleta | ~1,1 GB | ~100 MB |
| Crescimento de dados | 600 mil linhas/dia (legado) | só mudanças reais + 1 linha/listing |

Com os índices de ordenação `NULLS LAST` (migração 0019) as duas últimas linhas
caem para **5,5 ms** e **5,9 ms**.

Medido em **produção** (VM Oracle, após 0018 + 0019 + tuning de memória):

| Endpoint | Antes | Depois |
|---|---|---|
| `/catalog` (HTML, página 1) | ~13 s | **0,5–0,9 s** |
| `/catalog?view=offers` | ~13 s | **0,4–0,6 s** |
| `/catalog?view=changes` | ~13 s | **0,9–1,4 s** |
| `/catalog/v2/prices?limit=100` | ~1,3 s | **31–90 ms** |
| `/catalog/v2/offers?limit=100` | ~2,1 s | **41–100 ms** |
| `/catalog/v2/price-changes?limit=100` | ~0,9 s | **34–100 ms** |

O que sobrou nas páginas HTML é o `count(*)` (varredura do índice inteiro,
~250 ms nesta VM) e o I/O limitado do host — não há mais filtro em Python nem
leitura de 44 mil linhas.

---

## 6. Escala de verdade (o que acontece quando crescer)

- `store_listings` a **1 M de linhas** (5× atual): leitura continua O(página);
  índices BTREE/GIN seguram.
- `price_periods` a **dezenas de M** (anos de histórico): as 16 partições por
  HASH do listing mantêm cada índice pequeno; o histórico por produto lê uma só.
- Se o volume de escrita saturar a VM: **separar leitura/escrita no Postgres**
  (read replica) ou subir IOPS — a aplicação não muda, é config.
- Se precisar de análise histórica pesada (ex.: "preço médio por rede por mês"):
  uma consulta agregada pontual em `price_periods`, não um sistema novo.

---

## 7. O que **não** entra (e por quê)

| Candidato | Por que não |
|---|---|
| Cache Redis para o catálogo | a leitura já é uma tabela indexada; cache só adiciona invalidação |
| Materialized view | refresh por coleta é pesado; a linha corrente faz o mesmo sem passo extra |
| Event bus / Kafka | o ingest já roda na transação do Postgres; eventos só p/ fora do app |
| Novo banco (ClickHouse, etc.) | o volume cabe em Postgres particionado por anos |
| Microsserviço de leitura | uma tabela + FastAPI resolve |

---

## 8. Plano de migração (por fase, cada uma já entrega valor)

| Fase | Entrega | Status |
|---|---|---|
| 0 | Fechar transações de leitura (`release_read_transaction`) | ✅ feito |
| 1 | `source_product_versions.department` + backfill + `price_periods` particionada | ✅ feito (migração `0018`) |
| 2 | `store_listings` é o read model (colunas derivadas + ingest atualizado) | ✅ feito |
| 3 | Tela/CSV/API leem `store_listings` (filtro/count/page em SQL) | ✅ feito |
| 4 | Parar dual-write do legado; congelar `catalog_price_observations` | ✅ feito (`LEGACY_CATALOG_WRITE_ENABLED=false`) |

Operação única depois do deploy, para preencher o read model dos dados antigos:

```
python -m app.cli backfill-catalog-read-model
```

É idempotente: calcula o departamento das versões antigas (regra atual) e
reescreve produto/loja/preço dos listings a partir da versão corrente e do
período aberto.

---

## 9. Decisões fechadas

| # | Tema | Decisão |
|---|---|---|
| 1 | Fonte do `department` | **regra atual** (`canonical_department`) |
| 2 | Nome denormalizado vs join | **denormalizar** no read model (ver 9.1) |
| 3 | Legado `catalog_price_observations` | **congelar no Postgres** (ver 9.2) |
| 4 | Particionar `price_periods` | **já** — feito como `HASH (store_listing_id)` (ver 2.2) |

### 9.1 Custo/ganho — denormalizar o nome no read model

Tamanhos medidos em produção (2026-11-02): `store_listings` = 103 MB / 412 mil
linhas; `source_product_versions` = 326 MB.

| | Denormalizar em `store_listings` (A) | Join indexado (B) |
|---|---|---|
| Custo | ~50 MB a mais (nome+marca+GTIN × 412 mil linhas); **zero lógica nova** — o ingest já reescreve a linha corrente quando o produto muda (`raw_hash`) | 1 join por query quente (lista, count, CSV) + join no count; risco de esquecer o join em endpoint novo |
| Ganho | read model autossuficiente: **1 tabela, sem joins** em todo o caminho quente | single source of truth; divergência impossível |
| Divergência | impossível na prática (a mesma transação que versiona o produto reescreve a linha) | — |

**Decisão: A.** O custo é ~50 MB e o ganho é o read model ficar autossuficiente —
é o princípio do design (derivar na escrita).

### 9.2 Custo/ganho — legado congelado vs parquet

Tamanho medido: `catalog_price_observations` = **10,1 GB** (4,9 GB dados +
5,2 GB índices), 30,6 M linhas — mais que todas as tabelas v2 juntas (~0,9 GB).

| | Congelar no Postgres (A) | Exportar parquet + drop (B) |
|---|---|---|
| Custo | mantém os 10,1 GB em disco e nos backups; zero trabalho | job de export + validação + drop; histórico sai do SQL (passa a viver em parquet); telas/auditorias que leem a tabela precisam se adaptar |
| Ganho | zero risco, nada é apagado, SQL continua vendo o histórico | libera ~10 GB de disco/backup; parquet comprime para ~1–2 GB |

**Decisão: A (congelar no Postgres).** O disco ainda não é crítico. Se um dia
ficar, o caminho é: exportar para parquet como cópia de segurança **e manter** a
tabela até o disco realmente apertar — nunca deletar sem o export validado.

---

## 10. Notas de implementação (aprendidas no deploy)

### 10.1 Booleano cru no `WHERE` (senão o índice parcial é ignorado)

SQLAlchemy gera `active IS TRUE` para `.is_(True)`. O *predicate proof* do
Postgres **não** reconhece `IS TRUE` como implicação de `active` ao casar um
índice parcial `WHERE active`, então o plano cai para *parallel seq scan*:
1.500 ms por página contra **9 ms** com o índice.

```python
# certo
conditions = [StoreListing.active, StoreListing.effective_price_cents.is_not(None)]
# errado (ignora ix_sl_page_default / ix_sl_offer_discount / ix_sl_change_abs)
conditions = [StoreListing.active.is_(True), ...]
```

Regra permanente: **todo índice parcial `WHERE active` deve ser casado por
`active` puro**, e o benchmark tem que rodar o SQL exato que o ORM gera —
`WHERE active` e `WHERE active IS TRUE` produzem planos diferentes.

### 10.2 Backfill precisa de keyset + `SKIP LOCKED`

O ingest mantém uma transação por loja (dezenas de milhares de linhas). Um
backfill com `WHERE department IS NULL LIMIT n` sem paginação (a) varre a tabela
a cada lote e (b) fica preso atrás do `UPDATE` da coleta. Solução aplicada em
`app/catalog/v2/rebuild.py`: paginar por `id` (usa a PK) e
`FOR UPDATE SKIP LOCKED`. O comando é idempotente e retoma de onde parou.

### 10.3 Warmups de tela devem fechar a transação

Os caches (`butcher`, `produce_prices`, `dept_prices`, `review`,
`shop_catalog`) chamam `current_listings(db, release=True)`: a transação fecha
logo depois do `SELECT`, em vez de ficar `idle in transaction` durante o
processamento de 400 mil linhas — foi isso que travou `CREATE INDEX
CONCURRENTLY` no passado.

### 10.4 Partição por HASH exige `id` na PK

Em tabela particionada a chave de partição precisa estar em **toda** restrição
única. Como `price_periods` particiona por `store_listing_id`, a PK passou a ser
`(id, store_listing_id)` e `UNIQUE (store_listing_id, version)` foi preservado.
Nenhum código usa `db.get(PricePeriod, id)`.

### 10.5 Preço-sentinela de indisponibilidade (0,01 / 999,90)

Varejistas publicam um valor-placeholder quando o item está sem preço no PDV:

| Rede | Valor | Observação |
|---|---|---|
| Max Atacadista | R$ 0,01 | a API responde com 1 centavo e estoque > 0 |
| Assaí | R$ 999,90 | inclusive com `available: true` (a flag não é confiável) |
| Pague Menos | — | R$ 999,90 ali é **preço real** (vinho Don Melchor) |

Sem tratamento, o sentinela vira um período de preço e, quando o preço
verdadeiro volta, o histórico registra **+19.800%**. Correção:

- `SourceConfig.sentinel_prices` (por rede, em `app/catalog/v2/registry.py`) +
  piso global `MIN_VALID_PRICE_CENTS = 5` (nenhum item de supermercado custa
  menos de R$ 0,05);
- `_sanitize_prices` no ingest zera `sales_price`/`regular_price` sentinela
  **antes** de avaliar o período — o período aberto continua intacto, que é o
  histórico correto (o item apenas ficou indisponível);
- `python -m app.cli purge-catalog-sentinels` limpa os períodos já gravados,
  reabre o período anterior e recompõe o read model (idempotente).

A regra é **por rede, nunca global** — foi o que preservou o vinho de R$ 999,90.

---

## 11. Lista canônica (identidade determinística, sem LLM)

### 11.1 O que é

Uma terceira visão sobre o mesmo read model: em vez de "produto × loja", a tela
mostra **"produto canônico"** — o mesmo item vendido por várias redes, comparado
por **preço unitário** (R$ / kg, R$ / L, R$ / unidade). Nenhuma chamada de LLM:
só o normalizador determinístico (`app/canonical/normalize.py`, `canon-3.0`).

### 11.2 Fluxo (tudo na escrita)

```
coleta → normalized_product_versions  (match_key, size, pack, coverage_group)
       → projeção em store_listings   (identity_key, canonical_name,
                                       comparison_quantity/unit, unit_price_micros)
       → agregado canônico            (canonical_products: 1 linha por identity_key)
```

| Etapa | Onde | Custo |
|---|---|---|
| Normalizar | `app.canonical.backfill` / `incremental` | ~4 min para 229k versões (1×, ou por rede) |
| Projetar | `app.canonical.project.project_all` | ~1 min para 440k listings |
| Agregar | `refresh_canonical_products` | ~6 s |

A leitura da tela não faz `GROUP BY` nenhum: `SELECT ... FROM canonical_products`
= **~20 ms** com cache quente (165.910 produtos canônicos).

### 11.3 Preço unitário

`unit_price_micros = round(effective_price_cents * 10000 / quantidade_base)`
— micro-reais por **grama**, **mililitro** ou **unidade**. A conversão para
kg/L acontece só na formatação (`_unit_label`), nunca no banco.

Quantidade base = `size_value` convertido (`kg→g`, `l/lt→ml`, `dz→un`,
`peca/capsula/folha/sache/rolo/tablete/saco→un`) × `pack_qty`.
`dim:` (dimensão de embalagem) não gera preço unitário.

### 11.4 Grupos de cobertura

| Grupo | Significado | Comparável |
|---|---|---|
| `A1` | chave idêntica em 2+ redes | sim |
| `A2` | identidade completa (marca + tamanho) em 1 rede | sim |
| `B1`–`B4` | marca/tamanho inferidos ou ausentes | não |
| `C` | sem identidade | não |
| `R` | fila de revisão | não |

Produtividade atual (base local, out/2026): **A1+A2 = 364.589 listings**
(83% do catálogo ativo), **320.793 listings com preço unitário** (91,9% dos
preços válidos), **149.299 produtos canônicos comparáveis**.

### 11.5 Telas e API

| Rota | O que mostra |
|---|---|
| `GET /canonical` | lista (busca por nome, departamento, "só comparáveis") |
| `GET /canonical/{identity_key}` | ofertas ordenadas por preço unitário |
| `GET /canonical/api/products` | JSON da lista |
| `GET /canonical/api/product/{key}` | JSON das ofertas |
| `GET /canonical/api/stats` | cobertura por grupo |

### 11.6 Decisões

1. **Agregado materializado, não view.** `GROUP BY identity_key` sobre 440k
   listings custa 1,7 s; a tabela agregada custa 20 ms.
2. **Índices derrubados durante a reconstrução** — manter btree em 165k
   inserts custa mais que recriar depois (11,3 s → 6,6 s).
3. **Sem GIN trgm no nome**: `ILIKE` em 165k linhas é seq scan de ~20 ms;
   o GIN encarecia toda reconstrução.
4. **Departamento e nome por `mode()`**, não `min()` — o mesmo produto pode ter
   classificações divergentes entre redes; vale a mais frequente.
5. **Deduplicação na tela**: o mesmo item pode existir em dois catálogos da
   mesma rede (ids externos diferentes). Fica a observação mais recente por
   `(rede, loja, nome)`.
6. **Sem LLM nesta fase.** `ai_assessments` / resolução por modelo continuam
   desligados; o grupo `R` existe para quando ligarem.

### 11.7 Ligar / reconstruir

```bash
python -m app.cli canonical-backfill     # normaliza o corpus inteiro + projeta + agrega
CANONICAL_ENABLED=true                  # habilita o incremental por coleta
```
