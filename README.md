# Offer Monitoring

PoC local e auditavel para descobrir encartes, baixar as imagens originais, extrair ofertas com Qwen3-VL via Ollama e persistir o historico no PostgreSQL. Este Milestone 1 suporta o GoodBom Monte Mor; as interfaces de provider, fila e extracao sao genericas para os proximos supermercados.

## Requisitos

- Docker Desktop com Docker Compose
- Ollama no host Windows
- Modelo `qwen3-vl:8b`: `ollama pull qwen3-vl:8b`

Verifique com `ollama list`. Copie `.env.example` para `.env` e ajuste se necessario:

```bash
copy .env.example .env
```

## Subir e usar

```bash
docker compose up -d --build
docker compose exec api alembic upgrade head
docker compose exec api python -m app.cli seed
docker compose exec api python -m app.cli discover-all
docker compose logs -f worker
```

Swagger: http://localhost:8000/docs. Health: `curl http://localhost:8000/health`.

`GET /offers` pesquisa ofertas e `GET /offers/{id}` retorna o registro com suas embalagens e condicoes de preco.

## Revisao das regioes de oferta

Acesse http://localhost:8000/annotation para revisar as regioes propostas por visao computacional antes da extracao. No editor e possivel criar, mover, redimensionar e excluir caixas; salvar a revisao; aprovar a pagina; e exportar somente as paginas aprovadas no formato COCO em `GET /annotation/export/coco`.

As coordenadas sao armazenadas normalizadas de 0 a 1000, preservando a correspondencia com a imagem original em qualquer resolucao. A aprovacao e sempre explicita: gerar uma pre-anotacao nunca aprova a pagina automaticamente.

Para descobrir manualmente uma fonte, obtenha seu UUID em `GET /stores`/banco e execute:

```bash
docker compose exec api python -m app.cli discover --source <id>
docker compose exec api python -m app.cli extract --flyer <id> --strategy tiles --force
```

O scheduler usa `DISCOVERY_CRON`; o padrao vem de `.env` e nao e codificado. A descoberta cria jobs RQ e o worker chama `http://host.docker.internal:11434` por padrao. O lock de cada job usa `JOB_LOCK_TIMEOUT_SECONDS` e deve ser maior que o maior timeout da fila.

`QWEN_REQUEST_TIMEOUT_SECONDS` limita cada chamada ao Ollama. Dez segundos favorecem falha rapida; aumente para imagens grandes ou hardware mais lento.

## Adicionar supermercados

Providers cuidam apenas de localizar encartes e paginas originais. Download, hash, fila, extracao e banco sao compartilhados. Consulte [docs/ADDING_PROVIDERS.md](docs/ADDING_PROVIDERS.md) para implementar e registrar uma nova rede.

O Arena Atacado possui um catalogo estruturado separado dos encartes. Para coletar todos os produtos, incluindo precos regulares, promocionais e faixas de atacado, execute:

```bash
docker compose exec api python -m app.cli arena-catalog --output /app/artifacts/arena
```

O comando consulta `Search-UpdateGrid`, percorre os departamentos publicos, remove produtos repetidos por ID, persiste produtos e observacoes de preco datadas no PostgreSQL e gera JSON e CSV. Cada execucao cria um `catalog_run`; o historico fica em `catalog_price_observations`, incluindo preco normal, promocional, faixas por quantidade, estoque e disponibilidade.

O catálogo estruturado do GoodBom Hortolândia também pode ser coletado e persistido:

```bash
docker compose exec api python -m app.cli goodbom-catalog --output /app/artifacts/goodbom-catalog
```

Essa fonte usa o GraphQL público da Mercafácil e armazena preço normal, desconto, clube, atacado, estoque e a data da observação vinculados à loja de Hortolândia.

O catalogo publico do Atacadao (VTEX) pode ser coletado com:

```bash
docker compose exec api python -m app.cli atacadao-catalog --output /app/artifacts/atacadao-catalog
```

O coletor percorre as categorias para respeitar o limite de paginacao da API e persiste cada
SKU com EAN, codigo interno, preco de lista, preco de venda e data da observacao. Os precos e a
disponibilidade sao confirmados pela simulacao de compra do CEP `02170-901`, canal 1, seller
`atacadaobr60`, e vinculados a loja Atacadao Vila Maria.

## Coletas agendadas e variacao de preco

O scheduler envia as coletas estruturadas de Arena, GoodBom, Atacadao, Savegnago, Davitta,
Assaí, Tenda Atacado e São Vicente para a fila tres vezes
ao dia, por padrao as `06:00`, `14:00` e `22:00` no fuso `America/Sao_Paulo`. A configuracao
fica nas variaveis `CATALOG_COLLECTION_ENABLED`, `CATALOG_COLLECTION_CRON` e
`SCHEDULER_TIMEZONE`.

