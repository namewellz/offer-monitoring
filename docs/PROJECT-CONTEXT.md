# Contexto do projeto Offer Monitoring

Última atualização: 2026-09-01.

Este documento registra o objetivo do produto, o estado atual da implementação,
as decisões tomadas e os motivos por trás delas. Ele deve ser lido junto com
[`INFRASTRUCTURE.md`](INFRASTRUCTURE.md) e
[`DEPLOY-ORACLE.md`](DEPLOY-ORACLE.md).

## 1. Objetivo

O Offer Monitoring centraliza catálogos e ofertas de supermercados para:

- pesquisar produtos de várias redes em uma única interface;
- filtrar por departamento com uma nomenclatura comum;
- consultar preços por supermercado e filial;
- identificar ofertas e condições especiais de preço;
- acompanhar variações entre coletas;
- preservar um histórico auditável;
- executar e acompanhar atualizações automáticas ou manuais;
- continuar aproveitando a estrutura anterior de encartes e extração por visão.

O foco operacional atual é a região de Hortolândia/SP. Quando uma fonte não
possui a filial desejada, a loja de referência existente é registrada de forma
explícita, sem fingir que o preço pertence a Hortolândia.

## 2. Escopos que convivem no mesmo sistema

Há dois fluxos relacionados, mas independentes.

### 2.1 Catálogos estruturados

É o fluxo usado pelo painel `/catalog` e pelas oito fontes atuais. Os coletores
consultam APIs ou endpoints dos e-commerces, normalizam os campos e persistem
uma fotografia datada dos produtos e preços.

```text
Scheduler ou atualização manual
        ↓
Redis/RQ (fila flyers)
        ↓
Worker → coletor da fonte → API/site do supermercado
        ↓
JSON em /data/catalog/<fonte> + PostgreSQL
        ↓
Painel, busca, ofertas, variações e log de atualização
```

### 2.2 Encartes e extração visual

É o fluxo original da aplicação. Providers descobrem encartes, as imagens são
armazenadas em `/data`, regiões podem ser revisadas em `/annotation` e a
extração usa Qwen3-VL via Ollama quando `DISCOVERY_ENABLED=true`.

Na Oracle esse fluxo está desabilitado porque não há Ollama configurado no
servidor. O histórico migrado continua acessível; `ollama=false` no `/health` é
esperado nessa configuração.

## 3. Fontes atuais

| Fonte | Integração | Filial ou referência | Identificadores disponíveis | Observações |
|---|---|---|---|---|
| Arena Atacado | Demandware `Search-UpdateGrid` | catálogo público da rede | ID interno da fonte | percorre departamentos e remove duplicados |
| GoodBom | GraphQL Mercafácil | loja 2, Hortolândia | ID/model ID; sem EAN confiável no payload atual | preserva clube, atacado, estoque e variantes |
| Atacadão | VTEX + simulação de checkout | Vila Maria, CEP `02170-901`, seller `atacadobr60` | EAN e código de referência | a simulação confirma preço e disponibilidade por loja |
| Savegnago | VTEX + simulação de checkout | LJ 55 Hortolândia, CEP `13184-222` | EAN e código de referência | combina catálogo completo e coleção `Ofertas da Semana` |
| Davitta | MobileSIM autenticada por token | Loja 04 Monte Mor, `store_id=101` | barcode/EAN, SKU e offer ID | mantém preço comum, promocional e Connect |
| Assaí | APIs autenticadas do Meu Assaí | Assaí Hortolândia, store 175/code 173 | EAN, product ID e ID interno | mantém varejo, atacado e preço do app |
| Tenda | API pública do e-commerce | CT39 Tenda Hortolândia, branch 46, CEP `13184-222` | barcode/EAN e SKU | atualmente bloqueada pelo WAF para o IP da Oracle |
| São Vicente | Demandware com seleção de loja | loja 018 São Vicente Hortolândia | ID interno da fonte; sem EAN no payload atual | seleciona a loja antes de percorrer departamentos |

EAN/GTIN é armazenado quando a fonte o fornece e ele passa pela validação
numérica. A ausência de EAN não impede a coleta.

## 4. Identidade de produtos e códigos

### 4.1 Código da fonte

