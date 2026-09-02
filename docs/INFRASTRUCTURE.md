# Infraestrutura do Offer Monitoring

Última atualização: 2026-09-01.

Este documento descreve como o projeto está estruturado no desenvolvimento
local e no ambiente Oracle Cloud. Nenhum segredo é registrado aqui.

Documentos relacionados:

- [`PROJECT-CONTEXT.md`](PROJECT-CONTEXT.md): regras de negócio e decisões;
- [`DEPLOY-ORACLE.md`](DEPLOY-ORACLE.md): procedimento e checklist do deploy;
- [`../docker-compose.prod.yml`](../docker-compose.prod.yml): stack principal;
- [`../docker-compose.backup.yml`](../docker-compose.backup.yml): backup diário.

## 1. Visão geral

```text
GitHub namewellz/offer-monitoring
        ↓ push em main
GitHub Actions / Buildx
        ↓
GHCR: linux/amd64 + linux/arm64
        ↓ pull/Watchtower
Oracle Cloud (arm64)
  ├─ Caddy → offer-monitoring-api:8000
  ├─ API
  ├─ Scheduler
  ├─ Worker/RQ
  ├─ PostgreSQL 17
  ├─ Redis 7
  └─ Backup container
```

URL de produção:

```text
https://ofertas.overflowlab.net
```

## 2. Repositório e imagens

| Item | Valor |
|---|---|
| Repositório | `https://github.com/namewellz/offer-monitoring` |
| Branch de produção | `main` |
| Imagem | `ghcr.io/namewellz/offer-monitoring:latest` |
| Tag de rollback do deploy | `sha-b3bbe48c008fb3767ab75d83408c594084e762b2` |
| Digest publicado | `sha256:95fd1db5582abaface8b7e99452a84da1ee3c52a845ea6dea2aa73a89b823cc8` |
| Plataformas | `linux/amd64`, `linux/arm64` |
| Workflow | `.github/workflows/publish-image.yml` |

O servidor usa `latest` para receber atualizações pelo Watchtower. A tag
`sha-<commit>` é imutável e deve ser usada em rollback.

## 3. Ambiente local

### 3.1 Host

```text
Sistema: Windows
Workspace: C:\fonts\offer-monitoring
Runtime: Docker Desktop / Docker Compose
Compose: docker-compose.yml
URL quando ativo: http://localhost:8000
```

O Dockerfile é único para API, scheduler e worker. Cada serviço troca apenas o
comando de entrada.

### 3.2 Containers locais

| Serviço | Função | Exposição |
|---|---|---|
| `postgres` | banco e histórico | somente rede do Compose |
| `redis` | fila e locks | somente rede do Compose |
| `api` | FastAPI e interfaces | `8000:8000` |
| `scheduler` | agenda descoberta e catálogos | sem porta |
| `worker` | executa jobs RQ | sem porta |

Volumes nomeados:

```text
offer-monitoring_postgres_data → /var/lib/postgresql/data
offer-monitoring_flyer_data    → /data
```

No Compose local atual, Redis é efêmero. Isso é aceitável para
desenvolvimento, mas produção usa persistência AOF.

Segredos locais são indicados pelo `.env` e montados como arquivos somente de
leitura. O `.env`, o token Davitta e o bundle Assaí não são versionados nem
incluídos na imagem Docker.

Ollama, quando utilizado no fluxo de encartes, roda no host e é acessado pelo
container através de `host.docker.internal`.

### 3.3 Estado após a virada

Antes do dump final, os jobs estavam ociosos. API, scheduler e worker locais
foram parados para congelar as escritas. Depois da migração, o Docker Desktop
foi encontrado desligado, portanto não há ambiente local coletando em paralelo.

Para voltar a usar o ambiente local sem reativar coletas automáticas, confirme
primeiro no `.env`:

```dotenv
DISCOVERY_ENABLED=false
CATALOG_COLLECTION_ENABLED=false
```

