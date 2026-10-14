# Auditoria de códigos e nomes — 14/09/2026

## Resultado e escopo

Leitura direta do PostgreSQL local, banco flyer. Nenhuma oferta, classificação ou vínculo foi alterado. O PostgreSQL estava parado e foi iniciado para permitir as consultas. Não foi necessário chamar LLM externa.

Foram examinados 191.109 produtos identificados por (catalog_sources.id, source_products.external_id), com 340.137 versões em public.source_product_versions. Há 148.960 produtos com pelo menos duas versões e 149.028 transições entre versões consecutivas. Isso não é o número de coletas nem de alterações de nome.

Resultado: 59 alterações de nome em 59 produtos; 7 são apenas caixa/acentuação segundo normalização conservadora de caracteres. As 52 restantes não representam necessariamente produtos diferentes: incluem expansão de abreviações, reordenação, correções e remoção de detalhes. Não foi encontrado um caso inequívoco de substituição por um produto totalmente diferente nas diferenças de nome, marca, GTIN e medida examinadas. Existem mudanças relevantes de identidade comercial que precisam de revisão.

A base contém 211 execuções legadas de coleta, entre 23/08/2026 23:14 e 08/09/2026 13:02, horário de São Paulo. Portanto, esta análise feita em 14/09 não implica coletas até 14/09.

## Distribuição por fonte

| Fonte | Produtos | Com ≥2 versões | Versões | Mudanças de nome | % sobre ≥2 versões | Trocas no campo EAN |
|---|---:|---:|---:|---:|---:|---:|
| Atacadão | 55.950 | 55.785 | 111.800 | 17 | 0,030% | 1 |
| Assaí | 42.911 | 42.911 | 85.822 | 0 | 0,000% | 1 |
| Dalben | 17.685 | 0 | 17.685 | Sem histórico comparável | Não mensurável | 0 |
| Savegnago | 15.537 | 14.997 | 30.534 | 3 | 0,020% | 6 |
| Pague Menos | 13.798 | 0 | 13.798 | Sem histórico comparável | Não mensurável | 0 |
| São Vicente | 10.739 | 10.264 | 21.006 | 3 | 0,029% | 0 |
| Tenda | 10.067 | 7.857 | 17.924 | 5 | 0,064% | 0 |
| GoodBom | 9.539 | 8.777 | 18.316 | 27 | 0,308% | 0 |
| Arena | 7.903 | 7.580 | 15.483 | 0 | 0,000% | 0 |
| Spani | 5.594 | 0 | 5.594 | Sem histórico comparável | Não mensurável | 0 |
| Davita | 792 | 212 | 1.004 | 3 | 1,415% | 0 |
| Max | 594 | 577 | 1.171 | 1 | 0,173% | 0 |

No total, 59/148.960 = 0,0396% dos produtos com pelo menos duas versões têm mudança de nome. Esse percentual descreve apenas as versões preservadas; não é uma taxa diária nem uma estimativa de toda a vida do catálogo. Produtos com uma versão podem ter sido observados repetidamente sem alteração. Dalben, Pague Menos e Spani têm somente uma versão por produto: não se deve interpretar isso como estabilidade comprovada.

## Limitação crítica: a migração não recuperou nomes antigos

O legado catalog_products sobrescreve name, brand e ean. catalog_price_observations preserva preços, mas não guarda o nome associado àquela observação. O backfill criou a versão inicial a partir do cadastro corrente, utilizando first_seen_at como valid_from. Logo, um nome cuja versão começa em agosto não está comprovadamente preservado desde aquela primeira coleta de agosto.

A comparação disponível, na maioria dos casos, é o cadastro migrado em 02/09 contra uma coleta posterior. Das 59 alterações de nome, 52 têm baseline de backfill e apenas 7 são entre duas versões originadas de coletas scheduled: 4 do Atacadão e 3 do São Vicente. O esquema catalog_v2 de Go contém 55.950 produtos Atacadão e 120 Savegnago, todos com somente uma versão, e não amplia a cobertura temporal.

A consulta examina a base de dados. Os arquivos JSON avulsos de artifacts não foram incorporados como um histórico adicional, pois isso exigiria verificar cobertura, origem e datas de cada snapshot.