`CatalogProduct.external_id` é o identificador original e estável da fonte. A
chave lógica atual é:

```text
(retailer_id, external_id)
```

Esse código não deve ser reescrito, reutilizado como código canônico global ou
substituído por um resultado de IA. Ele é necessário para reconciliar uma nova
coleta com o mesmo item e para manter a auditoria até o sistema de origem.

`internal_code` e `ean` são atributos adicionais. Eles também preservam o valor
recebido da fonte, depois apenas de validações de formato e tamanho.

### 4.2 Código canônico entre supermercados

Ainda não existe uma entidade canônica de produto entre redes. Produtos de
varejistas diferentes permanecem separados, mesmo quando parecem representar o
mesmo item.

Uma evolução segura deve criar novas tabelas de resolução de entidades, sem
alterar os códigos de origem. A ordem de evidências recomendada é:

1. EAN/GTIN válido e coincidente;
2. marca e fabricante normalizados;
3. descrição, variante, unidade, quantidade e embalagem;
4. similaridade textual;
5. sugestão por IA;
6. revisão humana para casos ambíguos.

A IA deve sugerir ligações e apresentar confiança/evidências. Ela não deve
sobrescrever automaticamente o produto original. Esse desenho reduz falsos
positivos e permite desfazer uma associação sem perder histórico.

## 5. Categorias e departamentos

Cada produto guarda dois conceitos:

- `categories`: categorias originais da fonte, preservadas para auditoria;
- `department`: departamento canônico compartilhado entre as fontes.

Departamentos canônicos atuais:

```text
Açougue
Bebidas
Bazar e Utilidades
Congelados
Doces e Sobremesas
Frios e Laticínios
Higiene
Hortifruti
Limpeza
Mercearia
Padaria
Peixaria
Pet Shop
Saudáveis e Orgânicos
Outros
```

A classificação prioriza a categoria recebida da fonte e usa o nome do produto
como fallback. As regras são determinísticas em `app/catalog/taxonomy.py`.

Por que manter os dois campos:

- a categoria original explica como o supermercado organizou o item;
- o departamento canônico torna filtros e comparações consistentes;
- uma regra nova pode reclassificar o histórico sem nova coleta;
- erros de classificação não destroem o dado bruto.

O comando `python -m app.cli reclassify-catalog` reaplica a taxonomia.

## 6. Preços, ofertas e histórico

`CatalogProduct` representa a identidade do item dentro de uma rede.
`CatalogPriceObservation` representa seu estado em uma coleta e filial.

Cada observação pode guardar:

- preço regular;
- preço atual/de venda;
- preço anterior;
- diferença absoluta e percentual;
- disponibilidade e estoque;
- filial (`store_id`);
- preços por quantidade (`tier_prices`);
- tags de oferta (`offer_tags`);
- desconto informado ou calculado.

O histórico é append-only: uma coleta nova cria observações novas. Metadados do
produto podem ser atualizados para refletir a fonte atual, mas observações
anteriores não são reescritas.

A variação compara apenas com a observação imediatamente anterior do mesmo
produto e da mesma filial. Isso evita comparar preços de lojas diferentes.

A aba **Em oferta** usa sinais explícitos da fonte — tags, desconto, preço
promocional ou condição especial — em vez de assumir que todo preço menor é uma
oferta.

## 7. Preços por filial

O modelo já vincula `CatalogRun` e `CatalogPriceObservation` a `Store`. Portanto,
o histórico de preço é estruturalmente preparado para filiais.

O que ainda precisa mudar para coletar várias filiais da mesma rede:

- configurar uma lista de filiais por coletor;
- executar seleção/simulação de loja para cada filial;
- não misturar sessões e cookies entre lojas;
- persistir uma execução e observações com o `store_id` correto;
- incluir filial nos controles de deduplicação e locks quando necessário;
- revisar custo, duração, limites e volume do banco.

O impacto é aproximadamente proporcional ao número de filiais quando a API
exige repetir catálogo ou simulação. Fontes que retornam inventário de várias
filiais em um único payload podem ser mais eficientes.

## 8. Tolerância a falhas

Uma falha de página, categoria ou lote não deve invalidar toda a fonte.

