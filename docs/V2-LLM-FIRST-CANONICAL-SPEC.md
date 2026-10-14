# Especificação técnica V2 — catálogo canônico progressivo com resolução LLM-first

Última atualização: 2026-09-07.

Status: **especificação para implementação e validação experimental**.

Documento relacionado: [`CATALOG-COLLECTION-AND-ENRICHMENT.md`](CATALOG-COLLECTION-AND-ENRICHMENT.md).

Esta especificação mantém as decisões já tomadas para fontes, filiais, execuções,
produtos originais, versões imutáveis e períodos de preço. Ela substitui, para a
V2, a estratégia de enriquecimento que colocava a normalização determinística
como intérprete principal. A estratégia definida aqui é **LLM-first**: todo novo
conteúdo de identidade de produto é interpretado uma vez por uma LLM com saída
estruturada; fingerprints, cache, candidatos, validações objetivas e revisão
humana garantem idempotência, consistência e auditabilidade.

---

## 1. Decisão arquitetural

A V2 será um monólito modular com processamento assíncrono e quatro planos
claramente separados:

1. **Plano de coleta:** obtém e preserva dados de cada fonte e filial.
2. **Plano de interpretação:** usa LLM para extrair identidade comercial
   estruturada de cada versão de produto.
3. **Plano de resolução:** relaciona a interpretação a conceitos, variantes e
   itens comerciais canônicos progressivos.
4. **Plano de leitura:** mantém projeções prontas para busca, lista de compras,
   comparação de preço e detecção de promoções.

```text
Orquestrador
    ↓ tarefas por fonte + filial
Workers de coleta
    ├── PostgreSQL: execução e manifesto
    ├── Object storage: payload bruto imutável
    └── Outbox/fila: evento de coleta
              ↓
Normalização LLM-first versionada
              ↓
Geração de candidatos canônicos
              ↓
Validação + resolução
    ├── automática
    ├── segunda avaliação
    ├── proposta de novo canônico
    └── revisão humana
              ↓
Catálogo canônico progressivo
              ↓
Projeções incrementais de leitura
    ├── busca/autocomplete
    ├── lista e otimizador de compras
    ├── comparação cross-market
    └── inteligência de promoções
```

### 1.1 Escolha de implantação

Não serão criados microsserviços independentes nesta fase. A mesma base de
código será executada em processos separados:

- `api`: rotas HTTP e painel administrativo;
- `collector-worker`: coleta de fontes;
- `enrichment-worker`: inferência, candidatos e resolução;
- `projection-worker`: atualização de read models;
- `scheduler`: criação de tarefas conforme SLA e freshness;
- PostgreSQL;
- Redis ou broker equivalente;
- object storage S3-compatible.

Os processos podem escalar horizontalmente. A separação física em serviços só
será considerada quando métricas demonstrarem contenção, necessidades de
segurança diferentes ou evolução por equipes distintas.

### 1.2 Decisões fechadas

- PostgreSQL é a fonte de verdade.
- Payloads brutos são imutáveis e reprocessáveis.
- A fila transporta eventos e referências, não é o arquivo histórico.
- Entrega é `at-least-once`; consumidores são idempotentes.
- Preço pertence à listagem da filial, nunca diretamente ao produto canônico.
- Alteração apenas de preço ou estoque não chama a LLM.
- Toda interpretação e resolução guarda modelo, prompt, schema, política e
  evidências.
- A LLM nunca sobrescreve dado original nem resolução humana bloqueada.
- Uma página de usuário nunca executa inferência nem reconstrói todo o catálogo.
- Categoria canônica não é sinônimo de identidade canônica.

### 1.3 Hipóteses a validar

- Uma chamada LLM estruturada por nova versão de identidade oferece melhor
  precisão/custo que regras determinísticas extensas.
- Lotes de 20 a 50 itens mantêm qualidade sem exceder contexto ou produzir
  omissões frequentes.
- Busca textual, aliases e embeddings conseguem trazer o candidato correto para
  o top 10 na maior parte dos casos.
- Uma segunda avaliação apenas para casos ambíguos e propostas novas mantém o
  custo controlado.
- Políticas por família são mais estáveis que prompts livres por categoria.

Estas hipóteses não serão assumidas como verdade em produção; terão métricas e
experimentos descritos na seção de testes.

---

## 2. Objetivos e requisitos de produto

### 2.1 Objetivos primários

- relacionar o mesmo item comercial entre várias redes e filiais;
- comparar produtos equivalentes com o grau correto de precisão;
- suportar descrições abreviadas, siglas, erros e vocabulários próprios das
  fontes;
- preservar o catálogo canônico de maneira progressiva, revisável e auditável;
- processar produtos novos automaticamente sem bloquear coleta ou interface;
- impedir repetição de custo quando a identidade recebida não mudou;
- disponibilizar todo produto em algum estado operacional, sem desaparecimentos
  silenciosos;
- permitir expansão para muitas fontes sem reimplementar persistência,
  orquestração e enriquecimento;
- sustentar posteriormente lista otimizada de compras e identificação de
  promoções reais.

### 2.2 Objetivos de qualidade

- precisão alta em associações automáticas exatas;
- falsa união de produtos deve ser significativamente menos frequente que
  fragmentação temporária;
- correções humanas não podem regredir silenciosamente;
- todo resultado precisa ser reproduzível a partir do input, configuração e
  versões armazenadas;
- filas e backlogs precisam ser mensuráveis;
- custo de inferência precisa ser atribuível por fonte, família, modelo e versão;
- reprocessamento deve ser seletivo, reiniciável e idempotente.

### 2.3 Fora do escopo inicial

- treinamento ou fine-tuning próprio de modelo;
- publicação automática no Instagram;
- otimização geográfica avançada com trânsito em tempo real;
- comparação nutricional;
- identidade global de fabricantes além do necessário para os produtos;
- extração visual de encartes integrada à primeira entrega do resolvedor;
- microsserviços por domínio;
- dependência obrigatória de GTIN/EAN.

---

## 3. Linguagem de domínio

| Termo | Definição |
| --- | --- |
| Fonte | Namespace técnico de onde produtos e preços são coletados. |
| Alvo de coleta | Configuração da fonte para uma filial, CEP, seller ou canal. |
| Produto da fonte | Identidade estável dentro da fonte, normalmente por ID externo. |
| Versão do produto da fonte | Conteúdo descritivo imutável criado quando a identidade recebida muda. |
| Listagem | Produto da fonte comercializado em um alvo/filial. |
| Estado comercial | Preço, condições, disponibilidade e estoque da listagem. |
| Interpretação | Estrutura de identidade extraída pela LLM de uma versão da fonte. |
| Conceito | Necessidade ampla de compra, como `Arroz`, `Maçã` ou `Cerveja`. |
| Variante | Especificação comparável, como `Maçã Fuji` ou `Cerveja Pilsen`. |
| Item comercial | Produto embalado exato, como `Heineken lata 350 ml`. |
| Alias | Forma textual observada que fornece evidência para uma entidade canônica. |
| Candidato | Entidade canônica potencial apresentada ao resolvedor. |
| Resolução | Decisão versionada que liga uma versão da fonte ao catálogo canônico. |
| Proposta canônica | Possível nova entidade ainda não consolidada. |
| Política | Regras estruturadas de identidade e comparação por família. |
| Read model | Projeção otimizada para consultas de produto, preço ou lista. |

### 3.1 Níveis de identidade

```text
Conceito: Cerveja
  └── Variante: Cerveja Pilsen
       └── Item comercial: Heineken Lata 350 ml
            ├── listagem no Dalben Campinas
            ├── listagem no GoodBom Hortolândia
            └── listagem no Pague Menos Rosolém
```

Para um produto embalado, a resolução ideal chega a `trade_item_id`. Para um
produto vendido por peso, como carne ou hortifrúti, a política pode encerrar a
resolução em `variant_id`, pois não existe necessariamente um item industrial
exato compartilhado entre lojas.

### 3.2 Relações distintas

Não será usado um único conceito de “produto igual”. A API e o banco devem
distinguir:

