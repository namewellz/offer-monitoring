# Deploy manual do Offer Monitoring na Oracle Cloud

Este documento descreve o deploy por imagens Docker, seguindo o mesmo modelo do
Auction Monitor: GitHub, GHCR, Portainer, Watchtower e Caddy. Ele também inclui
a migração do PostgreSQL e do diretório `/data`, preservando o histórico local.

> Marque uma tarefa trocando `[ ]` por `[x]`. Em uma GitHub Issue, as caixas
> podem ser clicadas diretamente. Nunca registre senhas, tokens ou chaves neste
> arquivo.

## Variáveis usadas nos exemplos

Defina os valores reais antes de executar os comandos:

```text
GITHUB_OWNER=namewellz
GITHUB_REPOSITORY=offer-monitoring
APP_IMAGE=ghcr.io/namewellz/offer-monitoring:latest
STACK_NAME=offer-monitoring
ORACLE_IP=IP_PUBLICO_DA_ORACLE
ORACLE_USER=ubuntu                  # ou opc no Oracle Linux
SSH_KEY=C:\caminho\oracle.key
APP_DOMAIN=ofertas.seudominio.com
SERVER_ROOT=/srv/offer-monitoring
```

## Arquitetura final

```text
GitHub → GitHub Actions → GHCR (amd64 + arm64)
                              ↓
Oracle Cloud → Portainer → API + Scheduler + Worker
                         → PostgreSQL + Redis
                         → Watchtower
                         → Caddy → HTTPS/domínio
```

Dados persistentes:

```text
/srv/offer-monitoring/postgres-data   banco e histórico
/srv/offer-monitoring/redis-data      estado do Redis
/srv/offer-monitoring/flyer-data      arquivos e catálogos em /data
/srv/offer-monitoring/secrets         arquivos secretos
/srv/offer-monitoring/backups         backups recorrentes
```

## 1. Preparação e segurança do repositório

- [x] Confirmar que o projeto funciona localmente.
- [x] Confirmar que PostgreSQL e Redis estão healthy.
- [x] Confirmar que `.env` está ignorado.
- [x] Confirmar que backups e arquivos secretos não serão enviados ao GitHub.
- [x] Adicionar as exclusões abaixo ao `.gitignore`, se ainda não existirem.

```gitignore
.env
.env.*
!.env.example
!.env.production.example

__pycache__/
.pytest_cache/
.ruff_cache/
*.pyc
*.egg-info/

data/
backup/
backups/
*.dump
*.tar.gz
*.bak

.idea/
.vscode/
```

Antes de cada commit, revisar os arquivos:

```powershell
Set-Location C:\fonts\offer-monitoring
git status
git diff --cached --name-only |
  Select-String -Pattern '\.env$|dotenv|hermes|bundle|dump|tar\.gz|backup'
```

- [x] A busca acima não apresenta nenhum segredo ou backup.
- [x] Nenhum token ou senha está dentro de arquivos versionados.

## 2. Criar e enviar o repositório ao GitHub

No GitHub, criar `namewellz/offer-monitoring` sem README, licença ou `.gitignore`.

Se o diretório ainda não for um repositório Git:

```powershell
Set-Location C:\fonts\offer-monitoring
git init -b main
git add .
git status
git commit -m "Initial production-ready Offer Monitoring"
git remote add origin https://github.com/namewellz/offer-monitoring.git
git push -u origin main
```

- [x] Repositório criado.
- [x] Primeiro commit enviado.
- [x] `.env` não aparece no GitHub.
- [x] Arquivos de Davitta e Assaí não aparecem no GitHub.

## 3. Publicação multi-arquitetura no GHCR

Criar `.github/workflows/publish-image.yml`:

```yaml
name: Publish Docker image

on:
  push:
    branches: [main]
  workflow_dispatch:

concurrency:
  group: publish-production-image
  cancel-in-progress: true

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  publish:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - name: Checkout
        uses: actions/checkout@v6
      - name: Set up QEMU
        uses: docker/setup-qemu-action@v4
      - name: Set up Buildx
        uses: docker/setup-buildx-action@v4
      - name: Log in to GHCR
        uses: docker/login-action@v4
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - name: Build and publish
        uses: docker/build-push-action@v7
        with:
          context: .
          platforms: linux/amd64,linux/arm64
          push: true
          tags: |
            ghcr.io/${{ github.repository }}:latest
            ghcr.io/${{ github.repository }}:sha-${{ github.sha }}
          labels: |
            org.opencontainers.image.source=${{ github.server_url }}/${{ github.repository }}
            org.opencontainers.image.revision=${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

Enviar:

```powershell
git add .github/workflows/publish-image.yml
git commit -m "Publish multi-platform Docker image"
git push
```

- [x] Workflow finalizou verde em **GitHub → Actions**.
- [x] Package apareceu em **GitHub → Packages**.
- [x] Tag `latest` foi publicada.
- [x] Tag `sha-<commit>` foi publicada.
- [x] Manifesto contém `linux/amd64` e `linux/arm64`.

Se possível, tornar somente o package público. Para package privado, cadastrar
um token com `read:packages` no Portainer e autenticar o Docker usado pelo
Watchtower.

## 4. Preparar a Oracle Cloud

Conectar por SSH:

```powershell
ssh -i "C:\caminho\oracle.key" ubuntu@IP_PUBLICO_DA_ORACLE
```

No Oracle Linux, o usuário normalmente é `opc`.

Verificar arquitetura e Docker:

```bash
uname -m
docker version
docker compose version
```

Resultados comuns:

```text
aarch64 = linux/arm64
x86_64  = linux/amd64
```

Criar diretórios:

```bash
sudo mkdir -p /srv/offer-monitoring/{postgres-data,redis-data,flyer-data,secrets,migration,backups}
sudo chown -R "$USER":"$USER" /srv/offer-monitoring
```

Descobrir os IDs dos usuários internos das imagens:

```bash
docker pull postgres:17-alpine
docker pull redis:7-alpine
docker run --rm postgres:17-alpine id postgres
docker run --rm redis:7-alpine id redis
```

Aplicar os UID/GID apresentados, por exemplo:

```bash
sudo chown -R 70:70 /srv/offer-monitoring/postgres-data
# Substituir o valor abaixo pelo UID:GID real do Redis.
sudo chown -R 999:1000 /srv/offer-monitoring/redis-data
```

Criar ou verificar a rede compartilhada com o Caddy:

```bash
docker network inspect proxy || docker network create proxy
```

- [x] Docker e Compose disponíveis.
- [x] Arquitetura identificada.
- [x] Diretórios criados.
- [x] Permissões do PostgreSQL e Redis ajustadas.
- [x] Rede `proxy` existente.

## 5. Firewall e DNS

Na Security List ou NSG da Oracle, liberar:

| Origem | Protocolo | Porta | Finalidade |
|---|---:|---:|---|
| Seu IP `/32` | TCP | 22 | SSH |
| `0.0.0.0/0` | TCP | 80 | HTTP/Caddy |
| `0.0.0.0/0` | TCP | 443 | HTTPS/Caddy |

Não liberar publicamente `8000`, `5432` ou `6379`.

Ubuntu:

```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw status
```

Oracle Linux:

```bash
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
```

No provedor DNS, criar:

```text
Tipo: A
Nome: ofertas
Valor: IP_PUBLICO_DA_ORACLE
```

Não criar `AAAA` sem IPv6 funcional.

- [ ] Porta 22 restrita ao IP administrativo.
- [x] Portas 80 e 443 abertas.
- [x] Portas internas continuam fechadas.
- [x] DNS aponta para a Oracle.

## 6. Segredos dos coletores

Copiar os arquivos usando os caminhos reais do `.env` local:

```powershell
scp -i "C:\caminho\oracle.key" `
  "C:\caminho\davita_dotenv" `
  ubuntu@IP_PUBLICO:/srv/offer-monitoring/secrets/davita_dotenv

scp -i "C:\caminho\oracle.key" `
  "C:\caminho\meu_assai_bundle.js" `
  ubuntu@IP_PUBLICO:/srv/offer-monitoring/secrets/meu_assai_bundle.js
```

No servidor:

```bash
chmod 600 /srv/offer-monitoring/secrets/davita_dotenv
chmod 600 /srv/offer-monitoring/secrets/meu_assai_bundle.js
ls -la /srv/offer-monitoring/secrets
```

- [x] Token Davitta copiado.
- [x] Bundle Assaí copiado.
- [x] Permissões `600` aplicadas.
- [x] Segredos não estão no GitHub.

## 7. Stack de produção no Portainer

Criar `docker-compose.prod.yml` no repositório. A stack deve usar a imagem do
GHCR, bind mounts em `/srv/offer-monitoring`, rede externa `proxy` e não deve
publicar PostgreSQL ou Redis.

Variáveis mínimas a cadastrar no Portainer:

```dotenv
APP_IMAGE=ghcr.io/namewellz/offer-monitoring:latest
POSTGRES_DB=flyer
POSTGRES_USER=flyer
POSTGRES_PASSWORD=GERAR_COM_OPENSSL