Os coletores acumulam resultados válidos e registram problemas como:

```json
{
  "scope": "department=123 page=4",
  "error": "HTTPStatusError: ..."
}
```

Regras de status:

- `SUCCESS`: coleta sem problemas registrados;
- `PARTIAL_SUCCESS`: existem produtos utilizáveis e uma ou mais partes falharam;
- `FAILED`: não foi possível produzir nenhum produto utilizável ou uma etapa
  essencial — autenticação, seleção de loja ou descoberta inicial — falhou.

Uma execução parcial é persistida para auditoria, mas não substitui a última
fotografia integral usada como referência principal do painel. Isso evita que
uma página ausente faça milhares de itens parecerem removidos.

## 9. Fila e concorrência

Todos os trabalhos usam a fila RQ `flyers`. Existe um lock por fonte e uma chave
de deduplicação: pedidos repetidos enquanto a mesma fonte está na fila ou em
execução reutilizam o job existente.

O ambiente atual tem um worker. Logo, fontes são processadas em sequência. A
escolha reduz concorrência contra sites externos, simplifica o diagnóstico e
controla memória/CPU. Mais workers podem reduzir a janela total, mas exigem
revisão dos limites das fontes e dos recursos do servidor.

## 10. Interfaces e endpoints principais

| Recurso | Endereço |
|---|---|
| Painel principal | `/catalog` |
| Log por fonte | `/catalog/updates` |
| Departamentos | `GET /catalog/departments` |
| Ofertas | `GET /catalog/offers` |
| Variações | `GET /catalog/price-changes` |
| Histórico de um produto | `GET /catalog/price-history` |
| Atualizar todas as fontes | `POST /catalog/collections` |
| Atualizar uma fonte | `POST /catalog/collections/{retailer_slug}` |
| Consultar job | `GET /catalog/collections/jobs/{job_id}` |
| Histórico de jobs | `GET /catalog/collections/jobs` |
| Saúde | `GET /health` |
| Revisão de encartes | `/annotation` |
| Documentação OpenAPI | `/docs` |

O painel foi feito para desktop e possui media queries para celular. A tela de
logs agrupa execuções por fonte, mostra quantidade de itens/com preço e lista
cada falha separadamente.

## 11. Diagnóstico do Tenda na Oracle

### Evidência funcional

Foram executadas coletas reais na Oracle após a migração. Arena, GoodBom,
Atacadão, Savegnago, Davitta, Assaí e São Vicente terminaram com:

```text
RQ status: finished
outcome: SUCCESS
warnings: 0
```

O Tenda terminou com:

```text
RQ status: failed
HTTP 403 Forbidden
GET https://api.tendaatacado.com.br/api/public/store/departments
```

O ciclo automático das 22:00 de 2026-09-01 repetiu o mesmo resultado: sete
fontes concluídas e Tenda bloqueado antes da primeira página.

### Evidência de rede/WAF

A URL foi chamada diretamente a partir da Oracle com:

- `curl` simples;
- User-Agent de Chrome;
- `Origin` e `Referer` do Tenda;
- `Accept`, `Accept-Language` e cabeçalhos `Sec-Fetch-*`;
- cookie obtido antes na página principal.

Todas as tentativas retornaram HTTP 403, `server: nginx`,
`x-azion-request-id` e a página `Azion - Default error page` com título
`Forbidden`. O mesmo código havia coletado o Tenda no ambiente local.

Conclusão: o bloqueio ocorre antes da lógica de paginação e é consistente com
regra de WAF/reputação para a origem de saída da Oracle. Não foi inferido por
uma mensagem genérica do aplicativo; foi aferido pelo job, traceback, resposta
HTTP e repetição direta fora do coletor.

Próximas opções, em ordem de segurança:

1. solicitar ao Tenda/liberação oficial uma forma de acesso de servidor;
2. usar uma rota de saída/proxy apropriado e autorizado;
3. testar outro provedor/região de infraestrutura;
4. manter o histórico existente e a falha visível enquanto não houver rota.

Não é recomendável mascarar o erro, tratar 403 como página vazia ou apagar o
histórico anterior.

### Rota via proxy (2026-09-02)