## Código reutilizado ou cadastro corrigido?

É comprovado que o mesmo código recebe dados de identidade diferentes ao longo do histórico. Não é possível afirmar apenas com esses dados se houve troca física de produto, redução de embalagem, correção de cadastro ou variação entre lojas.

Casos prioritários:

| Fonte | external_id | Antes → depois | Interpretação |
|---|---|---|---|
| São Vicente | 1005120 | Frutap Morango 170g → 160g | Mudança de quantidade no nome, sem GTIN disponível. Duas coletas reais do mesmo target, de 02/09 22:31 para 04/09 16:35 (São Paulo). |
| São Vicente | 797448 | Frutap Uva 170g → 160g | Mesmo padrão acima; exige separar/revisar a apresentação comercial antes de comparar preços. |
| Atacadão | 774 | Drops IceKiss Azedinha Sortido → Morango, 12 un | Sabor mudou no texto; GTIN permaneceu 7896286620253. Pode ser correção ou mudança de variante. |
| Atacadão | 781 e 787 | Açaí 3,6kg → 3,6L | Unidade mudou; não converter kg em L automaticamente. GTIN permaneceu igual em cada código. |
| Savegnago | 1121 | Palmito Bonduelle 520g → 270g | Possível distinção entre peso total e drenado, hipótese não confirmada; mesmo GTIN. |
| Tenda | 44396 | Coco Bahia Seco Unidade → Coco Seco Kg | Base de venda contraditória entre títulos; raw_measure continuou BD. |
| Davita | 78113 | Cerveja Império 350ML C/15 → 350M | Perdeu informação de pacote e unidade no texto; indício de truncamento, não prova de mudança de produto. |
| Assaí | 90926, 45229 e 2910 | raw_measure UN → KG | Três pães Panebras; os nomes já continham kg e não mudaram. Provável correção de unidade; invisível para uma auditoria limitada aos nomes. |

Há também remoção de “Wandinha” do Oreo no São Vicente e alterações de descrição de hidratantes/sabonetes. Não há troca de marca não vazia por outra marca não vazia. As 19 alterações de marca são preenchimentos de marca antes ausente no GoodBom. Das 31 mudanças em raw_measure, 28 são preenchimentos vazio → un no GoodBom e 3 são UN → KG no Assaí. Não houve mudança em raw_quantity, raw_unit ou raw_package nas versões comparadas; isso não exclui quantidades alteradas dentro do nome.

## Trocas de EAN sob o mesmo código

São 8 códigos: 6 Savegnago, 1 Atacadão e 1 Assaí. Em todos, o nome permaneceu igual. Sete pares têm dois GTINs com comprimento e dígito verificador válidos; validade matemática não comprova atribuição correta pelo fabricante. O Assaí passou de um GTIN válido para uma sequência de 9 dígitos, que não é um GTIN de comprimento padrão.

| Fonte | Código | Nome | EAN anterior | EAN posterior |
|---|---|---|---|---|
| Atacadão | 63399 | Água Mineral Bulnez Sem Gás 1,5L | 7898944548343 | 7898944548275 |
| Assaí | 83870 | Ling t paio def aurora 400g | 7891164005825 | 838700013 |
| Savegnago | 12720 | Molho Pimenta Gallo 50ml Com Azeite | 5601252113644 | 5601252111602 |
| Savegnago | 16511 | Vinho Brasileiro Country Wine 750ml Suave Tinto | 7891141024559 | 7891141011986 |
| Savegnago | 22043 | Aspargo Branco La Violetera 205g | 7891089071134 | 7891089071127 |
| Savegnago | 5670 | Gin Bombay 750ml | 764175742263 | 5010677715201 |
| Savegnago | 9880 | Azeite Português Gallo 500ml Vidro Tipo Único | 7891042101670 | 5601252106103 |
| Savegnago | 989904232 | Lava Roupa Pó Omo Todo Ciclo 2,2Kg | 7891150199347 | 7891150199262 |

Os códigos antigos e novos também foram procurados nos demais nomes da base. Não surgiu evidência de classes de produtos completamente diferentes associadas a esses pares. Isso mantém os oito casos como alterações de identificador a revisar, e não como reutilização comprovada.

## Fonte versus filial