- `EXACT`: mesmo item comercial;
- `VARIANT_EQUIVALENT`: mesma variante comparável, mas sem prova de item exato;
- `CONCEPT_RELATED`: mesmo conceito amplo;
- `SUBSTITUTE`: substituto comercial configurado;
- `NOT_COMPARABLE`: apenas compartilha departamento ou categoria.

---

## 4. Arquitetura dos coletores

### 4.1 Unidade de trabalho

A unidade de coleta é:

```text
catalog_source + collection_target + collection_run
```

`collection_target` representa filial, contexto de entrega ou retirada, seller,
canal e CEP. A mesma rede pode ter vários targets.

### 4.2 Camadas

```text
Collector worker genérico
  └── Adaptador de plataforma
       └── Configuração de rede/target
```

O worker cuida de:

- ciclo de vida do job;
- leases e locks;
- timeout;
- retry e backoff;
- métricas;
- persistência do manifesto;
- publicação pela outbox.

O adaptador cuida de:

- autenticação e sessão;
- seleção correta da filial;
- paginação;
- interpretação do protocolo da fonte;
- preservação dos campos brutos;
- sinalização de completude e erros parciais.

Configuração cuida de:

- URL base;
- IDs de loja e seller;
- canal de venda;
- CEP;
- política de rate limit;
- política de egress/proxy autorizado;
- cron/freshness;
- segredos por referência, nunca por texto no banco público.

### 4.3 Contrato do adaptador

```python
class CatalogAdapter(Protocol):
    adapter_name: str
    adapter_version: str

    async def collect(
        self,
        target: CollectionTargetConfig,
        context: CollectionContext,
    ) -> CollectionArtifact:
        ...
```

`CollectionArtifact` contém:

- manifesto da execução;
- itens brutos;
- estado comercial bruto;
- erros por escopo;
- contagens esperadas e observadas;
- indicador de completude;
- payloads auxiliares;
- checksums.

### 4.4 Envelope de item bruto

```json
{
  "event_id": "uuid-v7",
  "run_id": "uuid-v7",
  "source_id": "dalben-vipcommerce",
  "target_id": "dalben-campinas",
  "retailer_id": "dalben",
  "store_id": "uuid",
  "external_product_id": "12345",
  "external_listing_id": "12345:campinas",
  "observed_at": "2026-09-07T17:00:00Z",
  "collector": "vipcommerce",
  "collector_version": "2.1.0",
  "schema_version": "raw-catalog-item-1",
  "raw_identity": {
    "name": "CERV HEINEKEN LT 350ML",
    "brand": null,
    "categories": ["BEBIDAS", "CERVEJAS"],
    "gtin": null,
    "measure": "UN",
    "description": null,
    "package": null,
    "attributes": {}
  },
  "raw_commercial_state": {
    "currency": "BRL",
    "regular_price_cents": 499,
    "effective_price_cents": 399,
    "available": true,
    "stock": null,
    "price_terms": []
  },
  "raw_payload_uri": "s3://offer-monitoring/raw/...json.gz",
  "raw_payload_sha256": "hex"
}
```

### 4.5 Payload bruto e eventos

O payload integral deve ser gravado antes de publicar o evento. A ordem é:

1. coletar;
2. gravar artefato imutável;
3. persistir run e referências em transação;
4. gravar `outbox_event` na mesma transação;
5. publicador envia o evento;
6. consumidor reconhece de forma idempotente.

Mensagens de fila devem conter IDs e URIs, não catálogos completos.

### 4.6 Completude e ausência

Uma execução só pode desativar listagens ausentes quando:

- `is_complete=true`;
- todas as páginas/cursores esperados foram processados;
- nenhuma falha cobre um escopo que poderia conter o produto;
- a fonte declara uma fotografia completa, e não apenas ofertas ou resultados
  parciais.

---

## 5. Identidades, versões e fingerprints

### 5.1 Identidade do produto da fonte

Chave lógica:

```text
(catalog_source_id, external_product_id)
```

A filial não faz parte dessa chave quando a fonte utiliza o mesmo produto em
várias lojas. A filial pertence à `store_listing`.

Se uma API reutilizar IDs por filial, o namespace da `catalog_source` deve ser
configurado para refletir isso ou o external ID deve receber um prefixo técnico
determinístico documentado.

### 5.2 Canonicalização para hashing

Antes de calcular hashes:

- strings recebem Unicode NFKC;
- `CRLF` e `CR` viram `LF`;
- espaços externos são removidos;
- sequências de whitespace viram um espaço, exceto campos que preservam texto;
- valores ausentes têm representação única `null`;
- números são serializados em forma decimal canônica;
- objetos usam chaves ordenadas;
- arrays preservam ordem quando ela expressa hierarquia;
- campos desconhecidos ficam em `raw_attributes`, com chaves ordenadas.

O valor bruto original permanece preservado. A canonicalização existe apenas
para hash e não pode substituir o conteúdo recebido.

### 5.3 `raw_payload_hash`

SHA-256 do payload bruto armazenado. Serve para integridade e replay, não para
decidir se a identidade mudou.

### 5.4 `identity_fingerprint`

SHA-256 de JSON canônico contendo somente campos capazes de alterar identidade:

```json
{
  "name": "...",
  "brand": "...",
  "gtin": "...",
  "categories": [],
  "description": "...",
  "measure": "...",
  "quantity": "...",
  "unit": "...",
  "package": "...",
  "identity_attributes": {}
}
```

Não entram:

- preço;
- estoque;
- disponibilidade;
- tags promocionais;
- URL de imagem se a imagem não for usada na inferência;
- URL do produto;
- timestamps;
- posição em paginação.

Se uma imagem ou OCR passar a compor a inferência, seu hash entra em
`identity_fingerprint` ou em um `visual_identity_fingerprint` versionado.

### 5.5 `commercial_state_hash`

SHA-256 de:

- preço regular;
- preço efetivo;
- melhor preço condicionado;
- termos comerciais normalizados;
- disponibilidade;
- estoque, se a política de histórico exigir;
- validade da promoção;
- moeda.

Esse hash controla períodos de preço. Ele não dispara enriquecimento.

### 5.6 Chaves de cache da inferência

Existem duas chaves porque interpretação semântica e decisão contra candidatos
possuem ciclos de invalidação diferentes.

`interpretation_cache_key` é SHA-256 de:

```text
identity_fingerprint
+ model_provider
+ model_name
+ model_revision
+ interpretation_prompt_version
+ output_schema_version
+ policy_version
```

Ela responde: “este conteúdo de identidade já foi interpretado por esta versão
do pipeline?”. Uma coleta repetida consulta essa chave e não chama a LLM.

`resolution_request_hash` é SHA-256 de:

```text
interpretation_fingerprint
+ resolver_model_provider
+ resolver_model_name
+ resolver_model_revision
+ resolver_prompt_version
+ policy_version
+ candidate_set_hash
+ inference_mode
```

Ela responde: “esta interpretação já foi avaliada contra exatamente estes
candidatos?”. O cache é exato; não será usado cache semântico para assumir que
textos ou conjuntos apenas parecidos têm a mesma resposta.

Uma chamada primária combinada pode produzir interpretação e resolução de uma
vez, mas deve registrar ambas as chaves. O crescimento normal do catálogo não
invalida automaticamente interpretações ou resoluções aprovadas. Um novo
candidate set só dispara chamada quando o item continua sem resolução, está em
baixa confiança ou participa de campanha explícita de reavaliação.

### 5.7 Quando executar novamente a LLM

A inferência é necessária quando pelo menos uma condição ocorre:

- não existe interpretação compatível com a versão atual do pipeline;
- `identity_fingerprint` mudou;
- política ativa exige reprocessamento;
- prompt/schema/modelo mudou e a campanha de reprocessamento incluiu o item;
- resolução está em baixa confiança ou erro recuperável;
- conjunto de candidatos mudou materialmente e a política permite reavaliação;
- correção humana abriu um incidente sistêmico.

Reprocessar cria novas linhas imutáveis. Nunca atualiza ou apaga a interpretação
ou resolução anterior.

---

## 6. Modelo de dados proposto

### 6.1 Convenções

- PK interna `bigint generated always as identity` para índices compactos;
- `public_id uuid` quando a entidade for exposta externamente;
- `timestamptz` sempre em UTC;
- dinheiro em centavos inteiros na moeda original;
- quantidade em `numeric`, nunca `float`;
- JSONB apenas para extensibilidade, evidências e payloads; campos consultados
  frequentemente devem ser colunas;