Depois inicie somente o necessário. Não ative scheduler/worker locais enquanto
a Oracle for o ambiente oficial.

## 4. Oracle Cloud

### 4.1 Host e acesso

```text
Atalho SSH no PowerShell: ssh oracle
Usuário operacional: ubuntu
Arquitetura: aarch64 / linux/arm64
Docker: 29.6.1 no momento do deploy
Docker Compose: v5.3.1 no momento do deploy
Raiz da aplicação: /srv/offer-monitoring
```

O host executa outras aplicações. O Offer Monitoring não publica portas
próprias e não altera as redes internas das demais stacks.

### 4.2 Estrutura de diretórios

```text
/srv/offer-monitoring/
├── stack/            clone do repositório e .env.production
├── postgres-data/    PGDATA persistente
├── redis-data/       Redis AOF persistente
├── flyer-data/       montado como /data
├── secrets/          arquivos Davitta e Assaí, modo 600
├── migration/        dump e arquivos usados na migração
└── backups/
    └── automatic/    backups diários com retenção local
```

Uso aproximado logo após o deploy e primeiro ciclo automático:

| Diretório | Uso |
|---|---:|
| `postgres-data` | 2,1 GB |
| `redis-data` | 228 KB |
| `flyer-data` | 162 MB |
| `backups` | 225 MB |
| `migration` | 218 MB |
| `stack` | 99 MB |

Esses valores mudam conforme novas observações são adicionadas.

### 4.3 Stack principal

Projeto Compose: `offer-monitoring`.

| Container | Imagem | Função | Restart |
|---|---|---|---|
| `offer-monitoring-api-1` | GHCR Offer Monitoring | FastAPI, migrations e painel | `unless-stopped` |
| `offer-monitoring-scheduler-1` | GHCR Offer Monitoring | agenda catálogos | `unless-stopped` |
| `offer-monitoring-worker-1` | GHCR Offer Monitoring | worker RQ | `unless-stopped` |
| `offer-monitoring-postgres-1` | `postgres:17-alpine` | banco persistente | `unless-stopped` |
| `offer-monitoring-redis-1` | `redis:7-alpine` | fila persistente/AOF | `unless-stopped` |
| `offer-monitoring-backup-1` | `postgres:17-alpine` | backup recorrente | `unless-stopped` |

O projeto foi criado por Docker Compose e aparece no Portainer como stack
externa. Operações que alterem a definição devem usar os mesmos arquivos e o
mesmo nome de projeto.

Comando-base recomendado:

```bash
cd /srv/offer-monitoring/stack
docker compose \
  -p offer-monitoring \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  -f docker-compose.backup.yml \
  ps
```

Por que `-p offer-monitoring` é obrigatório: sem ele, o Compose usa o nome do
diretório (`stack`) e criaria outro projeto lógico.

### 4.4 Redes

```text
offer-monitoring-internal
  ├─ api
  ├─ scheduler
  ├─ worker
  ├─ postgres
  ├─ redis
  └─ backup

proxy (rede externa compartilhada)
  ├─ caddy
  └─ api, alias offer-monitoring-api
```

Somente a API participa da rede `proxy`. PostgreSQL, Redis, worker, scheduler e
backup ficam apenas na rede interna.

Os textos `5432/tcp` e `6379/tcp` em `docker ps` representam portas declaradas
pelas imagens, não portas publicadas. Não existe `0.0.0.0:<porta>` para esses
serviços.

### 4.5 Caddy e HTTPS

Caddy já existia como container global e usa:

```text
Host file: /opt/stacks/caddy/Caddyfile
Container: caddy
Container path: /etc/caddy/Caddyfile
Rede: proxy
Portas públicas: 80 e 443
```

Bloco adicionado:

```caddyfile
ofertas.overflowlab.net {
    encode zstd gzip
    reverse_proxy offer-monitoring-api:8000
}
```