A chave atual de source_products é (source_id, external_id), sem filial. first_run_id permite identificar o target que originou cada versão, mas não registra todas as reconfirmações de um nome em cada loja.

Das 59 mudanças de nome, 31 têm target anterior diferente do posterior: 27 GoodBom e 4 Atacadão. No Atacadão, são versões de coletas reais entre Vila Maria e Campinas Jd. Yeda. No GoodBom, o baseline usa o target Monte Mor atribuído pelo backfill e a coleta posterior é Hortolândia. Como o backfill escolhe um target de referência, isso não prova que todos os nomes antigos vieram de Monte Mor. Portanto, não se pode tratar as 31 ocorrências como mudanças temporais comprovadas dentro da mesma filial.

## Todas as 59 mudanças de nome

“Anterior” significa a versão anterior disponível, não necessariamente a primeira coleta real. Datas abaixo são da observação posterior em UTC. A origem backfill deve ser interpretada conforme a ressalva acima.

| Fonte | Código | Nome anterior | Nome posterior | Data posterior UTC | Baseline | Target antes → depois | Apenas forma |
|---|---|---|---|---|---|---|---|
| Atacadão | 10111 | Sabonete Clássico Francis Groselha Negra e Cedro 90g | Sabonete Clássico Francis Preto 90g | 2026-09-08 15:53:31 | scheduled | 38 → 51 | Não |
| Atacadão | 24114 | Sorvete Variatta 3 leites 1,8L | Sorvete Variatta 3 Leites 1,8L | 2026-09-03 15:51:57 | backfill | 38 → 38 | Sim |
| Atacadão | 33357 | Desodorante Aerossol Suave Jasmim e coco 200ml | Desodorante Aerossol Suave Jasmim e Coco 200ml | 2026-09-03 15:51:57 | backfill | 38 → 38 | Sim |
| Atacadão | 33383 | Desodorante Aerossol Suave Sport fresh 200ml | Desodorante Aerossol Suave Sport Fresh 200ml | 2026-09-03 15:51:57 | backfill | 38 → 38 | Sim |
| Atacadão | 37177 | Loção Hidratante Des Monange Flor de lavanda 200ml | Loção Hidratante Desodorante Monange Flor de lavanda 200ml | 2026-09-03 15:51:57 | backfill | 38 → 38 | Não |
| Atacadão | 37181 | Loção Hidratante Des Monange Frutas vermelhas 200ml | Loção Hidratante Desodorante Monange Frutas Vermelhas 200ml | 2026-09-03 15:51:57 | backfill | 38 → 38 | Não |
| Atacadão | 37188 | Loção Hidratante Des Monange Pele extrasseca 200ml | Loção Hidratante Desodorante Monange Pele Extrasseca 200ml | 2026-09-03 15:51:57 | backfill | 38 → 38 | Não |
| Atacadão | 38397 | Desinfetante Urca Lavanda 2L | Desinfetante Urca Flor de Lavanda 2L | 2026-09-08 15:53:31 | scheduled | 38 → 51 | Não |
| Atacadão | 40732 | Loção Hidratante Q10 Monange Pele Extrasseca 400ml | Loção Hidratante Monange Q10 Pele Extrasseca 400ml | 2026-09-03 15:51:57 | backfill | 38 → 38 | Não |
| Atacadão | 4265 | Água Mineral Nossa Água 200ml | Água Mineral Nossa Água Sem Gás 200ml | 2026-09-08 15:53:31 | scheduled | 38 → 51 | Não |
| Atacadão | 43 | Loção Hidratante Monange Frutas vermelhas 400ml | Loção Hidratante Monange Frutas Vermelhas 400ml | 2026-09-03 15:51:57 | backfill | 38 → 38 | Sim |
| Atacadão | 55 | Loção Hidratante Monange Pele Extrasseca 200ml | Loção Hidratante Monange Q10 200ml | 2026-09-03 15:51:57 | backfill | 38 → 38 | Não |
| Atacadão | 58 | Loção Hidratante Monange Pele extrasseca 400ml | Loção Hidratante Monange Pele Extrasseca 400ml | 2026-09-03 15:51:57 | backfill | 38 → 38 | Sim |
| Atacadão | 5924 | Margarina Coamo Com sal 500g | Margarina Coamo Com Sal 500g | 2026-09-08 15:53:31 | scheduled | 38 → 51 | Sim |
| Atacadão | 774 | Drops IceKiss Azedinha Sortido 12 un | Drops IceKiss Azedinha Morango 12 un | 2026-09-03 15:51:57 | backfill | 38 → 38 | Não |
| Atacadão | 781 | Açaí Maori Congelado 3,6kg | Açaí Maori Congelado 3,6L | 2026-09-03 15:51:57 | backfill | 38 → 38 | Não |
| Atacadão | 787 | Açaí Marujinho Congelado 3,6kg | Açaí Marujinho Congelado 3,6L | 2026-09-03 15:51:57 | backfill | 38 → 38 | Não |
| Davita | 78113 | CERV IMPERIO PURO MALTE LT 350ML C/15 | CERV IMPERIO PURO MALTE LT 350M | 2026-09-03 16:01:18 | backfill | 40 → 40 | Não |
| Davita | 81118 | CERV MICHELOB ULRA LN 330ML | CERV MICHELOB ULTRA LN 330ML | 2026-09-03 16:01:18 | backfill | 40 → 40 | Não |
| Davita | 89521 | CERV IMPERIO ULTRA ZERO  LN 275ML | CERV IMPERIO ULTRA ZERO  LN 275 | 2026-09-03 16:01:18 | backfill | 40 → 40 | Não |
| GoodBom | 31111 | CR.DENT.COLGATE LUMINOUS WHITE C.COR.99G | CREME DENTAL COLGATE LUMINOUS WHITE COLOR CORRECT 99G | 2026-09-03 15:48:05 | backfill | 36 → 37 | Não |
| GoodBom | 31112 | SAB.PROTEX ANTIBAC.LIMPEZA PROFUNDA125G | SABONETE PROTEX ANTIBACTERIANO LIMPEZA PROFUNDA 125G | 2026-09-03 15:48:05 | backfill | 36 → 37 | Não |
| GoodBom | 31113 | SH.PALMOLIVE CUID.ESP.BOND REPAIR 315ML | SHAMPOO PALMOLIVE CUIDADOS ESPECIAIS BOND REPAIR 315ML | 2026-09-03 15:48:05 | backfill | 36 → 37 | Não |
| GoodBom | 31328 | FR.FOFURA BABY HIPER XG C/58 | FRALDA FOFURA BABY HIPER XG C/58 | 2026-09-03 15:48:05 | backfill | 36 → 37 | Não |
| GoodBom | 31329 | FR.FOFURA BABY MEGA M C/34 | FRALDA FOFURA BABY MEGA M C/34 | 2026-09-03 15:48:05 | backfill | 36 → 37 | Não |
| GoodBom | 31330 | FR.FOFURA BABY MEGA XXG C/22 | FRALDA FOFURA BABY MEGA XXG C/22 | 2026-09-03 15:48:05 | backfill | 36 → 37 | Não |
| GoodBom | 31331 | FR.FOFURA BABY MEGA G C/28 | FRALDA FOFURA BABY MEGA G C/28 | 2026-09-03 15:48:05 | backfill | 36 → 37 | Não |
| GoodBom | 31332 | FR.FOFURA BABY HIPER XXG C/50 | FRALDA FOFURA BABY HIPER XXG C/50 | 2026-09-03 15:48:05 | backfill | 36 → 37 | Não |
| GoodBom | 31333 | FR.FOFURA BABY MEGA XG C/24 | FRALDA FOFURA BABY MEGA XG C/24 | 2026-09-03 15:48:05 | backfill | 36 → 37 | Não |
| GoodBom | 31334 | FR.FOFURA BABY HIPER G C/64 | FRALDA FOFURA BABY HIPER G C/64 | 2026-09-03 15:48:05 | backfill | 36 → 37 | Não |
| GoodBom | 31335 | FR.FOFURA BABY MEGA P C/36 | FRALDA FOFURA BABY MEGA P C/36 | 2026-09-03 15:48:05 | backfill | 36 → 37 | Não |
| GoodBom | 31336 | FR.FOFURA BABY HIPER M C/72 | FRALDA FOFURA BABY HIPER M C/72 | 2026-09-03 15:48:05 | backfill | 36 → 37 | Não |
| GoodBom | 31351 | LIMP.PESADA VEJA C/CLORO 1L LV+PG- | LIMPADOR LIMPEZA PESADA VEJA C/CLORO 1L LV+PG- | 2026-09-03 15:48:05 | backfill | 36 → 37 | Não |
| GoodBom | 31352 | LIMP.PESADA VEJA ORIGINAL 500ML LV+PG- | LIMPADOR LIMPEZA PESADA VEJA ORIGINAL 500ML LV+PG- | 2026-09-03 15:48:05 | backfill | 36 → 37 | Não |
| GoodBom | 31354 | LIMP.LIMO VEJA X-14 CLORO GAT.500ML LV+PG- | LIMPADOR LIMO VEJA X-14 CLORO GATILHO 500ML LV+PG- | 2026-09-03 15:48:05 | backfill | 36 → 37 | Não |
| GoodBom | 31355 | LIMP.PESADA VEJA C/CLORO 500ML LV+PG- | LIMPADOR LIMPEZA PESADA VEJA C/CLORO 500ML LV+PG- | 2026-09-03 15:48:05 | backfill | 36 → 37 | Não |
| GoodBom | 31357 | LIMPA VIDRO VEJA VIDREX C/ALCOOL 500ML LV+PG- | LIMPA VIDRO VEJA VIDREX C/ÁLCOOL 500ML LV+PG- | 2026-09-03 15:48:05 | backfill | 36 → 37 | Sim |
| GoodBom | 31358 | DET.TABLETE P/MAQ.LAVAR FINISH P.QUANTUM C/60 | DETERGENTE TABLETE P/MAQUÍNA DE LAVAR FINISH POWEBALL QUANTUM C/60 | 2026-09-03 15:48:05 | backfill | 36 → 37 | Não |
| GoodBom | 31359 | LIMP.PESADA VEJA ORIGINAL 1L LV+PG- | LIMPADOR LIMPEZA PESADA VEJA ORIGINAL 1L LV+PG- | 2026-09-03 15:48:05 | backfill | 36 → 37 | Não |
| GoodBom | 31360 | DET.TABLETE P/MAQ.LAVAR FINISH P.QUANTUM C/26 | DETERGENTE TABLETE P/MAQUÍNA DE LAVAR FINISH POWERBALL QUANTUM C/26 | 2026-09-03 15:48:05 | backfill | 36 → 37 | Não |
| GoodBom | 31362 | LIMP.PERF.VEJA AGUAS MARANHENSES 1L | LIMPADOR PERFUMADO VEJA ÁGUAS MARANHENSES 1L | 2026-09-03 15:48:05 | backfill | 36 → 37 | Não |
| GoodBom | 31363 | LIMP.PERF.VEJA AGUAS MARANHENSES 2L | LIMPADOR PERFUMADO VEJA ÁGUAS MARANHENSES 2L | 2026-09-03 15:48:05 | backfill | 36 → 37 | Não |
| GoodBom | 31366 | DESOD.HARPIC CLICK GEL BRISA MAR C/3 | DESODORANTE HARPIC CLICK GEL BRISA MAR C/3 | 2026-09-03 15:48:05 | backfill | 36 → 37 | Não |
| GoodBom | 31367 | DESOD.HARPIC CLICK GEL FLORES VERAO C/3 | DESODORANTE HARPIC CLICK GEL FLORES VERAO C/3 | 2026-09-03 15:48:05 | backfill | 36 → 37 | Não |
| GoodBom | 31368 | LIMP.PERF.VEJA AGUAS MARANHENSES 500ML | LIMPADOR PERFUMADO VEJA ÁGUAS MARANHENSES 500ML | 2026-09-03 15:48:05 | backfill | 36 → 37 | Não |
| GoodBom | 31371 | DESINF.HARPIC CLORO FORTE 750ML PG+LV- | DESINFETANTE HARPIC CLORO FORTE 750ML PG+LV- | 2026-09-03 15:48:05 | backfill | 36 → 37 | Não |
| GoodBom | 31373 | DESINF.HARPIC MARINE 750ML PG+LV- | DESINFETANTE HARPIC MARINE 750ML PG+LV- | 2026-09-03 15:48:05 | backfill | 36 → 37 | Não |
| Max | 323147 | ENERG RED BULL POMELO EDITION 473ML | ENERG RED BULL 473ML POMELO EDITION | 2026-09-03 16:16:53 | backfill | 44 → 44 | Não |
| São Vicente | 1005120 | Leite Fermentado Desnatado Frutap Morango 170g | Leite Fermentado Desnatado Frutap Morango 160g | 2026-09-04 19:35:59 | scheduled | 43 → 43 | Não |
| São Vicente | 640107 | Biscoito Recheado Oreo Chocolate Wandinha 90g | Biscoito Recheado Oreo Chocolate 90g | 2026-09-04 19:35:59 | scheduled | 43 → 43 | Não |
| São Vicente | 797448 | Leite Fermentado Desnatado Frutap Uva 170g | Leite Fermentado Desnatado Frutap Uva 160g | 2026-09-04 19:35:59 | scheduled | 43 → 43 | Não |
| Savegnago | 1121 | Palmito Bonduelle 520g Pupunha Picado | Palmito Bonduelle Pupunha Picado 270g | 2026-09-03 15:59:16 | backfill | 39 → 39 | Não |
| Savegnago | 4765 | Azeite Italiano Filippo Berio Trufado 250ml | Molho Base Azeite Oliva Com Trufa Filippo Berio 250ml | 2026-09-03 15:59:16 | backfill | 39 → 39 | Não |
| Savegnago | 8985 | Azeite Italiano Empório Tartufi 100ml | Moho Azeite Empório Tartufi Tartufo Bianco 100ml | 2026-09-03 15:59:16 | backfill | 39 → 39 | Não |
| Tenda | 1021 | Abacaxi Pérola Unidade | Abacaxi Fresco Unidade \| Tenda Atacado | 2026-09-03 16:12:34 | backfill | 42 → 42 | Não |
| Tenda | 44396 | Coco Bahia Seco Unidade | Coco Seco Kg \| Tenda Atacado | 2026-09-03 16:12:34 | backfill | 42 → 42 | Não |
| Tenda | 5013 | Uva Crimson Bandeja 500g | Uva Vermelha sem Semente 500g \| Tenda Atacado | 2026-09-03 16:12:34 | backfill | 42 → 42 | Não |
| Tenda | 5434 | Sabonete Líquido Cabeça Aos Pés Johnsons Baby 200ml | Sabonete Líquido Infantil Johnsons Cabeça aos Pés 200ml | 2026-09-03 16:12:34 | backfill | 42 → 42 | Não |
| Tenda | 7551 | Uva Vitória Bandeja 500g | Uva Preta sem Semente 500g \| Tenda Atacado | 2026-09-03 16:12:34 | backfill | 42 → 42 | Não |