- tabelas de decisão são append-only;
- ponteiros `current_*` podem ser atualizados em transação;
- FKs e uniques devem representar invariantes reais.

### 6.2 Coleta e armazenamento bruto

#### `raw_ingestion_objects`

| Campo | Tipo | Regra |
| --- | --- | --- |
| `id` | bigint | PK |
| `public_id` | uuid | unique |
| `run_id` | bigint | FK |
| `object_type` | varchar | catalog, page, auxiliary |
| `uri` | text | localização do objeto |
| `sha256` | char(64) | integridade |
| `content_type` | varchar | MIME |
| `compression` | varchar | gzip/zstd/none |
| `size_bytes` | bigint | observabilidade |
| `schema_version` | varchar | contrato do payload |
| `created_at` | timestamptz | imutável |

Unique recomendado: `(run_id, object_type, sha256)`.

#### `outbox_events`

| Campo | Tipo |
| --- | --- |
| `id` | bigint |
| `event_id` | uuid unique |
| `aggregate_type` | varchar |
| `aggregate_id` | varchar |
| `event_type` | varchar |
| `schema_version` | varchar |
| `payload` | jsonb |
| `occurred_at` | timestamptz |
| `published_at` | timestamptz nullable |
| `attempt_count` | integer |
| `last_error` | text nullable |

Índice parcial em `published_at IS NULL`.

### 6.3 Produto original

#### `source_product_versions`

Além dos campos já definidos no modelo v2, deve conter:

- `identity_fingerprint bytea`;
- `raw_payload_hash bytea`;
- `identity_schema_version varchar`;
- `valid_from timestamptz`;
- `valid_until timestamptz null`;
- `first_seen_run_id bigint`;
- `supersedes_version_id bigint null`;
- `reused_external_id_suspected boolean`;
- `quality_flags jsonb`.

Invariantes:

- uma versão aberta por `source_product_id`;
- `(source_product_id, version)` único;
- `(source_product_id, identity_fingerprint)` pode ser único se a política não
  precisar registrar retorno histórico ao mesmo conteúdo;
- versões antigas não recebem alteração de conteúdo.

### 6.4 Execuções LLM

#### `llm_inference_runs`

Representa uma chamada ao fornecedor, inclusive chamadas que falham.

| Campo | Descrição |
| --- | --- |
| `id/public_id` | identidade |
| `request_hash` | idempotência/cache |
| `provider` | fornecedor |
| `model` | nome do modelo |
| `model_revision` | revisão quando disponível |
| `prompt_version_id` | FK |
| `policy_version_id` | FK |
| `output_schema_version` | schema exigido |
| `inference_mode` | primary, verify, proposal_dedupe, shadow |
| `status` | queued/running/succeeded/invalid/failed |
| `batch_size` | itens enviados |
| `input_uri` | request integral fora do banco, se grande |
| `raw_response_uri` | resposta integral |
| `parsed_response` | JSONB validado, quando pequeno |
| `input_tokens/output_tokens` | consumo |
| `estimated_cost` | custo calculado |
| `latency_ms` | tempo total |
| `attempt_count` | tentativas |
| `error_class/error_message` | falha sanitizada |
| `created_at/started_at/finished_at` | auditoria |

`request_hash` é único para inferências concluídas reutilizáveis. Falhas podem
ter múltiplas tentativas ligadas ao mesmo pedido lógico.

#### `llm_inference_items`

Uma chamada em lote contém vários itens:

- `inference_run_id`;
- `source_product_version_id`;
- `sequence`;
- `candidate_set_id`;
- `status`;
- `raw_item_output jsonb`;
- `schema_errors jsonb`;
- `missing_from_response boolean`;
- `retry_of_item_id`.

Unique `(inference_run_id, source_product_version_id)`.

### 6.5 Interpretação normalizada

#### `product_interpretations`

Cada linha representa a leitura estruturada de uma versão da fonte.

Campos obrigatórios:

- `source_product_version_id`;
- `inference_item_id`;
- `interpretation_version`;
- `department_code`;
- `family_code`;
- `product_type`;
- `canonical_display_suggestion`;
- `brand_raw` e `brand_normalized`;
- `manufacturer_normalized`;
- `variant`;
- `flavor`;
- `species`;
- `cut`;
- `variety`;
- `presentation`;
- `conservation`;
- `bone_state`;
- `seasoning_state`;
- `package_type`;
- `package_count`;
- `net_quantity`;
- `unit`;
- `total_quantity_base`;
- `sale_mode`;
- `attributes jsonb`;
- `field_confidences jsonb`;
- `evidence jsonb`;
- `abbreviations_expanded jsonb`;
- `ambiguities jsonb`;
- `quality_flags jsonb`;
- `interpretation_fingerprint`;
- `created_at`.

Interpretações são imutáveis. `current_product_interpretations` seleciona a
interpretação vigente para cada versão da fonte.

### 6.6 Políticas e prompts

#### `classification_policies`

Identifica a política lógica: `beverages.beer`, `produce.apple`,
`cleaning.laundry_detergent`.

#### `classification_policy_versions`

- `policy_id`;
- `version`;
- `status`: draft, evaluating, active, retired;
- `identity_level`: concept, variant, trade_item;
- `required_fields jsonb`;
- `optional_fields jsonb`;
- `ignored_fields jsonb`;
- `critical_match_fields jsonb`;
- `comparison_rules jsonb`;
- `unit_rules jsonb`;
- `synonyms jsonb`;
- `abbreviations jsonb`;
- `positive_examples jsonb`;
- `negative_examples jsonb`;
- `auto_resolution_thresholds jsonb`;
- `second_pass_rules jsonb`;
- `created_by`, `created_at`, `activated_at`.

Somente uma versão ativa por política.

#### `prompt_versions`

- template de sistema;
- template de item;
- versão do schema;
- hash do conteúdo compilado;
- status;
- autoria;
- changelog;
- resultados da avaliação que autorizou ativação.

### 6.7 Candidatos

#### `candidate_sets`

- `source_product_version_id`;
- `interpretation_id nullable`;
- `retrieval_version`;
- `catalog_revision`;
- `candidate_set_hash`;
- `created_at`.

#### `match_candidates`

- `candidate_set_id`;
- `entity_level`;
- `concept_id`;
- `variant_id`;
- `trade_item_id`;
- `rank`;
- `retrieval_methods jsonb`;
- `alias_score`;
- `text_score`;
- `embedding_score`;
- `attribute_score`;
- `final_retrieval_score`;
- `evidence jsonb`.

Unique `(candidate_set_id, entity_level, canonical_entity_id)`.

### 6.8 Catálogo canônico

#### `product_concepts`

Exemplos: `Arroz`, `Cerveja`, `Maçã`, `Picanha`.

Campos adicionais recomendados:

- `status`: provisional, active, merged, retired;
- `policy_id`;
- `preferred_name`;
- `search_document`;
- `merged_into_id`;
- `created_method`;
- `created_by`.

#### `product_variants`

Exemplos: `Maçã Fuji`, `Cerveja Pilsen`, `Picanha Suína`.

Deve guardar atributos que definem comparabilidade conforme a política. Seu
`identity_hash` é calculado de uma representação canônica desses atributos.

#### `trade_items`

Exemplos: `Cerveja Heineken Lata 350 ml`.

Campos essenciais:

- `variant_id`;
- `preferred_name`;
- `brand_id` ou marca normalizada;
- `manufacturer_id nullable`;
- `net_quantity`;
- `unit`;
- `package_count`;
- `package_type`;
- `attributes`;
- `identity_hash`;
- `status`;
- `merged_into_id`.

#### `trade_item_identifiers`

GTIN é evidência, não requisito. Cada identificador possui:

- `scheme`;
- `value`;
- `validation_status`;
- `check_digit_valid`;
- `conflict_status`;
- `source`;
- `verified_at`.

### 6.9 Aliases

#### `canonical_aliases`

- `alias_normalized`;
- `alias_fingerprint`;
- `source_id nullable`;
- `department_code`;
- `family_code`;
- `entity_level`;
- entidade canônica alvo;
- `occurrence_count`;
- `source_count`;
- `resolution_method`;
- `confidence`;
- `locked`;
- `first_seen_at/last_seen_at`;
- `created_from_resolution_id`.

