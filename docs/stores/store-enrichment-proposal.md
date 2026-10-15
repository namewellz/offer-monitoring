# Proposta: enriquecimento de lojas (Rede - Cidade - Tipo - Bairro)

Status: PROPOSTA. Nada aplicado no banco. Arquivos: `draft_0015_store_enrichment.sql`
(nao aplicado; testado num banco scratch descartado), `sample_backfill_simulation.sql`,
`sample_display.txt`.

## 1. Hoje
- `stores`: `id, retailer_id, name, city, state, active`. Sem bairro, tipo, CEP, filial, lat/lng.
- `stores.name` e a chave de dedupe dos coletores (`persistence.py` casa por `Store.name`;
  `v2/ingest.py` gera `target_key` a partir dele) -> **nao renomear**; exibir por campo calculado.
- `collection_targets` tem `external_store_id/code`, `seller_id`, `reference_postal_code`,
  `public_config` (Atacadao: filial+endereco). `catalog_runs.source_context.store` guarda o
  que cada coletor trouxe.
- `region_bucket` nao existe neste repo; a regra "so Campinas" hoje e a allowlist do coletor
  Atacadao. A proposta cria `stores.region_bucket`.
- Nome da loja e renderizado cru (`store.name`) em: `app/main.py` (506, 571, 658, 1378-1393),
  `app/catalog/v2/read.py` (243, 298, 536), `app/shopping/pages.py` (288, 478, 642),
  `app/annotation/routes.py:51`, dashboards de `app/enrichment/*`.
- Atencao: `13184-222` (Hortolandia centro) e CEP de **referencia** usado por GoodBom, Max,
  Pague Menos, Sao Vicente, Tenda -> nao e o CEP da loja (so Savegnago, cujo endereco bate).

## 2. Cobertura (27 lojas ativas: 24 fisicas + 3 "Nacional"/online)
| Campo | Auto da fonte | Derivavel (CEP/regra) | Manual |
|---|---|---|---|
| rede | 27 | - | - |
| cidade | 27 | - | - |
| tipo | 0 | 27 (regra: Nacional->online, demais->loja) | revisar Spani (CD 40/41/42) e Max (referencia regional) |
| bairro | 11 Atacadao (app `neighborhood`) | +5 via ViaCEP (Spani 3, Dalben, Savegnago) | 8: Assai, Davitta, GoodBom x2, Max, Pague Menos (provavel Jd. Rosolem), Sao Vicente, Tenda |
| filial/codigo | 24 (Atacadao filial, Spani/Dalben CD, Assai 175, Davitta 101, Max 141, PM 16, SV 018, Savegnago 55, Tenda CT39, GoodBom slug) | - | - |
| CEP real | 11 Atacadao + Spani 3 + Dalben + Savegnago = 16 | - | 8 (mesmos do bairro) |
| lat/lng | 11 Atacadao (app `latitude/longitude`) | 5 via geocodificacao do endereco | 8 |

Conflitos app x ViaCEP (bairro): Americana (Vila Bertini x Sao Vito), Indaiatuba (Recreio
Campestre Joia x Itaici), Itu (Brasil x Sao Luiz). Hortolandia: app e ViaCEP dizem
"Parque Sao Miguel", mas o exemplo do usuario diz "Remanso Campineiro" -> curadoria manual vence.

## 3. Schema proposto
`stores` + colunas: `store_type` (enum loja|filial|cd|online), `store_code`, `neighborhood`,
`address_line`, `postal_code` (interno), `latitude`, `longitude`, `region_bucket`
(campinas|fora|online), `display_label` (rotulo curado opcional, ex. "Dunlop 24h"),
`field_sources` jsonb (proveniencia por campo), `curated_at`.

View `store_display`:
- `display_name = concat_ws(' - ', rede, cidade, Tipo, bairro)` (online omite cidade).
  Ex.: `Atacadão - Hortolândia - Loja - Parque São Miguel`.
- `short_label` (mobile) = `rede + (display_label|cidade)` e `(bairro)` so quando a rede tem
  mais de uma loja na mesma cidade. Ex.: `Atacadão Dom Pedro (Jardim Santa Genebra)`, `Dalben Campinas`.
- CEP nunca entra em `display_name`/`short_label` nem em arte publica.

## 4. Backfill
1. Regras: tipo, region_bucket (lista de cidades da regiao; Vila Maria -> `fora`).
2. Atacadao: job Python usando `busca-loja-via-cidade-nome/v2` (neighborhood, zipCode,
   latitude, longitude, address, number) para as filiais da allowlist; o coletor passa a gravar
   esses campos a cada coleta (nao sobrescreve campo com `field_sources=manual`).
3. Demais com CEP real: ViaCEP (bairro/logradouro) + geocodificacao (lat/lng).
4. Gaps: planilha de curadoria (8 lojas) -> UPDATE com `field_sources.neighborhood='manual'`.
5. Precedencia: manual > fonte do varejista > ViaCEP > vazio. Divergencia vira item de revisao.

## 5. Filtros (API)
`GET ...?rede=atacadao&cidade=Campinas&bairro=Jardim%20Yeda&tipo=loja&region=campinas`
(multi-valor por virgula; default `region=campinas`, que esconde `fora` e opcionalmente `online`).
`GET /api/stores` retorna `id, rede, cidade, bairro, tipo, store_code, display_name, short_label`
para popular os filtros. Lista de compras/catalogo/cortes/hortifruti trocam `store.name` por
`display_name` (desktop) / `short_label` (mobile).

## 6. Perguntas abertas
1. Bairro de Hortolandia: "Remanso Campineiro" (usuario) vs "Parque Sao Miguel" (app/ViaCEP)?
2. Spani 1/2/3 sao lojas ou CDs de e-commerce (centro_distribuicao 40/41/42)? Max Atacadista
   e GoodBom Monte Mor (CEP de referencia de Hortolandia) - qual loja fisica real?
3. Lojas "Nacional" (Arena, Atacadao, Savegnago): exibir como "Online" ou ocultar dos filtros?