O reload foi feito depois de validar o arquivo. O certificado Let's Encrypt foi
emitido, HTTP retorna 308 para HTTPS e `/health` retorna 200.

O reload do Caddy é gracioso. Durante o deploy, Auction Monitor e Portainer
continuaram respondendo HTTP 200.

### 4.6 DNS e portas

```text
ofertas.overflowlab.net → IP público da Oracle
80/tcp  → Caddy
443/tcp e 443/udp → Caddy
```

Offer Monitoring não publica 8000, 5432 ou 6379 no host. O acesso externo à API
é exclusivamente via Caddy.

A confirmação de que a porta 22 está restrita ao IP administrativo na Security
List/NSG da Oracle permanece pendente no checklist.

## 5. Configuração e segredos

Arquivo de ambiente de produção:

```text
/srv/offer-monitoring/stack/.env.production
permissão 600
```

Ele contém referências de imagem, banco, scheduler e credenciais. Nunca deve
ser impresso em logs, incluído no Git ou copiado para documentação.

Arquivos secretos:

```text
/srv/offer-monitoring/secrets/davita_dotenv
/srv/offer-monitoring/secrets/meu_assai_bundle.js
```

Ambos têm permissão `600` e são montados somente no worker como read-only:

```text
/run/secrets/davita_dotenv
/run/secrets/meu_assai_bundle.js
```

Somente o worker coleta essas fontes; por isso API e scheduler não recebem os
arquivos.

## 6. Scheduler e fila

Configuração cloud atual:

```dotenv
DISCOVERY_ENABLED=false
CATALOG_COLLECTION_ENABLED=true
CATALOG_COLLECTION_CRON=0 6,14,22 * * *
SCHEDULER_TIMEZONE=America/Sao_Paulo
```

O scheduler apenas enfileira. O worker executa os jobs e consulta as fontes.
Todos usam Redis e a fila `flyers`.

Com um worker, as oito fontes são executadas sequencialmente. No ciclo das
22:00 de 2026-09-01, sete fontes finalizaram com sucesso e o Tenda registrou
403 isoladamente; São Vicente foi executado depois, confirmando que uma falha de
fonte não bloqueia o restante da fila.

## 7. Watchtower

Já havia um único Watchtower global:

```text
Container: auction-monitor-watchtower-1
Imagem: nickfedor/watchtower:1.19.0
WATCHTOWER_LABEL_ENABLE=true
WATCHTOWER_CLEANUP=true
WATCHTOWER_POLL_INTERVAL=300
```

API, scheduler e worker possuem:

```yaml
com.centurylinklabs.watchtower.enable: "true"
```

PostgreSQL, Redis e backup não possuem a label. Assim, uma atualização da
aplicação não troca automaticamente bancos ou ferramentas de backup.

## 8. Persistência

| Dado | Persistência cloud |
|---|---|
| PostgreSQL | bind `/srv/offer-monitoring/postgres-data` |
| Redis AOF | bind `/srv/offer-monitoring/redis-data` |
| JSON, catálogos e encartes | bind `/srv/offer-monitoring/flyer-data` |
| Segredos | bind individual read-only no worker |
| Backups | bind `/srv/offer-monitoring/backups` |

O PostgreSQL e Redis têm healthchecks. API, scheduler e worker dependem desses
checks no Compose.

## 9. Migração realizada

Ponto de corte local:

```text
retailers,8
stores,8
catalog_runs,184
catalog_products,152676
catalog_price_observations,3536850
flyers,4
product_offers,235
```

Procedimento aplicado:

1. confirmar fila local ociosa;
2. parar API, scheduler e worker locais;
3. gerar `pg_dump -Fc` dentro do PostgreSQL;
4. compactar o volume `/data`;
5. calcular SHA-256;
6. transferir por SSH;
7. comparar hashes local/cloud;
8. restaurar em PostgreSQL novo;
9. comparar todas as contagens;
10. restaurar `/data` e testar uma imagem histórica pelo domínio.

Versão Alembic restaurada:

```text
0007_canonical_departments
```

Uma imagem histórica retornou HTTP 200 e `image/png` pela rota
`/pages/{page_id}/image`.

## 10. Backup automático

O container `offer-monitoring-backup-1` executa um backup ao iniciar e depois
dorme 86.400 segundos. Cada execução cria:

```text
/srv/offer-monitoring/backups/automatic/YYYYMMDD-HHMMSS/
├── offer-monitoring.dump
├── flyer-data.tar.gz
└── SHA256SUMS
```

Retenção local: diretórios com mais de 13 dias completos são removidos,
resultando em aproximadamente 14 dias de backups.

O primeiro backup automático foi concluído com aproximadamente 225 MB. Ele não
é uma cópia externa: falha da instância ou do disco pode atingir produção e
backup simultaneamente. Ainda é necessário escolher e configurar um destino
fora da Oracle.

## 11. Saúde e observabilidade

Health interno/externo esperado:

```json
{"application":true,"database":true,"redis":true,"ollama":false}
```

`ollama=false` é esperado porque descoberta visual está desabilitada.

Comandos úteis:

```bash
ssh oracle
cd /srv/offer-monitoring/stack

docker compose -p offer-monitoring \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  -f docker-compose.backup.yml ps

docker logs --tail 200 offer-monitoring-api-1
docker logs --tail 200 offer-monitoring-worker-1
docker logs --tail 200 offer-monitoring-scheduler-1
docker logs --tail 50 offer-monitoring-backup-1

docker exec offer-monitoring-worker-1 \
  rq info --url redis://redis:6379/0

curl -fsS https://ofertas.overflowlab.net/health
```

Interfaces operacionais:

```text
https://ofertas.overflowlab.net/catalog
https://ofertas.overflowlab.net/catalog/updates
```

## 12. Atualização e rollback

Fluxo normal:

1. testar localmente;
2. commit e push em `main`;
3. aguardar o workflow publicar os dois manifests;
4. Watchtower detectar `latest` e recriar API/scheduler/worker;
5. validar `/health`, logs e painel.

Para uma atualização manual controlada:

```bash
cd /srv/offer-monitoring/stack
git pull --ff-only origin main

docker compose -p offer-monitoring \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  -f docker-compose.backup.yml pull api scheduler worker

docker compose -p offer-monitoring \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  -f docker-compose.backup.yml up -d
```

Não use `docker compose down -v`; o projeto usa bind mounts, mas remover volumes
ou diretórios de forma indiscriminada é desnecessário e perigoso.

Rollback de imagem:

1. alterar apenas `APP_IMAGE` em `.env.production` para a tag SHA estável;
2. recriar API, worker e scheduler;
3. validar `/health` e logs;
4. lembrar que rollback de imagem não desfaz migration de banco.

## 13. Convivência com outras aplicações

O host também executa Auction Monitor, Portainer, Caddy, monitoramento,
Audiobookshelf, OLX Monitor, Stirling PDF e Jackett, entre outros.

Regras para não causar indisponibilidade:

- sempre filtrar por projeto ou nome exato de container;
- nunca executar `docker compose down` fora do diretório/arquivos corretos;
- validar o Caddyfile antes de reload;
- fazer reload, não restart, do Caddy;
- não criar um segundo Watchtower global;
- não publicar portas que conflitem com serviços existentes;
- conferir rede e mounts antes de remover containers;
- nunca apagar `/srv` ou diretórios calculados por variável não validada.

## 14. Pendências de infraestrutura

- confirmar a restrição da porta SSH na Security List/NSG;
- configurar cópia dos backups fora da instância;
- testar restauração de um backup produzido pelo container automático;
- proteger painel e endpoints de atualização com autenticação;
- validar o painel em um aparelho celular real;
- definir solução de egress autorizada para o Tenda;
- considerar alerta para job falho e backup atrasado;
- revisar disco/índices à medida que o histórico crescer.