Aliases globais exigem maior confiança. Um alias ambíguo pode ser limitado à
fonte ou família.

### 6.10 Resoluções e propostas

#### `product_resolutions`

- `source_product_version_id`;
- `interpretation_id`;
- `concept_id` obrigatório;
- `variant_id nullable`;
- `trade_item_id nullable`;
- `resolution_level`;
- `relation_type`;
- `method`;
- `model_assessment_id nullable`;
- `final_confidence`;
- `confidence_components jsonb`;
- `evidence jsonb`;
- `status`: proposed, auto_approved, human_approved, rejected, superseded;
- `normalizer_version`;
- `resolver_version`;
- `policy_version_id`;
- `approved_by`;
- `approved_at`;
- `supersedes_resolution_id`;
- `decision_hash`;
- `created_at`.

`current_product_resolutions` aponta para uma resolução vigente. A troca do
ponteiro e a criação da nova resolução ocorrem na mesma transação.

#### `canonical_proposals`

- nível proposto;
- interpretação originadora;
- parent concept/variant;
- nome e atributos propostos;
- `proposal_identity_hash`;
- candidatos semelhantes encontrados;
- avaliação primária;
- avaliação de deduplicação;
- status;
- contagem de produtos/fontes que reforçam a proposta;
- decisão humana.

Uma proposta não cria diretamente uma entidade ativa.

### 6.11 Revisão

#### `review_cases`

- `case_type`;
- `source_product_version_id`;
- `interpretation_id`;
- `candidate_set_id`;
- `proposed_resolution_id`;
- `status`;
- `priority`;
- `impact_score`;
- `reason_codes jsonb`;
- `assigned_to`;
- `opened_at`, `due_at`, `resolved_at`;
- `resolution_action`;
- `reviewer_notes`.

#### `review_decisions`

Append-only, contendo ação, valores anteriores, valores escolhidos, autoria e
justificativa.

---

## 7. Pipeline LLM-first

### 7.1 Disparo

O evento `source-product-version.created` cria um job de enriquecimento se não
existir interpretação compatível com o pipeline ativo.

Estado inicial:

```text
NEW → ENRICHMENT_QUEUED
```

Preço pode ficar disponível na busca bruta antes da resolução, mas não entra em
comparações canônicas automáticas.

### 7.2 Atalho por cache e resolução bloqueada

Antes de chamar a LLM:

1. procurar `interpretation_cache_key` concluída;
2. procurar resolução atual aprovada compatível com a interpretação;
3. procurar alias exato bloqueado compatível com fonte e política;
4. procurar resolução humana bloqueada para conteúdo equivalente;
5. validar se campos críticos do conteúdo continuam compatíveis;
6. se a interpretação puder ser reutilizada, gerar candidatos apenas quando a
   resolução ainda estiver pendente ou uma campanha explícita exigir revisão;
7. depois de gerar candidatos, procurar `resolution_request_hash` concluído.

Um alias nunca pode resolver se quantidade, unidade ou marca explícitas
contradisserem o alvo.

### 7.3 Recuperação inicial de candidatos

Como a interpretação ainda não existe, a primeira recuperação usa:

- texto bruto completo;
- categorias da fonte;
- números e unidades reconhecidos por parser simples;
- aliases exatos e aproximados;
- busca trigram;
- full-text search;
- embeddings do texto bruto;
- histórico de produtos do mesmo source/external namespace.

O objetivo é recall, não decisão. O candidato correto deve aparecer no top K.

Valores iniciais para experimento:

- `K=10` para item comercial;
- `K=8` para variante;
- `K=5` para conceito;
- máximo total de 20 entidades no prompt.

### 7.4 Chamada primária

A chamada primária recebe:

- conteúdo bruto delimitado como dado não confiável;
- contexto da fonte e categorias;
- política compilada provável;
- candidatos com IDs opacos e atributos;
- schema JSON obrigatório;
- instrução de não inventar IDs;
- ações permitidas.

A chamada deve realizar conjuntamente:

1. roteamento de departamento/família;
2. extração de atributos;
3. expansão de abreviações;
4. avaliação dos candidatos;
5. escolha da ação recomendada.

### 7.5 Schema de resposta primária

```json
{
  "source_product_version_id": 123,
  "classification": {
    "department_code": "beverages",
    "family_code": "beer",
    "product_type": "Cerveja Pilsen"
  },
  "identity": {
    "brand": "Heineken",
    "manufacturer": null,
    "variant": null,
    "flavor": null,
    "species": null,
    "cut": null,
    "variety": null,
    "presentation": null,
    "conservation": null,
    "package_type": "lata",
    "package_count": 1,
    "net_quantity": "350",
    "unit": "ml",
    "sale_mode": "package",
    "attributes": {}
  },
  "canonical_display_suggestion": "Cerveja Heineken Lata 350 ml",
  "abbreviations_expanded": [
    {"token": "CERV", "meaning": "cerveja"},
    {"token": "LT", "meaning": "lata"}
  ],
  "candidate_assessments": [
    {
      "candidate_id": "trade-item:817",
      "decision": "compatible",
      "confidence": "0.98",
      "matching_fields": ["family", "brand", "quantity", "unit", "package_type"],
      "conflicting_fields": []
    }
  ],
  "recommended_action": "MATCH_EXACT",
  "selected_candidate_id": "trade-item:817",
  "confidence": "0.98",
  "evidence": {
    "brand": ["HEINEKEN"],
    "quantity": ["350ML"],
    "package_type": ["LT"]
  },
  "ambiguities": [],
  "quality_flags": []
}
```

### 7.6 Ações permitidas

- `MATCH_EXACT`: corresponde a item comercial existente;
- `MATCH_VARIANT`: corresponde somente à variante;
- `MATCH_CONCEPT`: corresponde somente ao conceito;
- `CREATE_PROPOSAL`: não existe candidato suficiente;
- `NEEDS_REVIEW`: ambiguidade relevante;
- `INVALID_PRODUCT`: não é produto comercializável ou registro é inválido;
- `INSUFFICIENT_INFORMATION`: faltam atributos mínimos.

A LLM não pode retornar `CREATE_CANONICAL`, nem IDs fora da lista de candidatos.

### 7.7 Validação do schema

Após a resposta:

- validar JSON estritamente;
- rejeitar campos desconhecidos se o schema estiver em modo estrito;
- exigir todos os IDs do lote;
- exigir candidato selecionado para ações `MATCH_*`;
- impedir `trade_item` quando a política encerra em variante;
- validar enums;
- validar números decimais e unidades;
- validar que evidências são substrings do input quando declaradas como textuais;
- normalizar apenas a representação, não o significado.

Itens inválidos são reenviados isoladamente com erro de schema explícito. Um
item ausente na resposta não pode ser convertido automaticamente em rejeição.

### 7.8 Validações objetivas pós-LLM

As validações não tentam compreender todo o nome; elas detectam contradições:

- número/unidade explícitos incompatíveis com o candidato;
- pack múltiplo associado a unidade simples;
- marca explícita diferente;
- embalagem explicitamente diferente;
- família incompatível com categorias fortes da fonte;
- GTIN válido ligado a outro item ativo incompatível;
- preço ou medida implausível para a unidade proposta;
- entidade canônica inativa, fundida ou de política diferente;
- evidência declarada inexistente;
- candidato não enviado no prompt;
- nível de resolução não permitido pela política.

Cada falha gera `reason_code`, nunca somente texto livre.

### 7.9 Recuperação refinada

Depois da extração estruturada, o sistema repete a busca de candidatos usando os
atributos interpretados. Se surgir candidato materialmente melhor que não estava
na chamada primária, a decisão não é aprovada imediatamente. Uma verificação
direcionada compara os candidatos antigos e novos.

### 7.10 Segunda avaliação

Obrigatória inicialmente quando:

- ação é `CREATE_PROPOSAL`;
- dois candidatos têm pontuação próxima;
- qualquer atributo crítico está ausente;
- validação objetiva encontrou conflito;
- confiança está na faixa intermediária;
- item é de família de alto risco;
- decisão une grupos anteriormente separados;
- decisão altera uma resolução atual;
- produto tem alto impacto em buscas/listas/promoções.

