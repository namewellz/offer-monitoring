# Cronograma — Classificação por departamento (base inteira)

> Objetivo: classificar **toda a base** (~83.134 produtos com preço) em
> **categorias canônicas por departamento**, com o mesmo motor online (DeepSeek)
> e o mesmo playbook que já validamos no Açougue. Prioridade de partida
> (definida pelo usuário): **1) Mercearia · 2) Bebidas · 3) Frios e Laticínios**.

## Tamanho da base (distribuição aproximada por departamento — taxonomia atual)

| Departamento | Produtos | | Departamento | Produtos |
|---|---:|---|---|---:|
| Mercearia | ~19.048 | | Limpeza | ~6.066 |
| Higiene | ~10.983 | | Doces e Sobremesas | ~5.151 |
| Bebidas | ~9.318 | | **Outros** (sem dept claro) | ~4.294 |
| Bazar e Utilidades | ~8.396 | | Padaria | ~3.021 |
| Frios e Laticínios | ~7.712 | | Hortifruti | ~2.623 |
| Açougue (já feito) | ~2.370 | | Pet Shop | ~1.391 |
| | | | Congelados | ~1.112 |
| | | | Saudáveis e Orgânicos | ~985 |
| | | | Peixaria | ~664 |

> Nota: o pool que vai para a LLM costuma ser **maior** que o número "limpo" de
> cada departamento (o Açougue enviou ~6,3 mil itens p/ achar 3.520 aceitos +
> falsos positivos p/ rejeitar). Os pools reais por departamento serão medidos na
> Fase 0 com os novos coletores.

## Playbook por departamento (o mesmo que funcionou no Açougue)

Cada departamento repete estas etapas, mas o custo cai muito depois da Fase 0
(infra genérica pronta):

1. **Vocabulário canônico** — seed de categorias do departamento no banco
   (`llm_category_labels`), editável no painel (mesmo fluxo do Açougue, porém
   com seletor de departamento).
2. **Pool de candidatos** — coletor por departamento (palavras-chave +
   taxonomia), 1 produto = 1 id.
3. **Prompt por departamento** — sistema + regras + exemplos + proibição de
   acrescentar atributo/espécie; vocabulário fechado enviado no prompt.
4. **Piloto** — 1 rede, amostra pequena; exportar amostra p/ revisão manual.
5. **Rodada completa** — lotes (120 itens), retry corretivo por lote, persist
   incremental em `llm_classifications`.
6. **Normalização/domínio** — `normalize_category` + regras de domínio
   (espécie, apresentação) e correções manuais no painel.
7. **Aferição de qualidade** — taxa aceito/NAO, consistência entre redes,
   conferência visual no painel de revisão.

## Fase 0 — Fundação multi-departamento (uma vez)

Entregáveis de código (nada de classificar ainda):
- [ ] Coluna `department` na classificação (`llm_classifications`) + controle de
      "produto já classificado em outro departamento" (evitar dupla classificação).
- [ ] Categorias canônicas **por departamento** (coluna `department` em
      `llm_category_labels`/vocabulário; hoje é fixo do Açougue).
- [ ] Painéis (Revisão, Categorias, Comparativo) com **seletor de departamento**
      (hoje fixos em Açougue).
- [ ] Coletores de candidatos genéricos por departamento + contagem de pools.
- [ ] Geração de prompts por departamento (templates parametrizados).
- [ ] Migração `0013` + testes; manter 142+ verdes.

## Fase 1 — Mercearia (19.048) ⭐ primeiro
~160-200 lotes (batch 120) · estimativa 25-40 min de API + revisão do vocabulário
(pode exigir 2-3 iterações de prompt p/ fechar canônicos).

## Fase 2 — Bebidas (9.318)
~80 lotes · estimativa 15-25 min. Atenção: bebidas alcóolicas/não-alcoólicas,
unidade (l/ml/un), versões (lata/garrafa/retornável).

## Fase 3 — Frios e Laticínios (7.712)
~65 lotes · estimativa 12-20 min. Atenção: fatiado/peso variável; cortes de frios
não embutidos; laticínios (queijo/iogurte/leite) vs "bebidas lácteas".

## Fase 4 — Demais grandes (depois dos 3 primeiros)
Higiene (~11.0k) → Bazar e Utilidades (~8.4k) → Limpeza (~6.1k).

## Fase 5 — Médios
Doces e Sobremesas (~5.2k) → Padaria (~3.0k) → Hortifruti (~2.6k) →
Congelados (~1.1k) → Pet Shop (~1.4k) → Saudáveis e Orgânicos (~1.0k) →
Peixaria (~664).

## Fase 6 — "Outros" + auditoria final
- Tratar os ~4.3k produtos sem departamento claro (atribuição/limpeza).
- Auditoria de consistência cross-departamento (um produto = um departamento =
  uma categoria canônica) e fechamento da base.

## Critério de "pronto" por departamento
- 100% do pool com decisão gravada (`accept`+categoria OU `reject`).
- Vocabulário canônico estável (sem crescimento infinito de variantes).
- Consistência: mesmo produto em redes diferentes = mesma categoria.
- Tela de revisão sem pendências críticas de falso positivo.

> Aferição de **preço** (unidade, comparativo por categoria) fica como evolução
> posterior, por departamento — começamos apenas pela **classificação**.