DISCOVERY_ENABLED=false
CATALOG_COLLECTION_ENABLED=false
CATALOG_COLLECTION_CRON=0 6,14,22 * * *
SCHEDULER_TIMEZONE=America/Sao_Paulo

ASSAI_USERNAME=SEU_CPF_OU_CNPJ
ASSAI_PASSWORD=SUA_SENHA
LOG_LEVEL=INFO
```

Gerar uma senha segura e compatível com URL:

```bash
openssl rand -hex 32
```

No Portainer:

1. Abrir **Stacks → Add stack**.
2. Nomear `offer-monitoring`.
3. Escolher **Git Repository**.
4. Informar `https://github.com/namewellz/offer-monitoring.git`.
5. Usar a referência `refs/heads/main`.
6. Usar o Compose path `docker-compose.prod.yml`.
7. Cadastrar as variáveis sem colocá-las no Git.
8. Fazer o primeiro deploy com coletas desabilitadas.

- [x] Stack criada.
- [x] Imagem GHCR configurada.
- [x] PostgreSQL healthy.
- [x] Redis healthy.
- [x] API, scheduler e worker criados.
- [x] Coletas automáticas ainda desabilitadas.

## 8. Watchtower

Se o Auction Monitor já possui um Watchtower global com:

```text
WATCHTOWER_LABEL_ENABLE=true
```

reutilize-o. Não execute dois Watchtowers globais no mesmo Docker daemon.

Os serviços `api`, `scheduler` e `worker` devem possuir:

```yaml
labels:
  com.centurylinklabs.watchtower.enable: "true"
```

PostgreSQL e Redis não devem receber essa label.

Verificar o existente:

```bash
docker ps --format 'table {{.Names}}\t{{.Image}}' | grep -i watchtower
docker logs --tail 100 NOME_DO_WATCHTOWER
```

- [x] Apenas um Watchtower global está ativo.
- [x] Somente serviços da aplicação possuem a label.
- [x] `WATCHTOWER_CLEANUP=true` está configurado.
- [x] Pull de imagem GHCR funciona no servidor.

## 9. Backup final do ambiente local

> Faça esta etapa somente quando estiver pronto para a migração. Não execute
> atualização manual durante o backup.

No PowerShell:

```powershell
Set-Location C:\fonts\offer-monitoring
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupDir = Join-Path (Get-Location) "backup\$timestamp"
New-Item -ItemType Directory -Force -Path $backupDir
```

Registrar contagens:

```powershell
docker compose exec -T postgres psql -U flyer -d flyer -c "
SELECT 'retailers' tabela, COUNT(*) total FROM retailers
UNION ALL SELECT 'stores', COUNT(*) FROM stores
UNION ALL SELECT 'catalog_runs', COUNT(*) FROM catalog_runs
UNION ALL SELECT 'catalog_products', COUNT(*) FROM catalog_products
UNION ALL SELECT 'catalog_price_observations', COUNT(*) FROM catalog_price_observations
UNION ALL SELECT 'flyers', COUNT(*) FROM flyers
UNION ALL SELECT 'product_offers', COUNT(*) FROM product_offers;
" | Out-File -Encoding utf8 (Join-Path $backupDir "contagens-locais.txt")
```

Parar as escritas:

```powershell
docker compose stop api scheduler worker
docker compose ps
```

Gerar dump dentro do container e copiá-lo. Esse método evita corrupção de
arquivo binário por redirecionamento do Windows PowerShell:

```powershell
$pgContainer = docker compose ps -q postgres
docker compose exec -T postgres `
  pg_dump -U flyer -d flyer -Fc -f /tmp/offer-monitoring.dump
docker cp "${pgContainer}:/tmp/offer-monitoring.dump" `
  (Join-Path $backupDir "offer-monitoring.dump")
```

Validar:

```powershell
docker compose exec -T postgres pg_restore --list /tmp/offer-monitoring.dump |
  Select-Object -First 30
Get-Item (Join-Path $backupDir "offer-monitoring.dump")
Get-FileHash (Join-Path $backupDir "offer-monitoring.dump") -Algorithm SHA256
```

Descobrir o volume `/data`:

```powershell
$apiContainer = docker compose ps -a -q api
$dataVolume = docker inspect $apiContainer `
  --format '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Name}}{{end}}{{end}}'
$dataVolume
```

Compactar o volume nomeado:

```powershell
$backupAbs = (Resolve-Path $backupDir).Path
docker run --rm `
  --mount "type=volume,src=$dataVolume,dst=/source,readonly" `
  --mount "type=bind,src=$backupAbs,dst=/backup" `
  alpine:3.21 `
  tar -czf /backup/flyer-data.tar.gz -C /source .
```

Validar:

```powershell
Get-Item (Join-Path $backupDir "flyer-data.tar.gz")
Get-FileHash (Join-Path $backupDir "flyer-data.tar.gz") -Algorithm SHA256
```

- [x] API, scheduler e worker foram parados.
- [x] Dump foi gerado em formato customizado.
- [x] `pg_restore --list` conseguiu ler o dump.
- [x] `/data` foi compactado.
- [x] SHA-256 dos dois arquivos foi registrado.
- [x] Contagens locais foram salvas.

## 10. Transferir o backup

```powershell
scp -i "C:\caminho\oracle.key" `
  (Join-Path $backupDir "offer-monitoring.dump") `
  ubuntu@IP_PUBLICO:/srv/offer-monitoring/migration/

scp -i "C:\caminho\oracle.key" `
  (Join-Path $backupDir "flyer-data.tar.gz") `
  ubuntu@IP_PUBLICO:/srv/offer-monitoring/migration/
```

No servidor:

```bash
ls -lh /srv/offer-monitoring/migration
sha256sum /srv/offer-monitoring/migration/offer-monitoring.dump
sha256sum /srv/offer-monitoring/migration/flyer-data.tar.gz
tar -tzf /srv/offer-monitoring/migration/flyer-data.tar.gz | head -50
```

- [x] Arquivos transferidos.
- [x] Hashes local e cloud são idênticos.
- [x] Arquivo `/data` pode ser listado.

## 11. Restaurar o PostgreSQL

No Portainer, parar API, scheduler e worker. Manter PostgreSQL e Redis ativos.

Localizar o PostgreSQL:

```bash
PG_CONTAINER=$(docker ps \
  --filter label=com.docker.compose.project=offer-monitoring \
  --filter ancestor=postgres:17-alpine \
  --format '{{.ID}}' | head -1)
test -n "$PG_CONTAINER"
echo "$PG_CONTAINER"
```

Copiar e validar o dump:

```bash
docker cp /srv/offer-monitoring/migration/offer-monitoring.dump \
  "$PG_CONTAINER:/tmp/offer-monitoring.dump"
docker exec "$PG_CONTAINER" pg_restore --list /tmp/offer-monitoring.dump | head -30
```

Os comandos abaixo assumem usuário e banco `flyer`:

```bash
docker exec "$PG_CONTAINER" psql -U flyer -d postgres -v ON_ERROR_STOP=1 \
  -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='flyer' AND pid<>pg_backend_pid();"

docker exec "$PG_CONTAINER" dropdb --if-exists --force -U flyer flyer
docker exec "$PG_CONTAINER" createdb -U flyer -O flyer flyer

docker exec "$PG_CONTAINER" pg_restore \
  -U flyer -d flyer \
  --no-owner --no-privileges --exit-on-error --verbose \
  /tmp/offer-monitoring.dump
```

Validar migration e contagens:

```bash
docker exec "$PG_CONTAINER" psql -U flyer -d flyer \
  -c "SELECT * FROM alembic_version;"

docker exec "$PG_CONTAINER" psql -U flyer -d flyer -c "
SELECT 'retailers' tabela, COUNT(*) total FROM retailers
UNION ALL SELECT 'stores', COUNT(*) FROM stores
UNION ALL SELECT 'catalog_runs', COUNT(*) FROM catalog_runs
UNION ALL SELECT 'catalog_products', COUNT(*) FROM catalog_products
UNION ALL SELECT 'catalog_price_observations', COUNT(*) FROM catalog_price_observations;
"
```

- [x] Banco cloud recriado.
- [x] Restore terminou sem erro.
- [x] Alembic possui a versão esperada.
- [x] Contagens são iguais às locais.

## 12. Restaurar `/data`

```bash
sudo tar --no-same-owner \
  -xzf /srv/offer-monitoring/migration/flyer-data.tar.gz \
  -C /srv/offer-monitoring/flyer-data
