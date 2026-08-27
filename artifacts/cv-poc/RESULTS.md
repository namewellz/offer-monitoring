# PoC de detecção de ofertas sem modelo generativo

Método: OpenCV, segmentação de painéis de preço e agrupamento geométrico. O Qwen não participa desta PoC.

| Página | Esperadas | Âncoras detectadas | Cobertura por contagem | Avaliação visual |
|---|---:|---:|---:|---|
| 1 | 26 | 23 | 88,5% | Âncoras reais, mas caixas inadequadas no layout irregular |
| 2 | 45 | 45 | 100% | Melhor resultado; grade praticamente isolada |
| 3 | 44 | 40 | 90,9% | Caixas utilizáveis; quatro ofertas sem painel `DE R$` omitidas |
| 4 | 20 | 17 | 85% | Caixas utilizáveis; três ofertas com estilo diferente omitidas |
| 5 | 16 | 12 | 75% | Reprovada; painéis claros confundidos com logos e textos |
| **Total** | **151** | **137** | **90,7%** | A contagem não representa precisão geométrica |

## Conclusão

O sinal visual de preço é suficiente para páginas de grade com `DE/POR`, mas não constitui um detector generalista. A página 5 comprova que regras de cor não generalizam para outros layouts, mesmo dentro do mesmo encarte.

O próximo passo tecnicamente justificável é manter este detector como gerador de pré-anotações e treinar um detector de uma classe (`offer_block`) com páginas de diferentes supermercados. A avaliação deverá usar caixas estruturadas e IoU, reservando supermercados inteiros para teste.
