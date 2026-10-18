# Refino por estágio

O canon-3.0 continua sendo a classificação gravada em `normalized_product_versions`. O refino é uma passagem depois disso. Ele só tenta cruzar item que ficou em A2 com uma âncora que já está em A1. Não reescreve `coverage_group`, `match_key` nem `core_key`. Não cria conceito e não grava `product_resolutions`.

## O que o painel mostra

A home e `/catalog/updates` leem `coverage_group`. Um vínculo do refino não entra nessa conta. O item fechado por um estágio continua aparecendo como A2 na cobertura canônica. O item que nenhum estágio fecha também continua A2.

Para o refino aparecer no painel, a tela precisa ler `canonical_refinements` numa linha separada. Essa linha não soma no percentual do canon-3.0.

## Onde o vínculo fica

Cada item fechado vira uma linha em `canonical_refinements`:

| Coluna | Conteúdo |
|---|---|
| `normalized_product_version_id` | o item que estava aberto |
| `anchor_match_key` | a chave A1 que ele passou a acompanhar |
| `anchor_version_id` | uma versão A1 dessa chave, a de menor id |
| `stage` | o estágio que fechou |
| `evidence` | núcleo antes e núcleo que casou |
| `refiner_version` | `refino-1` |

A chave única é a versão normalizada mais `refiner_version`. Rodar de novo a mesma versão não troca o motivo de quem já fechou. Uma regra nova sobe para `refino-2` e deixa as linhas anteriores no lugar. Apagar a tabela desfaz o refino. A coleta não grava nela.

## A lista

A ordem em `app/canonical/stages/__init__.py` é a ordem da execução.

```python
STAGES = [ancora, plural, abrev, ruido]
```

Cada função recebe quem ainda está aberto e o índice das âncoras. Devolve os vínculos que fecha. O nome da função é o valor de `stage`. Quem fechou sai da fila. O estágio seguinte não revisita.

Um item só fecha se houver uma única âncora com a mesma marca, o mesmo tamanho e a mesma quantidade. Dois A2 parecidos, sem âncora A1, continuam abertos. Duas âncoras possíveis: o estágio não escolhe.

1. `ancora`. O núcleo já é igual ao de uma âncora. Vale mesmo quando essa chave exata está em uma rede só, porque o A1 dela pode ter vindo do GTIN.
2. `plural`. Tira um `s` final de token com 5 letras ou mais. `roupas` alcança `roupa`. `cond` não muda.
3. `abrev`. Troca a palavra inteira, e só se ela tem um destino. O mapa em `app/canonical/stages/abrev.py` começa com `ling` → linguiça, `refrig` → refrigerante e `ceb` → cebola. `choc`, `cond`, `masc` e `hid` ficam de fora.
4. `ruido`. Remove `barcode`, `multipack` e `emb`. `embalagem` permanece.

## Acrescentar um estágio

Crie um arquivo em `app/canonical/stages/` com uma função do mesmo contrato. Coloque a função no fim de `STAGES`. Acrescente um teste em `tests/test_canonical_refine.py` com um caso que fecha e um caso que continua aberto. Não precisa de migration: `stage` é texto.

`save_refinements` só adiciona as linhas na sessão. Não dá commit e não altera o item A1. Preencher a tabela local é um passo à parte. Esta entrega não roda esse passo.