A chamada de verificação deve ser independente da justificativa anterior sempre
que possível e receber uma pergunta menor: escolher entre candidatos, confirmar
proposta ou identificar insuficiência.

### 7.11 Confiança final

`final_confidence` não é cópia da confiança declarada pela LLM. É calculada por
versão do resolvedor a partir de:

- confiança da chamada primária calibrada;
- concordância da segunda avaliação;
- margem entre candidatos;
- compatibilidade dos campos críticos;
- força de alias;
- presença de identificador validado;
- suporte cross-source;
- quantidade de atributos ausentes;
- flags de qualidade;
- histórico de precisão do modelo naquela família.

Pesos e limiares são definidos em política e medidos sobre dataset dourado.

Limiar inicial apenas para experimento:

- `>= 0,985`: candidato a autoaprovação exata;
- `0,93–0,985`: segunda avaliação ou revisão;
- `< 0,93`: revisão/proposta/insuficiente;
- proposta de novo canônico nunca é ativada apenas pela primeira avaliação.

Esses valores não são contrato permanente.

---

## 8. Catálogo canônico progressivo

### 8.1 Criação progressiva

O catálogo não será preenchido integralmente antes do uso. Ele cresce quando:

- produto não encontra candidato adequado;
- interpretação possui atributos mínimos da política;
- verificação confirma que não há entidade equivalente;
- revisão ou regra de ativação aprova a proposta.

### 8.2 Estados da entidade

- `PROVISIONAL`: proposta utilizável apenas internamente;
- `ACTIVE`: liberada para resolução e leitura;
- `MERGED`: redireciona para outra entidade;
- `RETIRED`: preservada para histórico, não aceita novas resoluções;
- `BLOCKED`: entidade com problema de qualidade.

### 8.3 Ativação de proposta

Uma proposta pode ser ativada por:

- aprovação humana;
- duas avaliações independentes concordantes mais validações objetivas, quando
  a política permitir;
- múltiplos produtos/fontes independentes que reforcem a mesma identidade, após
  deduplicação;
- importação inicial curada.

### 8.4 Merge

Merge não altera resoluções históricas. Operação:

1. criar evento de merge;
2. marcar origem como `MERGED`;
3. preencher `merged_into_id`;
4. criar novas resoluções correntes quando necessário;
5. atualizar aliases;
6. reprocessar projeções afetadas;
7. registrar casos de avaliação para impedir recriação da duplicata.

### 8.5 Split

Split exige revisão explícita. O sistema cria novas entidades, seleciona quais
resoluções migram e preserva a trilha anterior. Nenhuma heurística deve dividir
automaticamente um canônico ativo de alto impacto sem shadow evaluation.

---

## 9. Políticas por domínio

### 9.1 Campos comuns

Toda política declara:

- nível máximo de resolução;
- campos que definem identidade;
- campos que definem comparabilidade;
- campos decorativos;
- atributos obrigatórios para autoaprovação;
- tolerâncias numéricas;
- unidades e conversões permitidas;
- critérios de segunda avaliação;
- regras de nome canônico;
- exemplos positivos e negativos.

### 9.2 Produtos embalados

Identidade típica:

```text
família + marca + variante/sabor + quantidade total + embalagem + pack count
```

Regras:

- 350 ml e 600 ml não são item exato;
- unidade e pack não são item exato;
- refil e embalagem principal não são item exato;
- mesma quantidade em embalagem diferente pode ser variante comparável, não
  item exato;
- marca própria deve permanecer distinta;
- ausência de marca onde marca é relevante impede autoaprovação de item exato.

### 9.3 Açougue e carnes

Identidade comparável típica:

```text
espécie + corte + apresentação relevante + conservação + osso + tempero
```

Marca frequentemente não define identidade. Venda por kg, peça e bandeja precisa
ser preservada. Peso aproximado de peça não deve virar identidade rígida.

### 9.4 Hortifrúti

Identidade comparável típica:

```text
produto + variedade + orgânico/convencional + apresentação + modo de venda
```

Calibre, origem e classificação comercial entram quando disponíveis e quando a
política demonstrar impacto. Bandeja, pacote, unidade e kg não devem ser
misturados sem conversão confiável.

### 9.5 Higiene e limpeza

Identidade típica:

```text
família + marca + linha/finalidade + variante/fragrância + volume + pack/refil
```

Fragrância pode ser ignorada na busca genérica, mas normalmente diferencia item
comercial exato.

### 9.6 Bazar e itens sem unidade padronizada

Autoaprovação exige descrição suficiente. Dimensões, material, capacidade,
voltagem e quantidade podem ser campos críticos. Produtos insuficientes seguem
para variante/conceito ou revisão, sem criar itens exatos excessivamente
genéricos.

---

## 10. Estados e máquina de processamento

### 10.1 Estado de enriquecimento

```text
NEW
  → ENRICHMENT_QUEUED
  → ENRICHING
  → INTERPRETED
  → CANDIDATES_REFINED
  → RESOLUTION_PENDING
      ├── AUTO_RESOLVED
      ├── VERIFYING → AUTO_RESOLVED
      ├── PROPOSAL_PENDING
      ├── NEEDS_REVIEW
      ├── INSUFFICIENT_INFORMATION
      └── INVALID_PRODUCT
```

Estados de erro:

- `RETRYABLE_ERROR`;
- `SCHEMA_ERROR`;
- `PROVIDER_ERROR`;
- `PERMANENT_ERROR`;
- `POLICY_MISSING`.

### 10.2 Regra de visibilidade

Produtos nunca desaparecem por ausência de resolução. A busca pode mostrar:

- canônico confirmado;
- interpretação provisória;
- produto bruto aguardando análise.

Somente comparações exatas e promoção automática exigem resolução aprovada no
nível exigido pela política.

### 10.3 Reprocessamento

Campanhas são registradas com:

- versão alvo;
- filtros por fonte/família/status/confiança;
- quantidade prevista;
- orçamento;
- modo `shadow` ou `activate`;
- progresso e erros;
- taxa de divergência;
- aprovação para promoção da versão.

---

## 11. Idempotência, concorrência e filas

### 11.1 Filas lógicas

- `collection.default`;
- `collection.authenticated`;
- `enrichment.primary`;
- `enrichment.verify`;
- `resolution.proposals`;
- `projection.refresh`;
- `maintenance.reprocess`;
- `dead-letter`.

Podem compartilhar o mesmo broker inicialmente, mas precisam de métricas e
limites independentes.

### 11.2 Chaves de idempotência

- coleta: `(target_id, ingestion_key)`;
- versão: `(source_product_id, identity_fingerprint)`;
- interpretação: `interpretation_cache_key`;
- avaliação de resolução: `resolution_request_hash`;
- candidato: `(source_product_version_id, retrieval_version, catalog_revision)`;
- resolução: `decision_hash`;
- projeção: `(projection_name, aggregate_id, source_revision)`.

### 11.3 Locks

- no máximo uma coleta ativa por target, salvo política explícita;
- no máximo um enriquecimento primário por versão/pipeline;
- lock curto para publicação da resolução corrente;
- nenhuma chamada externa deve manter transação do banco aberta;
- leases expiram e jobs precisam tolerar retomada.

### 11.4 Retry

Retry com jitter exponencial para:

- timeout;
- HTTP 429;
- 5xx;
- indisponibilidade temporária do broker/DB;
- JSON truncado recuperável.

Não repetir indefinidamente:

- erro de schema após limite configurado;
- política ausente;
- conteúdo inválido;
- prompt maior que limite sem possibilidade de redução;
- autenticação inválida até renovação de segredo.

### 11.5 Drenagem de backlog

O sistema não depende de uma única rodada de tamanho fixo. Enquanto houver itens
e orçamento:

1. worker reserva lote;
2. processa;
3. persiste resultados;
4. publica próximos eventos;
5. repete até fila vazia ou limite operacional.

Backlog deve ter idade máxima monitorada, não apenas quantidade.

---

## 12. Prompts e proteção da inferência

### 12.1 Estrutura do prompt