sudo chown -R "$USER":"$USER" /srv/offer-monitoring/flyer-data
du -sh /srv/offer-monitoring/flyer-data
find /srv/offer-monitoring/flyer-data -type f | head -30
```

- [x] Arquivos restaurados.
- [x] Aplicação consegue ler `/data`.
- [x] Imagens históricas carregam.

## 13. Iniciar e validar a aplicação

No Portainer:

1. Iniciar API.
2. Conferir migrations e logs.
3. Iniciar worker.
4. Iniciar scheduler por último.
5. Manter coletas automáticas desabilitadas.

Teste interno:

```bash
API_CONTAINER=$(docker ps \
  --filter label=com.docker.compose.project=offer-monitoring \
  --format '{{.ID}} {{.Names}}' | awk '$2 ~ /api/ {print $1; exit}')

docker exec "$API_CONTAINER" python -c \
  "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health').read().decode())"
```

Esperado, sem Ollama:

```json
{"application":true,"database":true,"redis":true,"ollama":false}
```

`ollama=false` é aceitável quando `DISCOVERY_ENABLED=false`.

- [x] API inicia sem erro.
- [x] Banco e Redis aparecem `true`.
- [x] Histórico aparece no painel.
- [x] Categorias aparecem.
- [x] Tenda e São Vicente aparecem.
- [x] Abas Todos, Em oferta e Variações funcionam.
- [x] Atualização manual está disponível.

## 14. Configurar o Caddy

### Caddy em Docker — recomendado

O Caddy e a API precisam compartilhar a rede `proxy`. A API deve ter o alias
`offer-monitoring-api` nessa rede.

Adicionar ao Caddyfile:

```caddyfile
ofertas.seudominio.com {
    encode zstd gzip
    reverse_proxy offer-monitoring-api:8000
}
```

Validar e recarregar:

```bash
docker exec NOME_DO_CADDY caddy validate --config /etc/caddy/Caddyfile
docker exec NOME_DO_CADDY caddy reload --config /etc/caddy/Caddyfile
docker logs --tail 100 NOME_DO_CADDY
```

### Caddy instalado no host

Neste caso, publicar a API somente em localhost:

```yaml
ports:
  - "127.0.0.1:8000:8000"
```

Caddyfile:

```caddyfile
ofertas.seudominio.com {
    encode zstd gzip
    reverse_proxy 127.0.0.1:8000
}
```

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
sudo journalctl -u caddy -n 100 --no-pager
```

Teste externo:

```powershell
curl.exe -I https://ofertas.seudominio.com/
curl.exe https://ofertas.seudominio.com/health
```

- [x] Certificado HTTPS emitido.
- [x] HTTP redireciona para HTTPS.
- [x] `/health` responde pelo domínio.
- [x] Painel abre no desktop.
- [ ] Painel funciona no celular.

## 15. Testar coleta manual e efetuar a virada

Antes de ativar o scheduler:

1. Selecionar uma fonte no painel.
2. Executar uma atualização manual.
3. Acompanhar os logs do worker.
4. Confirmar novo `catalog_run`.
5. Confirmar aumento das observações.
6. Testar individualmente fontes autenticadas.

```bash
docker logs --tail 200 -f NOME_DO_WORKER
```

```bash
docker exec "$PG_CONTAINER" psql -U flyer -d flyer -c "
SELECT provider_type,status,collected_at,product_count,priced_product_count
FROM catalog_runs ORDER BY collected_at DESC LIMIT 20;
"
```

### Tenda bloqueado pelo WAF

Se a coleta do Tenda retornar `HTTP 403` com `x-azion-request-id` (WAF da
Azion), a rota implementada é um forward proxy autorizado. No Portainer ou no
`.env.production`, definir:

```text
TENDA_PROXY_URL=http://USUARIO:SENHA@IP_DO_PROXY:3128
```

A variável afeta somente o coletor do Tenda. Recomendações do proxy:

- autenticação obrigatória e allowlist de hosts do Tenda (não pode ser proxy aberto);
- firewall liberando somente o IP da Oracle para a porta do proxy;
- o trânsito Oracle → proxy é HTTP sem TLS; para validação é aceitável, em
  produção use VPN/SSH tunnel ou TLS no listener.

Validar manualmente dentro do container:

```bash
docker exec "$API_CONTAINER" python -c "
import asyncio
from app.catalog.tenda import TendaCatalogClient
catalog = asyncio.run(TendaCatalogClient().collect())
print('products', catalog['product_count'])
print('errors', catalog.get('collection_errors'))
"
```

- [ ] `TENDA_PROXY_URL` definido no Portainer quando necessário.
- [ ] Coleta do Tenda validada com o proxy.

Quando a cloud estiver validada, manter a coleta local parada:

```powershell
docker compose stop scheduler worker api
```

No Portainer, ativar inicialmente somente catálogos:

```text
CATALOG_COLLECTION_ENABLED=true
DISCOVERY_ENABLED=false
```

- [x] Atualização manual concluída.
- [x] Assaí validado.
- [x] Davitta validada.
- [ ] Tenda validado.
- [x] São Vicente validado.
- [x] Demais fontes validadas.
- [x] Scheduler local parado.
- [x] Scheduler cloud ativado.
- [x] Não existem dois ambientes coletando simultaneamente.

## 16. Rollback de imagem

Em caso de problema, no Portainer trocar:

```text
APP_IMAGE=ghcr.io/namewellz/offer-monitoring:latest
```

por uma versão estável:

```text
APP_IMAGE=ghcr.io/namewellz/offer-monitoring:sha-HASH_DO_COMMIT
```

Atualizar a stack e validar `/health`. Rollback de imagem não desfaz migration
de banco automaticamente.

- [x] Tag SHA estável registrada.
- [x] Procedimento de rollback conhecido.

## 17. Backup recorrente

Configurar backup diário do PostgreSQL e de `/data`, com cópia para fora da
instância Oracle. O Watchtower não faz backup.

Política mínima sugerida:

```text
Dump PostgreSQL diário
Arquivo /data diário ou incremental
Retenção local de 14 dias
Cópia externa
Teste periódico de restauração
```

- [x] Backup automático configurado.
- [x] Retenção configurada.
- [ ] Cópia fora da Oracle configurada.
- [x] Restore de teste executado.

## Checklist final resumido

- [x] Código enviado ao GitHub sem segredos.
- [x] Imagem GHCR multi-arquitetura publicada.
- [x] Diretórios persistentes criados na Oracle.
- [x] Stack criada via Docker Compose e visível no Portainer.
- [x] Watchtower configurado sem duplicidade.
- [x] Dump PostgreSQL restaurado.
- [x] `/data` restaurado.
- [x] Contagens local e cloud conferidas.
- [x] DNS e Caddy configurados.
- [x] HTTPS funcionando.
- [ ] Interface validada no celular.
- [x] Coleta manual validada.
- [x] Scheduler cloud ativado.
- [x] Scheduler local desativado.
- [x] Backup recorrente configurado.
- [x] Rollback por tag SHA documentado.

## Registro do deploy de 2026-09-01

```text
URL: https://ofertas.overflowlab.net
Commit: b3bbe48c008fb3767ab75d83408c594084e762b2
Imagem: ghcr.io/namewellz/offer-monitoring:sha-b3bbe48c008fb3767ab75d83408c594084e762b2
Digest multi-arquitetura: sha256:95fd1db5582abaface8b7e99452a84da1ee3c52a845ea6dea2aa73a89b823cc8
Alembic: 0007_canonical_departments
```

Contagens no ponto de corte, conferidas localmente e na Oracle:

```text
retailers,8
stores,8
catalog_runs,184
catalog_products,152676
catalog_price_observations,3536850
flyers,4
product_offers,235
```

As coletas manuais de Arena, GoodBom, Atacadão, Savegnago, Davitta, Assaí e
São Vicente finalizaram com `SUCCESS`. O Tenda retornou `403 Forbidden` no WAF
da Azion para o IP de saída da Oracle, inclusive com cabeçalhos e cookies de
navegador. O histórico migrado do Tenda permanece disponível e a falha aparece
isoladamente na tela de atualizações. Para reativar essa coleta será necessária
uma rota de saída aceita pelo Tenda, como um proxy apropriado.