Cada coleta acrescenta novas observacoes; registros anteriores nunca sao atualizados nem
removidos. A variacao usa estritamente a observacao imediatamente anterior do mesmo SKU e loja.
A tela de acompanhamento fica em http://localhost:8000/catalog e a API de variacoes em
`GET /catalog/price-changes`, com filtros `product`, `retailer`, `direction`,
`department`, `minimum_percent` e `limit`. Todos os coletores preservam as categorias originais
da fonte em `source_categories` e também gravam um departamento canônico compartilhado:
`Açougue`, `Bebidas`, `Higiene`, `Hortifruti`, `Limpeza`, `Mercearia` e os demais retornados por
`GET /catalog/departments`. O historico completo de um produto pode ser auditado em
`GET /catalog/price-history?product_id=<uuid>` ou pelo EAN em
`GET /catalog/price-history?ean=<ean>`.

Quando a taxonomia for ampliada, reaplique-a ao histórico sem executar novas coletas:

```bash
docker compose exec api python -m app.cli reclassify-catalog
```

O Savegnago combina o catalogo completo da busca com a colecao publica `Ofertas da Semana`.
Produtos da colecao recebem a tag `weekly-offers` na observacao, sem duplicar o SKU. A coleta
usa exclusivamente a loja `Hortolândia - Hortolândia - LJ 55`: os preços e a disponibilidade
são confirmados pela simulação de compra do CEP `13184-222`, canal 1, seller 1, e vinculados ao
pickup point `Retira Loja 55` antes da gravação no banco. A coleta
manual pode ser executada com:

```bash
docker compose exec api python -m app.cli savegnago-catalog --output /data/catalog/savegnago
```

O Davitta consulta a API MobileSIM usando a filial `Loja 04 – Monte Mor` (`store_id=101`) e
descobre dinamicamente a aba `OFERTAS`. Preço comum, preço promocional e preço exclusivo
Clube/Connect são preservados separadamente. O token permanece fora do repositório e é lido do
arquivo configurado em `DAVITA_TOKEN_FILE_HOST`. Para executar manualmente:

```bash
docker compose exec api python -m app.cli davitta-catalog --output /data/catalog/davitta
```

O Assaí usa o catálogo autenticado do Meu Assaí para a loja `175` (Assaí Hortolândia,
`storeCode=173`). As credenciais pessoais ficam somente no `.env`; a configuração técnica é
extraída do bundle montado em `ASSAI_BUNDLE_FILE_HOST`, e tokens Cognito nunca são gravados.
Preço de varejo, atacado e exclusivo do aplicativo são mantidos separadamente. Execução manual:

```bash
docker compose exec api python -m app.cli assai-catalog --output /data/catalog/assai
```

O Tenda Atacado usa a API pública do e-commerce com o mesmo CEP de referência dos demais
coletores (`13184-222`). A disponibilidade e o estoque são filtrados para a filial `CT39`
(`Tenda Hortolândia`), enquanto promoções públicas, preços por quantidade e ofertas do app
são preservados no histórico:

```bash
docker compose exec api python -m app.cli tenda-catalog --output /data/catalog/tenda
```

O São Vicente seleciona a loja `018` (São Vicente Hortolândia) antes de consultar o catálogo
Demandware. A coleta preserva preços, faixas por quantidade, estoque e disponibilidade da loja:

```bash
docker compose exec api python -m app.cli saovicente-catalog --output /data/catalog/sao-vicente
```

A tela `/catalog` permite iniciar uma atualização manual de qualquer supermercado. Solicitações
repetidas para uma fonte que já está na fila ou em execução reutilizam o mesmo trabalho.

## Dados e rastreabilidade

Assets ficam no volume `/data/raw/<retailer>/<store UUID>/<flyer UUID>/`. Cada pagina persiste hash SHA-256, dimensoes, MIME, tamanho, URL, ETag e Last-Modified. Respostas integrais do modelo ficam em `extraction_attempts`; cada oferta aponta para pagina e extraction run. Um hash agregado das paginas impede nova extracao para o mesmo conteudo da mesma loja.

## Testes

```bash
pip install -e ".[dev]"
ruff check .
pytest
```

Testes nao acessam os sites nem o Ollama. Integracoes reais devem ser marcadas com `external`.

## Limitacoes atuais

- Apenas GoodBom Monte Mor esta cadastrado pelo seed deste milestone.
- A extracao divide cada pagina em quatro regioes sobrepostas, extrai cada uma separadamente e consolida ofertas duplicadas. A sobreposicao evita perder produtos que cruzam as linhas centrais.
- O parser GoodBom depende da configuracao publica conter JSON com `pages[].src`; uma alteracao e registrada como erro de parser, sem tentativa de contornar protecoes.