## Consequência para o catálogo canônico

Usar (fonte, código) para localizar o registro de origem, mas usar fingerprint dos campos de identidade para decidir se a classificação pode ser reaproveitada. O fingerprint deve cobrir nome, marca, GTIN, medida, quantidade e embalagem disponíveis. Mudanças cosméticas podem reutilizar o resultado após normalização; mudanças de quantidade, unidade, sabor ou identificador exigem nova validação.

Preservar o vínculo canônico por versão de origem. Uma alteração de 170g para 160g não deve reescrever silenciosamente o produto ao qual os preços antigos pertenciam. Guardar também observação por filial para distinguir variação simultânea entre lojas de alteração temporal. Armazenar snapshots brutos imutáveis e seus hashes evita a perda de histórico vista no legado.

## Reprodutibilidade

A consulta SQL acompanhante é somente leitura. Ordena versões por (version,id), compara cada uma com a anterior por source_product_id e agrupa pela fonte. Inclui casos de EAN/marca/medida que não alteraram o nome.

Arquivos de código consultados:
- app/catalog/persistence.py: atualização do cadastro legado.
- app/catalog/v2/backfill.py: baseline e atribuição de valid_from/target.
- app/catalog/v2/ingest.py: chave de origem e criação de versões.
- app/db/models.py e app/db/models_v2.py: campos persistidos e restrições.

Nenhuma mudança de implementação foi feita nesta auditoria.