1. sistema fixo e versionado;
2. contrato JSON;
3. política compilada da família;
4. ações permitidas;
5. candidatos fornecidos pelo sistema;
6. exemplos recuperados e limitados;
7. conteúdo bruto delimitado.

### 12.2 Conteúdo da fonte é não confiável

Nomes, descrições e categorias podem conter texto que pareça instrução. O
prompt deve declarar que todo conteúdo entre delimitadores é dado, nunca ordem.
O modelo não pode alterar schema, ação ou candidatos por instrução presente no
produto.

### 12.3 Saída

Preferência por JSON Schema/tool calling quando o provedor oferecer. Caso
contrário:

- temperatura baixa;
- resposta exclusivamente JSON;
- parser estrito;
- correção de formato no máximo configurado;
- nenhum regex permissivo que aceite texto parcial como decisão final.

### 12.4 Exemplos

Exemplos são recuperados por família e semelhança. Cada exemplo aprovado possui:

- input bruto;
- interpretação esperada;
- candidato esperado;
- ação esperada;
- fonte da decisão;
- tags de dificuldade.

Limitar exemplos para não dominar o contexto nem induzir a copiar marca/tamanho
de outro produto.

---

## 13. Painel administrativo

### 13.1 Dashboard operacional

Mostrar:

- backlog por fonte, família e estado;
- idade do item mais antigo;
- throughput por minuto;
- custo por mil produtos;
- taxa de cache hit;
- chamadas primárias e verificações;
- falhas de schema;
- taxa de autoaprovação;
- taxa de revisão;
- divergência de shadow runs;
- fontes com queda de qualidade.

### 13.2 Fila de revisão

Filtros:

- motivo;
- impacto;
- departamento/família;
- fonte;
- confiança;
- proposta nova;
- conflito de quantidade/marca/embalagem;
- usado em lista;
- potencial promoção.

Tela de caso:

- dados brutos e imagem;
- interpretação da LLM;
- evidências destacadas;
- candidatos lado a lado;
- preços/listagens associadas;
- histórico de decisões;
- prompt/modelo/política;
- validações que falharam.

Ações:

- aceitar candidato;
- escolher outro candidato;
- limitar resolução ao conceito/variante;
- editar interpretação;
- criar proposta;
- ativar proposta;
- unir entidades;
- separar entidade;
- marcar produto inválido;
- bloquear resolução;
- transformar decisão em exemplo de avaliação;
- abrir incidente de política.

### 13.3 Editor de políticas

Alterações criam draft. Para ativar:

1. salvar nova versão;
2. executar conjunto dourado;
3. comparar com versão ativa;
4. revisar regressões;
5. aprovar;
6. ativar atomicamente;
7. opcionalmente iniciar campanha shadow/backfill.

Não haverá edição destrutiva da política ativa.

### 13.4 Catálogo canônico

Busca e edição de conceito, variante e item, mostrando:

- aliases;
- produtos resolvidos;
- fontes e lojas;
- atributos;
- entidades semelhantes;
- histórico de merge/split;
- volume e impacto;
- qualidade das resoluções.

---

## 14. Projeções de leitura

### 14.1 Princípio

Rotas de usuário não devem consultar todas as versões, inferências e resoluções.
Eventos atualizam projeções incrementais.

### 14.2 `canonical_product_search`

Documento de busca por entidade, contendo:

- IDs canônicos;
- nome preferido;
- aliases relevantes;
- departamento/família;
- marca e atributos resumidos;
- status;
- quantidade de fontes;
- menor preço atual;
- freshness;
- imagem preferida;
- vetor/tsvector quando aplicável.

### 14.3 `current_offer_matrix`

Uma linha por entidade comparável, store listing e condição selecionável:

- entidade canônica e nível;
- produto/listagem da fonte;
- loja;
- preço final comum;
- preço condicionado separado;
- unidade base;
- preço unitário normalizado;
- validade;
- disponibilidade;
- última confirmação;
- confiança da resolução;
- versão de projeção.

### 14.4 Atualização

Disparada por:

- abertura/fechamento de período de preço;
- troca de resolução corrente;
- merge/split;
- ativação de entidade;
- alteração de política de comparação;
- mudança de disponibilidade/freshness.

### 14.5 Busca e lista

Autocomplete:

```http
GET /api/v2/products/search?q=heineken&department=beverages&limit=20
```

Itens da lista guardam `concept_id`, `variant_id` ou `trade_item_id` conforme o
nível escolhido, além de preferências. A página carrega somente a lista e suas
ofertas atuais; não recebe o catálogo inteiro.

---

## 15. APIs propostas

### 15.1 Operação

- `POST /api/v2/collection-runs`;
- `GET /api/v2/collection-runs/{id}`;
- `GET /api/v2/operations/backlog`;
- `POST /api/v2/reprocessing-campaigns`;
- `GET /api/v2/reprocessing-campaigns/{id}`.

### 15.2 Produto e resolução

- `GET /api/v2/source-products/{id}`;
- `GET /api/v2/source-product-versions/{id}/interpretations`;
- `GET /api/v2/source-product-versions/{id}/candidates`;
- `GET /api/v2/source-product-versions/{id}/resolutions`;
- `POST /api/v2/source-product-versions/{id}/reprocess`;
- `POST /api/v2/review-cases/{id}/decisions`.

### 15.3 Canônico

- `GET /api/v2/canonical/concepts`;
- `GET /api/v2/canonical/variants`;
- `GET /api/v2/canonical/trade-items`;
- `POST /api/v2/canonical/proposals/{id}/approve`;
- `POST /api/v2/canonical/entities/{id}/merge`;
- `POST /api/v2/canonical/entities/{id}/split`.

### 15.4 Políticas e avaliações

- `GET /api/v2/policies`;
- `POST /api/v2/policies/{id}/versions`;
- `POST /api/v2/policy-versions/{id}/evaluate`;
- `POST /api/v2/policy-versions/{id}/activate`;
- `GET /api/v2/evaluation-runs/{id}`.

### 15.5 Regras HTTP

- escrita administrativa exige autenticação e papel;
- `Idempotency-Key` em comandos reexecutáveis;
- ETag/revision em alterações concorrentes;
- paginação por cursor;
- erros com códigos estáveis;
- nenhuma resposta expõe credenciais ou prompts com dados secretos;
- auditoria inclui actor, request ID e motivo.

---

## 16. Observabilidade

### 16.1 Métricas de coleta

- runs por status/fonte/target;
- duração;
- páginas esperadas/processadas;
- itens observados/novos/alterados;
- queda percentual contra baseline;
- HTTP status e retry;
- idade da última coleta completa;
- bytes brutos armazenados.

### 16.2 Métricas LLM

- produtos processados;
- cache hit/miss;
- itens por lote;
- tokens e custo;
- latência;
- falhas por tipo;
- schema invalid rate;
- missing item rate;
- retry rate;
- segunda avaliação;
- resultado por família;
- custo por produto resolvido.

### 16.3 Métricas de resolução

- autoaprovação;
- revisão;
- insuficiência;
- propostas novas;
- precisão estimada por faixa de confiança;
- taxa de override humano;
- falsos merges;
- fragmentação canônica;
- candidate recall@K;
- tempo até resolução;
- backlog e idade.

### 16.4 Logs

Campos mínimos:

- trace/request/job ID;
- run/source/target;
- source product/version;
- inference run/item;
- policy/prompt/model;
- resolution/review case;
- status anterior e novo;
- duração;
- reason codes.

Dados brutos sensíveis e credenciais não entram em logs. Requests e responses
integrais da LLM ficam em storage com controle de acesso e retenção.

### 16.5 Alertas

- backlog acima do SLA;
- nenhuma coleta completa dentro da janela;
- custo por produto acima do limite;
- aumento de falha de schema;
- queda de candidate recall estimado;
- aumento de review rate;
- fonte produzindo volume anormal;
- projeção atrasada;
- divergência alta após nova política/modelo.

---

## 17. Segurança e governança

- segredos ficam fora do banco de configuração público;
- proxy/egress somente autorizado e auditado;
- rate limit respeitado por domínio/fonte;
- raw text é tratado como input não confiável contra prompt injection;
- painel administrativo exige autenticação;
- merge, split, ativação de política e desbloqueio exigem permissão elevada;
- toda decisão humana é auditada;
- artefatos LLM têm retenção e acesso definidos;
- dados pessoais incidentais devem ser removidos ou protegidos;
- exportações para avaliação não devem conter tokens, cookies ou URLs assinadas;
- fornecedores LLM e regiões de processamento precisam ser configuráveis.