A opção 2 foi implementada no coletor: a variável `TENDA_PROXY_URL` (vazia por
padrão) é aplicada somente ao `TendaCatalogClient`. Quando configurada, todas as
chamadas HTTP do Tenda passam por esse forward proxy; as demais fontes seguem
saindo diretamente.

Configuração mínima de um forward proxy para essa rota:

- autenticação obrigatória (`Proxy-Authorization`), para não virar proxy aberto;
- allowlist de hosts de destino (apenas `api.tendaatacado.com.br` e
  `www.tendaatacado.com.br`).

Transporte adotado em produção: **Tailscale**. O proxy roda na máquina de
desenvolvimento (nó `desktop-0lfqfru`, IP tailnet `100.103.174.68`) e a Oracle
(`100.107.197.65`) o alcança pela tailnet em `http://<token>@100.103.174.68:3128`.
Não há exposição pública nem regra de firewall externa; o tráfego Oracle → proxy
é criptografado pela tailnet.

Validação local (2026-09-02): com `TENDA_PROXY_URL` apontando para o proxy na
máquina de desenvolvimento, a coleta do Tenda retornou 7.879 produtos e os logs
do proxy confirmaram os túneis CONNECT para `api.tendaatacado.com.br`.

Ativação em produção (2026-09-02): `TENDA_PROXY_URL` foi adicionado ao
`.env.production` da Oracle apontando para o IP tailnet do proxy, e a stack foi
recriada. Coleta confirmada via worker sem override: 7.932 produtos e
`catalog_run` com sucesso.

Dependência operacional: a coleta do Tenda depende da máquina que roda o proxy
estar ligada e conectada à tailnet. Se ela ficar indisponível, o Tenda volta ao
403 e o histórico/falha permanecem visíveis.

## 12. Decisões importantes e porquês

### Preservar códigos da fonte

Garante rastreabilidade e reconciliação. Um código canônico global deve ser uma
camada adicional, nunca uma substituição.

### PostgreSQL para histórico

O volume de observações, relacionamentos por filial e consultas de variação
exigem integridade, índices e transações. JSON/CSV continuam como artefatos de
auditoria, não como fonte principal do painel.

### Redis/RQ para coleta

Uma requisição web não deve ficar aberta durante minutos. A fila oferece
timeouts, estados, deduplicação e histórico operacional.

### Categorias determinísticas antes de IA

Regras explícitas são baratas, reproduzíveis e auditáveis. IA pode ajudar em
resolução de entidades e exceções, mas precisa guardar evidência e confiança.

### Coleta parcial

Sites externos falham de forma intermitente. Manter páginas válidas aumenta a
disponibilidade sem esconder o que ficou incompleto.

### Imagens multi-arquitetura

O desenvolvimento ocorre em amd64 e a Oracle usa arm64. Publicar ambos os
manifests evita build manual no servidor e mantém o deploy reproduzível.

## 13. Limitações e riscos conhecidos

- Tenda está bloqueado pelo WAF para o IP atual da Oracle.
- Não existe ainda código canônico de produto entre redes.
- A maioria das fontes coleta uma filial fixa; múltiplas filiais ainda exigem
  parametrização dos coletores.
- O painel e os endpoints de atualização não têm autenticação própria. Como o
  domínio é público, deve-se considerar autenticação no Caddy ou na aplicação.
- O backup recorrente atual possui retenção local, mas ainda não tem cópia fora
  da Oracle.
- Um único worker torna a janela total longa, embora reduza carga e risco.
- Contratos não oficiais de sites podem mudar sem aviso.
- O banco cresce a cada observação; retenção, particionamento e índices devem ser
  revistos conforme o número de filiais aumentar.
- A interface possui CSS responsivo, mas o checklist de validação em aparelho
  físico permanece pendente.

## 14. Prioridades recomendadas

1. proteger o domínio e os endpoints POST com autenticação;
2. configurar backup externo e testar a restauração desse backup automático;
3. decidir a estratégia de saída para o Tenda;
4. criar o modelo de produto canônico com revisão assistida;
5. parametrizar filiais sem alterar códigos de origem;
6. adicionar métricas/alertas para jobs falhos, tamanho do banco e backups;
7. revisar capacidade antes de aumentar workers ou frequência.
