# Cobertura canônica v3 — protótipo (15/10/2026 BRT)

Somente leitura. Base: Postgres local de produção (export `backups/analysis/products.csv`, 228.019 produtos ativos). Protótipo: `tools/canonical_coverage_proto.py` (não ligado ao app, não commitado). Nenhuma escrita no banco. Grupo novo **R** = vínculo só por GTIN com `1 un` implícita (amostra de revisão, não auto-link).

v1 = regras do primeiro doc; v2 = r1–r5 (kg/un implícitos, marca opcional, dicionário, parser, núcleo vazio); v3 = v2 + q1–q10 abaixo.

## Regras v3

- **q1** dimensão/numeração = atributo válido (32,5cm, N.6, V, nº sapato)
- **q10** GTIN + 1 un implícita vai para amostra de revisão (R)
- **q2** contagens = quantidade com unidade (dúzia, un, cápsula, sachê, rolo, peça)
- **q3** marcas aprovadas (Dasabor, Black Skull, Gabriela Sabatini, Fest Lar, Tok, Casamia, Fortlar, Peterlongo)
- **q4** departamento Açougue para palavras de carne em 'Outros'
- **q5** whitelist de marcas curtas (L'Or, Nik, Ypê, Tok…) na guarda len<4
- **q6** limpeza de título ('|' → espaço, número solto = ml em bebida)
- **q7** regra de ovo restrita a ovos (sem Páscoa/brinquedo)
- **q8** parser: whey/proteína, dren/liq, Grátis/% Desconto
- **q9** lista de marcas de origem inválidas

## v1 → v2 → v3 por grupo
| Grupo | v1 | % | v2 | % | v3 | % | Δ v2→v3 |
|---|---|---|---|---|---|---|---|
| A1 | 119,318 | 52.3% | 121,399 | 53.2% | 121,420 | 53.2% | +21 |
| A2 | 58,964 | 25.9% | 74,254 | 32.6% | 79,882 | 35.0% | +5,628 |
| B1 | 9,579 | 4.2% | 12,303 | 5.4% | 13,417 | 5.9% | +1,114 |
| B2 | 856 | 0.4% | 483 | 0.2% | 304 | 0.1% | -179 |
| B3 | 33,118 | 14.5% | 15,430 | 6.8% | 7,858 | 3.4% | -7,572 |
| B4 | 3,835 | 1.7% | 3,768 | 1.7% | 3,862 | 1.7% | +94 |
| C | 2,349 | 1.0% | 382 | 0.2% | 255 | 0.1% | -127 |
| R | 0 | 0.0% | 0 | 0.0% | 1,021 | 0.4% | +1,021 |
| **A1+A2** | 178,282 | 78.2% | 195,653 | 85.8% | 201,302 | 88.3% | +5,649 |

v2→v3: +7,014 entraram em A, −1,365 saíram (1.021 vão para R por regra; o resto são correções de marca inválida/contagens). v1→v3: +24,269 entraram em A.

### Movimentos v2 (linha) → v3 (coluna)
| v2\v3 | A1 | A2 | B1 | B2 | B3 | B4 | C | R |
|---|---|---|---|---|---|---|---|---|
| A1 | 120,353 | 7 | 0 | 0 | 8 | 10 | 0 | 1,021 |
| A2 | 265 | 73,663 | 133 | 0 | 137 | 56 | 0 | 0 |
| B1 | 31 | 0 | 12,250 | 0 | 14 | 8 | 0 | 0 |
| B2 | 5 | 117 | 43 | 304 | 0 | 14 | 0 | 0 |
| B3 | 754 | 6,076 | 886 | 0 | 7,696 | 5 | 13 | 0 |
| B4 | 9 | 19 | 95 | 0 | 0 | 3,645 | 0 | 0 |
| C | 3 | 0 | 10 | 0 | 3 | 124 | 242 | 0 |
| R | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

## Resgatados por regra (cada regra sozinha sobre o v2)
| Regra | entraram em A | saíram de A | melhoraram | pioraram |
|---|---|---|---|---|
| q1 dimensão/numeração = atributo válido (32,5cm, N.6, V, nº sapato) | 3,515 | 0 | 4,074 | 0 |
| q10 GTIN + 1 un implícita vai para amostra de revisão (R) | 0 | 3,779 | 0 | 3,779 |
| q2 contagens = quantidade com unidade (dúzia, un, cápsula, sachê, rolo, peça) | 4,147 | 612 | 4,719 | 898 |
| q3 marcas aprovadas (Dasabor, Black Skull, Gabriela Sabatini, Fest Lar, Tok, Casamia, Fortlar, Peterlongo) | 0 | 12 | 58 | 12 |
| q4 departamento Açougue para palavras de carne em 'Outros' | 19 | 0 | 19 | 0 |
| q5 whitelist de marcas curtas (L'Or, Nik, Ypê, Tok…) na guarda len<4 | 8 | 20 | 83 | 20 |
| q6 limpeza de título ('|' → espaço, número solto = ml em bebida) | 0 | 0 | 1 | 0 |
| q7 regra de ovo restrita a ovos (sem Páscoa/brinquedo) | 0 | 27 | 0 | 27 |
| q8 parser: whey/proteína, dren/liq, Grátis/% Desconto | 134 | 3 | 185 | 15 |
| q9 lista de marcas de origem inválidas | 1 | 154 | 172 | 181 |

Leitura:
- **q1 (dimensão)** e **q2 (contagens)** dão o ganho: ~3,5 mil e ~4,1 mil itens entram em A. q2 também tira 612 de A porque `16 un` deixa de ser `1 un` implícita e deixa de casar com a rede que escreve só `un`.
- **q10** move 3.779 itens de A1 para R isolada; no v3 combinado só 1.021, porque q2 já substitui a `1 un` implícita por contagem real.
- **q9 (marcas inválidas)** é líquida negativa (saem 154 de A, 181 pioram): `Original` é marca real de cerveja e `Flores e Vegetais` é marca real de shampoo. `Generico` virou "sem marca (não importa)".
- q3/q5/q4/q6/q7/q8 são pequenos mas corrigem erros pontuais (L'Or, Black Skull, Linguiça, Peterlongo, ovo de Páscoa).

Diagnóstico v3: tamanho/atributo válido 204,816 → 216,820; origem do tamanho: título 178,310, multi 2,927, dimensão 9,882, contagem 10,396, kg implícito 10,481, un implícita 4,824, sem 11,199. Tipos de contagem: {'un': 16182, 'folha': 587, 'rolo': 354, 'peca': 326, 'sache': 200, 'capsula': 116, 'dz': 29, 'tablete': 15, 'saco': 2}. Marca: origem 166,720, inferida 48,850, sem marca-ok 5,295, nenhuma 7,154. Conflitos 744 → 338. Linguiça/churrasco etc. movidos para Açougue: 388. Marcas aprovadas encontradas: {'Dasabor': 32, 'Black Skull': 33, 'Gabriela Sabatini': 1, 'Fest Lar': 43, 'Tok': 57, 'Casamia': 20, 'Fortlar': 17, 'Peterlongo': 1}.

## Por departamento: % em A (A1+A2) e % em B/C — v1 → v2 → v3
| departamento | N | A v1 | A v2 | A v3 | Δ v2→v3 pp | B/C v1 | B/C v2 | B/C v3 |
|---|---|---|---|---|---|---|---|---|
| Mercearia | 46,163 | 90.8% | 91.3% | 91.8% | +0.5 | 9.2% | 8.7% | 8.2% |
| Higiene | 28,344 | 78.0% | 82.2% | 86.1% | +3.9 | 22.0% | 17.8% | 12.8% |
| Bebidas | 25,528 | 92.8% | 93.2% | 93.3% | +0.1 | 7.2% | 6.8% | 6.6% |
| Frios e Laticínios | 21,384 | 76.2% | 89.6% | 89.7% | +0.1 | 23.8% | 10.4% | 10.3% |
| Bazar e Utilidades | 21,020 | 40.5% | 62.0% | 70.1% | +8.1 | 59.5% | 38.0% | 27.6% |
| Outros | 18,723 | 73.1% | 76.7% | 88.3% | +11.6 | 26.9% | 23.3% | 11.6% |
| Limpeza | 16,303 | 88.1% | 91.4% | 92.2% | +0.8 | 11.9% | 8.6% | 7.0% |
| Doces e Sobremesas | 12,798 | 89.0% | 90.3% | 91.1% | +0.8 | 11.0% | 9.7% | 8.8% |
| Açougue | 10,225 | 52.2% | 90.2% | 90.0% | -0.2 | 47.8% | 9.8% | 10.0% |
| Padaria | 9,740 | 84.1% | 96.2% | 96.4% | +0.2 | 15.9% | 3.8% | 3.6% |
| Hortifruti | 7,645 | 58.1% | 82.4% | 82.6% | +0.2 | 41.9% | 17.6% | 17.3% |
| Congelados | 3,799 | 83.6% | 84.5% | 86.2% | +1.7 | 16.4% | 15.5% | 13.7% |
| Pet Shop | 2,357 | 85.8% | 89.1% | 88.5% | -0.6 | 14.2% | 10.9% | 10.0% |
| Saudáveis e Orgânicos | 2,021 | 72.2% | 73.1% | 73.4% | +0.3 | 27.8% | 26.9% | 26.6% |
| Peixaria | 1,969 | 81.7% | 90.2% | 90.6% | +0.4 | 18.3% | 9.8% | 9.4% |

## Por rede: % em A (A1+A2) e % em B/C — v1 → v2 → v3
| rede | N | A v1 | A v2 | A v3 | Δ v2→v3 pp | B/C v1 | B/C v2 | B/C v3 |
|---|---|---|---|---|---|---|---|---|
| atacadao | 87,820 | 76.2% | 87.9% | 87.6% | -0.3 | 23.8% | 12.1% | 11.4% |
| assai | 42,977 | 84.3% | 89.6% | 95.0% | +5.4 | 15.7% | 10.4% | 5.0% |
| dalben | 18,118 | 54.1% | 59.2% | 59.8% | +0.6 | 45.9% | 40.8% | 40.1% |
| savegnago | 16,712 | 89.9% | 90.5% | 93.9% | +3.4 | 10.1% | 9.5% | 6.0% |
| pague-menos | 14,041 | 80.5% | 82.7% | 94.0% | +11.3 | 19.5% | 17.3% | 6.0% |
| sao-vicente | 11,451 | 79.3% | 92.7% | 95.5% | +2.8 | 20.7% | 7.3% | 4.5% |
| goodbom | 10,431 | 69.5% | 74.4% | 77.6% | +3.2 | 30.5% | 25.6% | 22.4% |
| tenda | 10,242 | 91.9% | 93.0% | 96.8% | +3.8 | 8.1% | 7.0% | 2.9% |
| arena-atacado | 8,359 | 80.9% | 93.7% | 97.3% | +3.6 | 19.1% | 6.3% | 2.7% |
| spani | 5,699 | 85.7% | 88.3% | 88.9% | +0.6 | 14.3% | 11.7% | 11.1% |
| davitta | 1,475 | 62.1% | 67.5% | 68.7% | +1.2 | 37.9% | 32.5% | 31.1% |
| max-atacadista | 694 | 98.1% | 99.3% | 99.6% | +0.3 | 1.9% | 0.7% | 0.4% |

Nota: em departamento, v3 usa o mapeamento com a correção de carnes (388 itens saem de 'Outros' para Açougue), então N de Outros/Açougue difere entre v2 e v3.

## Motivos que sobram (v3)

- **B1** (13,417): marca só inferida do título: 13,417
- **B2** (304): kit / multi-medida: 214; tamanhos conflitantes: 90
- **B3** (7,858): sem nenhuma medida/contagem no título: 7,858
- **B4** (3,862): sem marca na origem nem no dicionário: 3,862
- **C** (255): sem marca e sem tamanho: 255
- **R** (1,021): vínculo só por GTIN com `1 un` implícita (revisar por amostra).

B3 por dept: {'Bazar e Utilidades': 2586, 'Outros': 1567, 'Higiene': 1490, 'Hortifruti': 802, 'Mercearia': 462, 'Limpeza': 302, 'Açougue': 226, 'Frios e Laticínios': 110}; por rede: {'assai': 2009, 'dalben': 1493, 'savegnago': 963, 'atacadao': 888, 'pague-menos': 760, 'goodbom': 680}

B4 por dept: {'Mercearia': 1182, 'Bebidas': 734, 'Frios e Laticínios': 375, 'Doces e Sobremesas': 327, 'Saudáveis e Orgânicos': 298, 'Higiene': 274, 'Outros': 268, 'Congelados': 196}; por rede: {'dalben': 2275, 'atacadao': 675, 'goodbom': 535, 'davitta': 216, 'spani': 119, 'assai': 22} (Dalben concentra B4: título sem campo de marca)

C por dept: {'Higiene': 61, 'Mercearia': 54, 'Outros': 47, 'Limpeza': 32, 'Saudáveis e Orgânicos': 16, 'Bebidas': 15, 'Frios e Laticínios': 13, 'Doces e Sobremesas': 10}

Causas principais que sobram, pelos exemplos:
- **B1 (13,4 mil):** marca só inferida; maior fila de revisão/aprovação em lote.
- **B3 (7,9 mil):** Bazar (2,6 mil), Outros, Higiene, Hortifruti: itens sem medida nem contagem (colher, vassoura, brinquedo, roseira, "Leve 3 Pague 2" de unidades, kit sem número).
- **B4 (3,9 mil):** marca real fora do dicionário (Dalben 2,3 mil); vinhos, cervejas e mercearia importada.
- **B2/C:** kits, protein/whey sem palavra-chave, intervalos de peso, títulos truncados.

## 10 exemplos novos por grupo restante (seed 31, sem repetir rodadas anteriores)


### B1
| rede | dept | título | marca origem | marca | tamanho | flags |
|---|---|---|---|---|---|---|
| atacadao | Bazar e Utilidades | Pá de Lixo Alklin Com Escova un |  | Alklin (inferida) | 1un  | <Flags(allows_duplicate_labels=True)> |
| dalben | Bazar e Utilidades | Porta Detergente Plasutil 540ml Decorado |  | Plasutil (inferida) | 540ml  | <Flags(allows_duplicate_labels=True)> |
| spani | Limpeza | Limpador Multi Uso Triex 500ml Frutas Vermelhas |  | TRIEX (inferida) | 500ml  | <Flags(allows_duplicate_labels=True)> |
| goodbom | Mercearia | ALIMENTO COM AVEIA BARISTA A TAL DA CASTANHA 1L |  | A Tal Da Castanha (inferida) | 1000ml  | <Flags(allows_duplicate_labels=True)> |
| davitta | Limpeza | LIMP VEJA X14 TIRA LIMO REFIL 400ML |  | Veja (inferida) | 400ml refil | <Flags(allows_duplicate_labels=True)> |
| tenda | Bazar e Utilidades | Kit Amendoim Yoki 420g com Guardanapos Scott 50 Unidades | Pra Você | Yoki (inferida) | 420g un 50un  | <Flags(allows_duplicate_labels=True)> |
| assai | Outros | Pimenta bode mape bj 300g | Generico | Mape (inferida) | 300g  | <Flags(allows_duplicate_labels=True)> |
| atacadao | Bazar e Utilidades | Bule Térmico Soprano Sonetto 750ml un |  | Soprano (inferida) | 750ml  | <Flags(allows_duplicate_labels=True)> |
| atacadao | Bazar e Utilidades | Caderno Fuzy Foroni 160 folhas un |  | Foroni (inferida) | 160folha un 160folha  | <Flags(allows_duplicate_labels=True)> |
| atacadao | Bazar e Utilidades | Prato Descartável Bio Trik Trik Neon Rosa 15cm 10un |  | Trik Trik (inferida) | dim:15cm un 10un  | <Flags(allows_duplicate_labels=True)> |

### B2
| rede | dept | título | marca origem | marca | tamanho | flags |
|---|---|---|---|---|---|---|
| goodbom | Bebidas | BEBIDA LACTEA YOPRO 15G DOCE DE LEITE HAVANNA 250ML | Danone | Danone | 15g  | <Flags(allows_duplicate_labels=True)> |
| tenda | Higiene | Enxaguante Bucal 500ml + Desodorante Aerosol Men 100ml Above | Above | Above | 500ml  | <Flags(allows_duplicate_labels=True)> |
| savegnago | Higiene | Sabonete Líquido 310ml e Loção Hidratante 200g Baunilha Flores E Vegetais | FLORES E VEGETAIS |  | 310ml  | <Flags(allows_duplicate_labels=True)> |
| sao-vicente | Higiene | Kit Protetor Solar Protect & Hidrata Nivea Fps30 De 200ml Grátis Protetor Solar Protect & Hidrata Facial Nivea Fps 30 De 100ml | Nivea | Nivea | 200ml  | <Flags(allows_duplicate_labels=True)> |
| atacadao | Pet Shop | Alimento para Cães Bonzo Carne e Cereais 18kg gts 2kg | Bonzo | Bonzo | 18000g  | <Flags(allows_duplicate_labels=True)> |
| assai | Higiene | Desod gillete aero 93g/150ml antibac | Gillette | Gillette | 93g  | <Flags(allows_duplicate_labels=True)> |
| pague-menos | Higiene | Pack Shampoo Skala Frutástica Abacate 325ml + Condicionador 200ml | Skala | Skala | 325ml  | <Flags(allows_duplicate_labels=True)> |
| dalben | Padaria | Bolo Casa Suica 350g-370g Clássico Laranja |  | Casa Suíça (inferida) | 350g  | <Flags(allows_duplicate_labels=True)> |
| arena-atacado | Saudáveis e Orgânicos | Adoçante Em Pó 3 Corações Sucralose Sachê C/ 244,8g Unid. 408g | 3 Coracoes | 3 Coracoes | 244.8g sache | <Flags(allows_duplicate_labels=True)> |
| goodbom | Bazar e Utilidades | REQUEIJÃO TIROLEZ 17G PRO+ 180G | Tirolez | Tirolez | 17g  | <Flags(allows_duplicate_labels=True)> |

### B3
| rede | dept | título | marca origem | marca | tamanho | flags |
|---|---|---|---|---|---|---|
| assai | Outros | Faca p/mesa treviso simonaggio | Simonaggio | Simonaggio |   | <Flags(allows_duplicate_labels=True)> |
| dalben | Bazar e Utilidades | Pilha Panasonic Alc.cr2032 |  | Panasonic (inferida) |   | <Flags(allows_duplicate_labels=True)> |
| savegnago | Bazar e Utilidades | Travesseiro Camesa Micro Cotton Super Médio Sortido 50X70cm | CAMESA | CAMESA |   | <Flags(allows_duplicate_labels=True)> |
| sao-vicente | Bazar e Utilidades | Flor Natural Dendrobium Nobily Pote 12 | Flor Natural | Flor Natural |  pote | <Flags(allows_duplicate_labels=True)> |
| goodbom | Hortifruti | ROSEIRA PT13 |  | sem marca (não importa) |   | <Flags(allows_duplicate_labels=True)> |
| atacadao | Bazar e Utilidades | Sandália F1 Futebol Rider 42 Branco/Azul Par | Rider | Rider |   | <Flags(allows_duplicate_labels=True)> |
| tenda | Bazar e Utilidades | Feira de Potes Plásticos Color SR10/49 Sanremo | Sanremo | Sanremo |   | <Flags(allows_duplicate_labels=True)> |
| pague-menos | Higiene | Tiara de Cabelo Marco Boni Minnie | Marco Boni | Marco Boni |   | <Flags(allows_duplicate_labels=True)> |
| arena-atacado | Limpeza | Bloco Higiênico Pato Caixa Acoplada Marine Leve 3 Pague 2 | Pato | Pato |  caixa | <Flags(allows_duplicate_labels=True)> |
| davitta | Hortifruti | HORTIFRUTI MACA FUGI FRUTIM PCT |  | sem marca (não importa) |  pacote | <Flags(allows_duplicate_labels=True)> |

### B4
| rede | dept | título | marca origem | marca | tamanho | flags |
|---|---|---|---|---|---|---|
| goodbom | Bebidas | BEBIDA ALCOOLICA BEATS GREEN MIX LT 269ML |  |  | 269ml lata | <Flags(allows_duplicate_labels=True)> |
| dalben | Bebidas | Vinho Tinto Mascara De Fuego 750ml Carmenere |  |  | 750ml  | <Flags(allows_duplicate_labels=True)> |
| atacadao | Frios e Laticínios | Fondue de Queijo Supremo 400g |  |  | 400g  | <Flags(allows_duplicate_labels=True)> |
| spani | Bebidas | Vinho Uruguaio La Hacienda 750ml Merlot |  |  | 750ml  | <Flags(allows_duplicate_labels=True)> |
| davitta | Mercearia | ACUCAR CRISTAL MIRANTE 2KG |  |  | 2000g  | <Flags(allows_duplicate_labels=True)> |
| assai | Frios e Laticínios | Mant Cenaggio Pt 500g C/S |  |  | 500g  | <Flags(allows_duplicate_labels=True)> |
| sao-vicente | Bebidas | Cerveja Original Lata 350ml C/ 12 Unid. | Original |  | 350ml pack 12 un 12un lata | <Flags(allows_duplicate_labels=True)> |
| arena-atacado | Bebidas | Cerveja Nacional Original Lata 269ml | Original |  | 269ml lata | <Flags(allows_duplicate_labels=True)> |
| pague-menos | Bebidas | Cerveja Original Pilsen 350ml Com 12 Unidades | Original |  | 350ml un 12un  | <Flags(allows_duplicate_labels=True)> |
| savegnago | Higiene | Shampoo Flores e Vegetais Matizante Cinza Platinado 310ml | FLORES E VEGETAIS |  | 310ml  | <Flags(allows_duplicate_labels=True)> |

### C
| rede | dept | título | marca origem | marca | tamanho | flags |
|---|---|---|---|---|---|---|
| atacadao | Outros | Kit Suplemento Centrum Essencial 30CP + 30CP |  |  |   | <Flags(allows_duplicate_labels=True)> |
| goodbom | Frios e Laticínios | ESPONJA DE  BANHO  DELICATA |  |  |   | <Flags(allows_duplicate_labels=True)> |
| dalben | Limpeza | Saco Alvejado Zenaleti Xadrez |  |  |  saco | <Flags(allows_duplicate_labels=True)> |
| assai | Outros | Osso no mini p/caes mais dog | Mais dog |  |   | <Flags(allows_duplicate_labels=True)> |
| tenda | Bebidas | Kit Cerveja Ipa com Hambúrguer de Picanha | Pra Você |  |   | <Flags(allows_duplicate_labels=True)> |
| davitta | Outros | ESPC SEMENTE DE GIRASSOL ( PEPI |  |  |   | <Flags(allows_duplicate_labels=True)> |
| spani | Congelados | Pacote Frango Asa Congelado Confina Todo Dia |  |  |  pacote | <Flags(allows_duplicate_labels=True)> |
| goodbom | Mercearia | COLORAÇÃO IMÉDIA CASTANHO CLARO 5 |  |  |   | <Flags(allows_duplicate_labels=True)> |
| goodbom | Higiene | ESCOVA PARA MAMADEIRA E BICO ROSA |  |  |   | <Flags(allows_duplicate_labels=True)> |
| dalben | Higiene | Acessórios Brink Biju |  |  |   | <Flags(allows_duplicate_labels=True)> |

## Suspeitos / erros que ainda restam (por grupo)
- **B1:** `Kit Amendoim Yoki … Scott` e `Kit Pipoca Yoki com Guaraná Antarctica`: kit com 2 marcas, marca origem lixo "Pra Você" (a inferência escolhe uma); `Pimenta bode mape` com origem "Generico" → inferiu `Mape` (marca de origem inválida era o certo: produto sem marca ou marca Mape, conferir); `Alimento com Aveia Barista A Tal Da Castanha` inferência correta mas `1L` ok.
- **B2:** `YOPRO 15G … 250ML` e `Requeijão Tirolez 17G PRO+ 180G` (proteína sem a palavra "proteína": falta regra para `PRO`/`PRO+`/`YOPRO`); `Bonzo 18kg gts 2kg` (`gts` = grátis); `Bolo Casa Suíça 350g-370g` (intervalo); `Adoçante … Sachê C/ 244,8g Unid. 408g` (total x unidade); kit Nivea com "Grátis"; `Flores e Vegetais` perdeu a marca por causa da lista de inválidas.
- **B3:** itens com medida mal escrita ou sem unidade: `Pilha Panasonic Alc.cr2032` (modelo), `Pote 12`, `Roseira PT13` (vaso), `Feira de Potes SR10/49`; `Leve 3 Pague 2` de rolos não vira contagem; `Flor Natural`/`Marco Boni` como marca de origem; `MAÇA FUGI … PCT` sem peso.
- **B4:** `Original` (cerveja Original, 3 de 10!) e `Flores e Vegetais` são marcas reais removidas pela lista de inválidas (q9); `Lo'r` (grafia errada de L'Or) não casa; Beats, Mascara de Fuego, La Hacienda, Mirante, Cenaggio, Supremo: faltam no dicionário.
- **C:** `Kit Suplemento Centrum 30CP + 30CP` (CP = comprimidos); `Osso … mais dog` (Mais dog é marca real de brinquedo pet); `ESPC SEMENTE DE GIRASSOL ( PEPI` título truncado; `Kit Cerveja Ipa com Hambúrguer` não é item de prateleira; `COLORAÇÃO IMÉDIA CASTANHO CLARO 5` (nº de tom).
- **Contagens:** `Porta Ovos … Dúzia` virou 1 dz (porta-ovos não é ovo); a base tem só 29 itens em dúzias.
- **Marca de origem inválida (q9):** recomendo tirar `Original` e `Flores e Vegetais` da lista, ou exigir contexto (ex.: só quando o departamento não for Bebidas/Higiene).

## Pendências sugeridas
1. Retirar `Original`/`Flores e Vegetais` da blacklist ou condicionar por departamento.
2. Regra de proteína (`PRO`, `PRO+`, `YOPRO`, `whey`) e `gts`, intervalos `350g-370g`, `NNCP` (comprimidos).
3. Aprovar candidatos em `brand-candidates.csv` (coluna `approve`, hoje só os 8 aprovados estão marcados `SIM`).
4. Amostrar grupo R (1.021) e A1 por GTIN antes de gravar.