---

## 18. Estratégia de testes

### 18.1 Pirâmide

1. testes unitários puros;
2. testes de contrato de coletor;
3. testes de persistência e idempotência;
4. testes de integração de filas;
5. testes de schema/prompt com LLM mock;
6. avaliações externas com modelo real;
7. shadow tests sobre dados reais;
8. testes de carga e performance;
9. revisão humana amostral.

### 18.2 Dataset dourado inicial

Criar `tests/fixtures/resolution/v1/` com:

- `source_products.jsonl`;
- `canonical_entities.jsonl`;
- `candidate_sets.jsonl`;
- `expected_interpretations.jsonl`;
- `expected_resolutions.jsonl`;
- `pair_labels.jsonl`;
- `README.md` com metodologia e origem.

Amostra inicial sugerida: 2.000 produtos, estratificados por fonte e família.

Composição mínima:

- 500 grupos cross-source conhecidos;
- 300 pares negativos difíceis;
- 200 descrições abreviadas/siglas;
- 200 embalagens múltiplas;
- 150 casos com marca ausente;
- 150 casos com tamanho ausente ou ambíguo;
- 150 carnes/hortifrúti;
- 100 refis versus embalagem principal;
- 100 erros reais observados;
- restante distribuído pelas principais famílias.

O mesmo grupo canônico não pode ser dividido entre treino/exemplos e conjunto de
teste final. O teste final deve ficar congelado e oculto do prompt.

### 18.3 Rótulos

Cada produto possui:

- interpretação esperada por campo;
- nível máximo resolvível;
- entidade esperada;
- alternativas aceitáveis;
- ação esperada;
- dificuldade;
- justificativa humana;
- revisores e concordância.

Pares usam:

- `EXACT`;
- `VARIANT_EQUIVALENT`;
- `CONCEPT_RELATED`;
- `SUBSTITUTE`;
- `NOT_COMPARABLE`;
- `INSUFFICIENT_INFORMATION`.

Casos críticos devem ter dupla revisão humana.

### 18.4 Testes unitários obrigatórios

#### Fingerprints

- preço diferente não muda identidade;
- whitespace e Unicode equivalentes não criam versão;
- quantidade diferente muda identidade;
- pack diferente muda identidade;
- ordem hierárquica relevante de categorias é preservada;
- JSON com ordem de chaves diferente produz mesmo hash;
- versão de prompt/política muda request hash;
- candidato novo muda candidate set hash.

#### Estado comercial

- `A → A` não abre período;
- `A → B → A` cria três períodos;
- evento duplicado é idempotente;
- evento atrasado segue política explícita;
- preço condicionado não substitui silenciosamente preço comum;
- coleta parcial não desativa ausentes.

#### Schema LLM

- ID ausente falha o item;
- candidato inventado é rejeitado;
- enum inválido falha;
- decimal inválido falha;
- evidência inexistente gera flag;
- ação e nível incompatíveis falham;
- item omitido não vira rejeição;
- campos extras seguem modo estrito.

#### Validações

- 350 ml não casa exatamente com 600 ml;
- unidade não casa com pack 12;
- refil não casa com frasco;
- marcas explícitas conflitantes bloqueiam autoaprovação;
- maçã Fuji não vira maçã Gala;
- picanha suína não vira picanha bovina;
- preço por kg não vira preço por embalagem.

### 18.5 Testes de candidatos

Medir:

- recall@1;
- recall@5;
- recall@10;
- MRR;
- latência;
- tamanho médio do prompt.

Meta experimental inicial:

- exact candidate recall@10 >= 98%;
- variant candidate recall@10 >= 97%;
- p95 de recuperação < 200 ms em ambiente de referência.

Sem recall adequado, não se deve atribuir falha somente à LLM.

### 18.6 Avaliação da interpretação

Métricas por campo:

- exact match normalizado;
- precision/recall/F1;
- erro absoluto para quantidade;
- taxa de campo inventado;
- taxa de evidência inválida;
- cobertura.

Campos críticos são medidos separadamente: família, marca, quantidade, unidade,
pack, embalagem e variante.

### 18.7 Avaliação da resolução

Métricas principais:

- precisão de autoaprovação exata;
- recall de correspondência exata;
- falsa união;
- fragmentação;
- precisão por faixa de confiança;
- taxa de revisão;
- precisão após segunda avaliação;
- duplicação de propostas canônicas.

Metas para piloto, sujeitas a confirmação:

- precisão de `MATCH_EXACT` autoaprovado >= 99,5%;
- falsa união <= 0,5%;
- precisão de variante autoaprovada >= 98,5%;
- override humano de autoaprovação <= 1%;
- duplicação de proposta <= 3%;
- nenhum caso crítico conhecido regredido;
- cobertura operacional: 100% em algum estado explícito.

Recall pode ser menor no início; é preferível revisar ou fragmentar a unir
produtos incorretamente.

### 18.8 Avaliação de confiança

- reliability diagram por família;
- expected calibration error;
- precisão por decil;
- taxa de revisão por faixa;
- comparação entre confiança do modelo e confiança final.

Limiar de autoaprovação só será ativado onde a amostra possuir tamanho mínimo.

### 18.9 Testes de prompts e políticas

Cada alteração produz relatório com:

- casos corrigidos;
- regressões;
- mudança de custo/tokens;
- mudança de latência;
- mudança de review rate;
- divergências por família;
- exemplos de maior impacto.

Ativação falha se:

- precisão crítica cair;
- qualquer golden case bloqueado regredir;
- schema invalid rate superar limite;
- custo ultrapassar orçamento sem aprovação;
- taxa de proposta duplicada aumentar materialmente.

### 18.10 Testes de integração

- evento duplicado não duplica versão/inferência/resolução;
- crash depois de gravar storage e antes da outbox é recuperável;
- crash depois de publicar e antes de ack é idempotente;
- LLM timeout retorna à fila;
- resposta parcial reenvia apenas itens afetados;
- troca de resolução atual é atômica;
- resolução humana bloqueada não é substituída;
- merge atualiza read models;
- alteração somente de preço não chama LLM;
- versão nova dispara enriquecimento;
- backlog continua sendo drenado após lote.

### 18.11 Testes de carga

Cenários:

- ingestão de 200 mil produtos;
- 50 mil produtos novos simultâneos;
- atualização de preço de 150 mil listagens sem mudança de identidade;
- reprocessamento shadow de 100 mil versões;
- atualização de projeção após merge de alto impacto;
- 100 buscas/s e 20 aberturas de lista/s.

Metas iniciais:

- página da lista p95 < 500 ms;
- autocomplete p95 < 200 ms;
- payload inicial da lista < 100 KB;
- nenhuma consulta do usuário faz scan integral do catálogo;
- worker retoma sem duplicidade após interrupção;
- backlog possui previsão de conclusão e não cresce indefinidamente.

### 18.12 Testes externos

Chamadas reais ao provedor são marcadas `external` e não executam no CI comum.
Devem usar orçamento, dataset congelado e armazenar:

- request hash;
- modelo/revisão;
- resposta bruta;
- parsed response;
- tokens/custo;
- métricas agregadas.

### 18.13 Testes em shadow

Antes de ativar nova versão:

1. manter resolução atual servindo produção;
2. executar pipeline novo;
3. comparar decisões;
4. priorizar divergências por impacto;
5. revisar amostra;
6. aprovar versão;
7. promover ponteiros em lotes reversíveis.

---

## 19. Plano inicial de experimentos

### Experimento E1 — schema e qualidade de extração

Objetivo: validar saída estruturada sem matching.

- selecionar 300 produtos difíceis;
- executar 2 ou 3 variantes de prompt;
- medir campos críticos, omissões e alucinação;
- escolher schema mínimo suficiente;
- resultado esperado: definição do prompt primário v1.

### Experimento E2 — candidate recall

Objetivo: garantir que o candidato correto chega à LLM.

- aliases + trigram;
- aliases + trigram + full text;
- combinação anterior + embeddings;
- medir recall@K e latência;
- resultado esperado: retrieval v1 e K escolhido.

### Experimento E3 — resolução em uma chamada

Objetivo: medir precisão/custo da chamada conjunta.

- 500 casos;
- comparar itens individuais com lotes 10/20/50;
- medir omissão, JSON inválido, precisão e tokens;
- resultado esperado: batch size e limiares preliminares.

### Experimento E4 — segunda avaliação

Objetivo: saber quando a segunda chamada agrega valor.

- aplicar somente a ambiguidades e propostas;
- comparar mesmo modelo/prompt alternativo e, opcionalmente, modelo diferente;
- medir correções e novos erros;
- resultado esperado: regras de verificação v1.

### Experimento E5 — cache e aliases

Objetivo: medir economia incremental.

- reprocessar coletas repetidas;
- alterar apenas preço;
- alterar whitespace;
- alterar quantidade;
- introduzir alias em outra fonte;
- resultado esperado: cache hit e invalidação corretos.

### Experimento E6 — piloto ponta a ponta

Objetivo: validar uma família em múltiplas fontes.

Família sugerida: cervejas ou arroz, por possuir marca, tamanho, embalagem e
variação textual, mas ser revisável.

- pelo menos quatro fontes;
- ingestão, interpretação, candidatos, resolução, revisão e read model;
- busca e lista consumindo somente o read model;
- relatório de custo, precisão, recall, revisão e latência.

### Experimento E7 — domínio não embalado

Objetivo: validar que o mesmo desenho suporta identidade por variante.

- maçãs ou cortes bovinos;
- resolução máxima por política;
- unidades de venda distintas;
- comparação sem falsa precisão de item comercial.

---

## 20. Estrutura inicial de código

```text
app/
  collection/
    contracts.py
    orchestration.py
    outbox.py
    adapters/
      base.py
      vtex.py
      demandware.py
      vipcommerce.py
  identity/
    fingerprints.py
    schemas.py
    states.py
  inference/
    client.py
    batching.py
    cache.py
    prompts.py
    parser.py
  policies/
    compiler.py
    repository.py
    validators.py
  resolution/
    retrieval.py
    scoring.py
    validators.py
    service.py
    proposals.py
    aliases.py
  projections/
    product_search.py
    current_offers.py
  review/
    service.py
    routes.py
  evaluation/
    datasets.py
    runner.py
    metrics.py
scripts/
  build_resolution_dataset.py
  run_resolution_eval.py
  compare_resolution_runs.py
tests/
  identity/
  inference/
  resolution/
  projections/
  integration/
  evaluation/
  fixtures/resolution/v1/
```

As pastas podem ser introduzidas progressivamente. O objetivo é separar
responsabilidades, não reorganizar todo o repositório antes do primeiro teste.

---

## 21. Sequência de implementação

### Fase 0 — avaliação reproduzível

- congelar dataset dourado v1;
- definir schemas Pydantic/JSON Schema;
- implementar runner de avaliação;
- registrar modelo, prompt, tokens e custos;
- estabelecer baseline do pipeline atual e do LLM-first.

Saída: relatório comparável e testes locais reproduzíveis.

### Fase 1 — fingerprints e armazenamento de inferência

- implementar canonical JSON e hashes;
- criar migrações de inferência/interpretação;
- criar cache por request hash;
- mock provider;
- provar que mudança só de preço não chama a LLM.

### Fase 2 — interpretação LLM-first

- prompt/schema primário;
- batching resiliente;
- parser estrito;
- retry por item;
- estados e dashboard de backlog;
- piloto sem resolução automática.

### Fase 3 — retrieval e aliases

- importar canônicos curados do piloto;
- implementar alias exato, trigram e full text;
- avaliar embeddings;
- persistir candidate sets;
- atingir meta de recall@K.

### Fase 4 — resolvedor e revisão

- validações objetivas;
- confiança final;
- segunda avaliação;
- resoluções imutáveis;
- painel de revisão;
- propostas progressivas;
- autoaprovação somente após metas.

### Fase 5 — read models e lista

- `canonical_product_search`;
- `current_offer_matrix`;
- autocomplete paginado;
- lista armazenando IDs canônicos;
- remoção de montagem integral em request;
- metas de performance.

### Fase 6 — expansão por famílias e fontes

- políticas adicionais;
- campanhas shadow;
- backfill incremental;
- métricas por família;
- desligamento da classificação transitória antiga.

### Fase 7 — promoção real e otimização

- baseline histórico;
- comparação cross-market;
- deal score explicável;
- planos de compra em 1, 2 ou N lojas;
- estúdio de conteúdo com revisão humana.

---

## 22. Critérios de aceite para o primeiro piloto

### Funcionais

- produto novo cria versão e job de enriquecimento;
- produto sem mudança de identidade reutiliza interpretação;
- mudança só de preço não chama LLM;
- mudança de tamanho cria nova versão e nova inferência;
- resposta estruturada é validada estritamente;
- candidato inventado não é aceito;
- produto ambíguo entra em revisão;
- proposta nova não vira canônico ativo diretamente;
- correção humana permanece bloqueada;
- busca retorna produto mesmo aguardando resolução;
- comparação exata usa apenas resoluções compatíveis.

### Qualidade

- metas do dataset dourado atendidas;
- nenhuma regressão em casos críticos bloqueados;
- candidate recall@10 dentro da meta;
- precisão de autoaprovação medida com amostra suficiente;
- custo por mil produtos conhecido;
- schema invalid rate abaixo do limite definido no experimento.

### Operacionais

- processamento idempotente;
- backlog observável e drenável;
- dead-letter consultável;
- replay do payload bruto funcional;
- métricas de tokens, custo e latência;
- nenhuma chamada LLM na rota HTTP;
- read model atualizado por evento;
- testes e lint no CI antes de publicar imagem.

### Performance

- autocomplete p95 < 200 ms;
- abertura da lista p95 < 500 ms;
- payload inicial < 100 KB;
- consultas sem full scan do catálogo;
- atualização de preço não dispara recomputação global.

---

## 23. Definition of Done por mudança

Uma mudança de modelo, prompt, política ou resolvedor só está pronta quando:

- possui versão explícita;
- possui migração compatível, quando aplicável;
- inclui testes unitários;
- executa dataset dourado;
- apresenta comparação com a versão ativa;
- registra custo e latência;
- não substitui decisão humana silenciosamente;
- é observável;
- suporta rollback de ponteiro/configuração;
- atualiza documentação e changelog;
- passa CI.

---

## 24. Decisões pendentes para o início dos testes

Estas decisões podem ser fechadas pelos experimentos, sem bloquear a criação do
harness inicial:

1. fornecedor/modelo primário e modelo de verificação;
2. batch size ideal;
3. uso de embeddings desde o piloto ou somente após baseline textual;
4. famílias do piloto embalado e não embalado;
5. limiares de autoaprovação por família;
6. regras para ativação automática de proposta;
7. retenção de requests/responses completos;
8. frequência e orçamento de campanhas shadow;
9. formato de autenticação do painel administrativo;
10. infraestrutura de object storage no ambiente local e produção.

Recomendação inicial:

- piloto embalado com cerveja ou arroz;
- piloto não embalado com maçãs;
- aliases + trigram como baseline;
- embeddings como variante experimental;
- uma chamada primária e segunda apenas em proposta/ambiguidade;
- nenhuma criação canônica automática na primeira iteração;
- nenhuma autoaprovação até medir o primeiro dataset dourado.

---

## 25. Resultado esperado

Ao final das primeiras fases, cada versão de produto terá uma resposta clara e
auditável:

```text
O que a fonte enviou?
Qual conteúdo mudou?
Qual modelo e política interpretaram?
Quais atributos foram extraídos e de onde?
Quais candidatos foram considerados?
Qual decisão foi tomada, com qual confiança?
Houve validação ou revisão humana?
Qual entidade canônica está vigente?
Quais preços e lojas podem ser comparados com segurança?
```

Esse desenho aceita que nomes de mercado sejam inconsistentes e que GTIN seja
escasso. A compreensão semântica fica a cargo da LLM, enquanto o restante do
sistema assegura memória, controle de versão, consistência, revisão, performance
e capacidade de evolução.
