# Reverse engineering da API do app "Meu AtacadÃ£o"

> **Objetivo deste documento.** Registrar, passo a passo e de forma reprodutÃ­vel, **como as
> credenciais e as rotas da API do app foram obtidas** â€” para que o processo possa ser repetido
> quando a Carrefour rotacionar `client_secret`, senha, `client_id` ou quando um app novo precisar
> do mesmo tratamento.
>
> Este Ã© o **estudo de caso concreto**. O procedimento genÃ©rico e reutilizÃ¡vel (para qualquer app)
> vive no agente `.github/agents/reverse-engineering.agent.md` e na skill
> `.github/skills/mobile-api-reverse-engineering/SKILL.md`.

---

## 0. Resultado obtido (resumo executivo)

| Item | Valor |
|---|---|
| App | `br.com.atacadao.b2c.app` — "Meu Atacadão" **v13.429.2** (`versionCode 876000`) |
| Runtime | Flutter / Dart, **arm64-v8a apenas** |
| API de ofertas da loja física | proxy: `https://txgwdepbtdvfnubmtewb.supabase.co/functions/v1/atacadao-in-store-offers` (origem real: `https://freyr.portal.atacadao.com.br`) |
| Autenticação (até 13.429.1) | Keycloak (realm `R-Mobile_Backend_Token-KC`) via Apigee, em `skadi-prod` |
| Autenticação (**agora**) | **server-side**: edge function da Supabase guarda a conta de serviço e repassa a chamada; o app só manda `x-api-key` |
| Cobertura | 389 lojas; o `idFilial` **é** o número da loja física (ex.: 632 = Hortolândia) |

Configuração usada pelo coletor (ver §14 para o histórico da rotação de Nov/2026):

```
ATACADAO_APP_BASE_URL = https://txgwdepbtdvfnubmtewb.supabase.co/functions/v1/atacadao-in-store-offers
ATACADAO_APP_API_KEY  = <REDACTED - see .env.production>   (header x-api-key)
```

Valores legados (não funcionam mais — a conta `kcc-ofertas-externo` foi
desativada no Keycloak em 31/10/2026):

```
client_id     = OfertaMobile-TokenAuth
client_secret = <REDACTED - see .env.production>
username      = kcc-ofertas-externo
password      = <REDACTED - see .env.production>
scope         = R-OfertasMobile-externo
```

Cliente pronto para uso: `scripts/atacadao_app_api.py` (sÃ³ `urllib`, sem dependÃªncias).

---

## Kit de ferramentas (tudo jÃ¡ no repositÃ³rio)

Todas funcionam isoladas; os prefixos indicam o papel. As de anÃ¡lise estÃ¡tica sÃ£o as primeiras a
usar em qualquer app novo.

| Script | Para que serve |
|---|---|
| `scan_app_bundle.py` | varre bundle de app hÃ­brido/Capacitor: hosts, rotas (inclui template literals) e chaves de config |
| `grep_bundle.py` | grep com contexto em bundle minificado (lÃª o bloco de configuraÃ§Ã£o do tenant) |
| `dart_strings.py` | dump/grep de strings do `libapp.so` (Dart AOT) com contexto — acha chaves de config, URLs e docstrings |
| `fetch_remote_config.py` | baixa o Remote Config de qualquer versÃ£o (`--version`) e imprime as chaves que casarem com `--match` |
| `probe_app_api_shape.py` | descobre limites de paginaÃ§Ã£o e o shape do catÃ¡logo por loja |
| `probe_departments.py` | prova de completude: departamentos devem somar o total geral |
| `probe_app_api_health.py` | chave + rotas da edge function do AtacadÃ£o (substitui o `probe_token_ttl.py`) |
| `list_app_stores.py` | registra as lojas da rede via API do app (AtacadÃ£o) |
| `validate_app_price.py` | consulta um produto especÃ­fico e mostra as trÃªs faixas de preÃ§o |
| `dump_store_offers.py` | pÃ¡gina as vitrines/ofertas de uma loja |
| `probe_spani_api.py` / `probe_spani_stores.py` / `probe_spani_cds.py` / `probe_spani_offers.py` | descoberta de rotas, unidades e ofertas da Spani |
| `compare_store_prices.py` | compara o preÃ§o do mesmo produto entre catÃ¡logos de lojas diferentes |
| `find_catalog_product.py` | acha um produto por termos e imprime as faixas de preÃ§o do catÃ¡logo coletado |
| `atacadao_app_api.py` | cliente de referÃªncia (sÃ³ `urllib`) da API do app do AtacadÃ£o |
| `patch_apk.py` + `build_patched_apk.ps1` | pipeline de patch/reassinatura do APK |
| `ui_taps.py` | automaÃ§Ã£o de UI via uiautomator quando a tela resiste |
| `mitm_capture.py` / `mitm_rewrite_rc.py` / `api_logger_proxy.py` | captura, reescrita de Remote Config e proxy reverso que loga em texto claro |

---

## 1. Ambiente necessÃ¡rio

Tudo jÃ¡ estÃ¡ instalado na mÃ¡quina `DESKTOP-0LFQFRU`. Em uma mÃ¡quina nova, reproduza este setup.

| Ferramenta | Caminho | ObservaÃ§Ã£o |
|---|---|---|
| Android SDK | `C:\Android\sdk` | build-tools 34.0.0, platform-tools |
| BlueStacks 5 | `C:\Program Files\BlueStacks_nxt` | instÃ¢ncia `Pie64` (Android 9 / API 28) |
| HD-Adb | `C:\Program Files\BlueStacks_nxt\HD-Adb.exe` | **adb v41 â€” use sempre este** |
| JDK 21 | `C:\Program Files\Eclipse Adoptium\jdk-21.0.12.8-hotspot` | para apktool/apksigner |
| apktool | `C:\Android\apktool\apktool.jar` | |
| OpenSSL | `C:\Program Files\Git\usr\bin\openssl.exe` | gerar CA do mitmproxy |
| venv de RE | `C:\Android\mitm-venv` | mitmproxy, pymupdf, pypdf |
| venv do projeto | `.venv` | httpx, SQLAlchemyâ€¦ |
| Artefatos/capturas | `C:\Android\capture` | logs, JSONs, APKs |

> **Pitfall crÃ­tico:** o `adb.exe` do Android SDK (v36) e o `HD-Adb.exe` (v41) conflitam pelo
> mesmo `adb server`. Sempre use o `HD-Adb.exe` para o BlueStacks e mate o outro antes
> (`& "C:\Android\sdk\platform-tools\adb.exe" kill-server`).

---

## 2. Fase 1 â€” Reconhecimento do pacote

1. Obtenha o **XAPK** oficial (APKMirror/APKPure) e extraia:
   `C:\Users\Wellz\AppData\Local\Temp\atacadao-xapk\{base.apk,split_0..3.apk}`
2. Verifique o manifesto antes de qualquer coisa:

```powershell
& "C:\Android\sdk\build-tools\34.0.0\aapt2.exe" dump badging "$env:TEMP\atacadao-xapk\base.apk" |
    Select-String "package:|native-code|sdkVersion|application-label:"
```

SaÃ­da relevante: `native-code: 'arm64-v8a'` â†’ **sÃ³ ARM64**. Isso decide toda a estratÃ©gia de
emulaÃ§Ã£o (seÃ§Ã£o 3): emulador x86 do Google **nÃ£o** roda, porque a traduÃ§Ã£o ARM64 via AOSP
(`qemu-system-aarch64`) nÃ£o inicializa neste host.

3. Decompile para procurar endpoints e segredos:

```powershell
$java = "C:\Program Files\Eclipse Adoptium\jdk-21.0.12.8-hotspot\bin\java.exe"
& $java -jar C:\Android\apktool\apktool.jar d -f -s -o C:\Android\apktool\base_src "$env:TEMP\atacadao-xapk\base.apk"
```

`-s` (= `--no-src`, manter `.dex`) acelera; o app Ã© Flutter, entÃ£o **a lÃ³gica de negÃ³cio estÃ¡ em
`lib/arm64-v8a/libapp.so`**, nÃ£o em smali. Scripts Ãºteis jÃ¡ no repositÃ³rio:

- `scripts/hunt_client_secret.py` â€” varre strings de todos os splits procurando `client_secret`,
  `Bearer`, `Authorization`, `openid-connect`, `keycloak`, `api_key`.
- `scripts/search_auth.py`, `scripts/search_auth2.py`, `scripts/inspect_auth.py` â€” buscas
  dirigidas no `libapp.so` (Dart AOT mantÃ©m URLs em texto claro; Ã© o melhor ponto de partida).
- `scripts/hunt_root_detection.py` â€” localiza a lib de detecÃ§Ã£o de root.

**LiÃ§Ã£o:** o `libapp.so` do Dart entrega URLs e nomes de parÃ¢metros em texto claro. Um
`strings`/regex nele jÃ¡ revela boa parte do contrato da API. O que ele **nÃ£o** entrega Ã© o
`client_secret`, que vem por **Firebase Remote Config** (seÃ§Ã£o 4).

---

## 3. Fase 2 â€” Rodar o app arm64-only

BlueStacks 5 com instÃ¢ncia **Pie64** traz traduÃ§Ã£o ARM64 (documentado pela BlueStacks para as
imagens "Pie 64-bit", "Android 11" e "Android 13"). `primaryCpuAbi=arm64-v8a` confirmado em runtime.

### 3.1 Habilitar ADB e root no BlueStacks

`C:\ProgramData\BlueStacks_nxt\bluestacks.conf`:

```ini
bst.enable_adb_access="1"
bst.enable_adb_remote_access="1"
bst.feature.rooting="1"
bst.instance.Pie64.enable_root_access="1"
```

**Pitfalls (todos jÃ¡ sofridos):**

- O BlueStacks **reescreve o `.conf` ao encerrar**: mate o processo antes de editar.
- `Set-Content -Encoding UTF8` no PowerShell 5.1 grava **BOM** â†’ o BlueStacks falha com
  *"Failed to read configuration file"*. E `[IO.File]::ReadAllText(path, UTF8)` **jÃ¡ remove** o
  BOM â€” se vocÃª remover "de novo" por conta prÃ³pria, come o primeiro byte (`b` de `bst.ai.enabled`).
  FaÃ§a: ler bytes â†’ remover BOM (se houver) â†’ regex â†’ gravar com `New-Object Text.UTF8Encoding($false)`.
- Scripts prontos: `scripts/bs_inspect_conf.ps1`, `scripts/bs_fix_conf.ps1`,
  `scripts/bs_fix_conf2.ps1`, `scripts/bs_enable_root_adb.ps1`.
- Instalar BlueStacks sem GUI: o micro-instalador WPF **nÃ£o aceita `/S`** (ele interpreta `/S`
  como caminho `C:\S`). SoluÃ§Ã£o: rodar elevado e clicar em "Install now"
  (`scripts/install_bluestacks.ps1`).

### 3.2 Conectar

```powershell
& "C:\Program Files\BlueStacks_nxt\HD-Adb.exe" connect 127.0.0.1:5555
& "C:\Program Files\BlueStacks_nxt\HD-Adb.exe" -s 127.0.0.1:5555 shell getprop ro.product.cpu.abilist
# -> x86_64,x86,arm64-v8a,armeabi-v7a,armeabi
```

Helper: `scripts/bs_adb.ps1`.

### 3.3 Instalar o app

Base + splits juntos (`install-multiple`, ordem: base primeiro):

```powershell
$adb = "C:\Program Files\BlueStacks_nxt\HD-Adb.exe"
& $adb -s 127.0.0.1:5555 install-multiple `
    "$env:TEMP\atacadao-xapk\base.apk" `
    "$env:TEMP\atacadao-xapk\split_0.apk" `
    "$env:TEMP\atacadao-xapk\split_1.apk" `
    "$env:TEMP\atacadao-xapk\split_2.apk" `
    "$env:TEMP\atacadao-xapk\split_3.apk"
```

Scripts: `scripts/install_apk.ps1`, `scripts/bs_capture.ps1`, `scripts/android_setup.ps1`.

---

## 4. Fase 3 â€” Captura de trÃ¡fego (o pulo do gato)

### 4.1 O problema: o Dart ignora o proxy do sistema

O proxy global do Android **nÃ£o** Ã© respeitado pelo `dart:io`/`HttpClient` do Flutter. Foi
verificado empiricamente: com proxy configurado, o mitmproxy sÃ³ viu trÃ¡fego dos SDKs **nativos**
(Facebook, Firebase, Crashlytics, Salesforce Marketing Cloud). Nenhuma chamada do app.

### 4.2 A soluÃ§Ã£o em duas partes

**(a) Fazer as URLs da API chegarem a um host nosso.**
O app lÃª as URLs base (`in_store_offers_api_url`, `in_store_offers_base_api_url`,
`in_store_offers_keycloak_login_url`, + variantes `hml_*`) do **Firebase Remote Config**. O RC Ã©
buscado por HTTP **nativo** (ou seja, esse trÃ¡fego *Ã©* interceptÃ¡vel). EntÃ£o:

1. `scripts/mitm_rewrite_rc.py` â€” addon do mitmproxy que reescreve a resposta do RC trocando
   essas chaves por `http://192.168.3.7:9999`.
2. `scripts/api_logger_proxy.py` â€” **proxy reverso HTTP puro** nessa porta que registra tudo em
   `C:\Android\capture\token_requests.jsonl` e encaminha:
   - `/realms/*`, `/resources/*` â†’ `https://skadi-prod.portal.atacadao.com.br`
   - todo o resto â†’ `https://freyr.portal.atacadao.com.br`

Rode os dois:

```powershell
# terminal 1 (mitmproxy com captura + reescrita do RC)
& "C:\Android\mitm-venv\Scripts\python.exe" -m mitmproxy `
    --listen-host 0.0.0.0 --listen-port 8080 `
    -s scripts\mitm_capture.py -s scripts\mitm_rewrite_rc.py

# terminal 2 (proxy reverso que fala com as duas origens reais)
& "C:\Android\mitm-venv\Scripts\python.exe" scripts\api_logger_proxy.py
```

Libere as portas no firewall (nÃ£o eleve a sessÃ£o: use `Start-Process -Verb RunAs`):

```powershell
New-NetFirewallRule -DisplayName "mitm8080" -Direction Inbound -Protocol TCP -LocalPort 8080 -Action Allow
New-NetFirewallRule -DisplayName "appproxy9999" -Direction Inbound -Protocol TCP -LocalPort 9999 -Action Allow
```

**(b) Fazer o app confiar no TLS do mitmproxy.**
Como o APK Ã© reassinado (seÃ§Ã£o 5), o jeito mais estÃ¡vel foi **embutir a CA** no APK em vez de
depender de CA de usuÃ¡rio. Script: `scripts/patch_apk.py` (etapa 3) + `scripts/build_patched_apk.ps1`.
Se preferir CA de usuÃ¡rio no guest: `scripts/install_ca.ps1` / `install_ca2.ps1` / `install_ca_user.ps1`.

> **Por que nÃ£o funciona sÃ³ o `frida-gadget`/`objection`?** NÃ£o Ã© necessÃ¡rio: a chave da captura nÃ£o
> Ã© bypass de pinning (o app confia na CA embutida) e sim **redirecionar o Dart**, que ignora o
> proxy. A reescrita do RC resolve isso sem instrumentaÃ§Ã£o em runtime â€” bem mais estÃ¡vel.

### 4.3 Ler a captura

```powershell
$env:PYTHONIOENCODING="utf-8"
& "C:\Android\mitm-venv\Scripts\python.exe" scripts\show_capture.py
```

TambÃ©m sÃ£o Ãºteis: `scripts/extract_capture.py`, `scripts/api_logger_proxy.py` (log bruto),
`scripts/fetch_remote_config.py`, `scripts/list_rc.py`, `scripts/rc_repeat_fetch.py`,
`scripts/enum_rc_namespaces.py` (sÃ³ o namespace `firebase` existe).

---

## 5. Fase 4 â€” Patches obrigatÃ³rios no APK

O app **recusa rodar em ambiente root** ("Dispositivo nÃ£o suportado") e, depois de reassinado,
perde o Remote Config (Firebase valida o certificado). `scripts/patch_apk.py` aplica as 4 etapas:

### 5.1 Root detection desligada

Lib: `com.w3conext.jailbreak_root_detection` (estilo RootBeer; checa `ro.debuggable=1`,
`ro.secure=0`, `test-keys`, presenÃ§a de `su`). O BlueStacks sempre cai em algum teste.
Patch (smali): `processJailBroken` â†’ `success(Boolean.FALSE)` e `processCheckIssues` â†’
`success(new ArrayList())`.

### 5.2 Identidade de certificado preservada (X-Android-Cert)

O FIS/Remote Config envia o header `X-Android-Cert`. Como o APK Ã© reassinado com a debug keystore,
o valor muda e o Firebase passa a negar o fetch â†’ o app perde os **399 valores** de RC.
SoluÃ§Ã£o: injetar o fingerprint **original** imediatamente antes de cada `const-string â€¦, "X-Android-Cert"`
(3 ocorrÃªncias):

```
smali/E9/o.smali
smali/m9/c.smali
smali/com/google/firebase/remoteconfig/internal/ConfigFetchHttpClient.smali
```

valor: `97B1257A29CBA1049C4B1F2D4DE3DBE5B1262040`

### 5.3 CA do mitmproxy embutida em `res/raw` + `network_security_config`

### 5.4 Splash do apktool

`res/drawable/launch_background.xml` reconstruÃ­do com `<bitmap android:src="@null">` â†’
`Resources$NotFoundException` no `MainActivity`. Substituir por um Ãºnico layer
`@android:color/white`.

### 5.5 Build e assinatura

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_patched_apk.ps1
```

apktool build â†’ `zipalign` â†’ `apksigner` com
`C:\Android\apktool\debug.keystore` (senha `android`, alias `androiddebugkey`, senha `android`).
SaÃ­da em `C:\Android\apktool\patched\*.apk`, instalada com `install-multiple`.

Variantes antigas (mantidas como referÃªncia): `build_modded_apk.ps1`, `build_modded_apk_ca.ps1`,
`patch_apk.ps1`.

### 5.6 AutomaÃ§Ã£o de UI (quando travar numa tela)

`scripts/ui_taps.py` â€” dirige o app por `uiautomator` via HD-Adb:

```powershell
python scripts\ui_taps.py dump                # Ã¡rvore de UI
python scripts\ui_taps.py screen              # screenshot
python scripts\ui_taps.py tap "Carnes, aves e peixes"
python scripts\ui_taps.py tapxy 450 1200      # coords no espaÃ§o retrato 900x1600
python scripts\ui_taps.py swipe
```

> **AtenÃ§Ã£o:** as coordenadas de `input tap` do BlueStacks sÃ£o no espaÃ§o **retrato 900x1600**,
> independentemente da rotaÃ§Ã£o mostrada na tela. Foi assim que descobrimos a rota real de busca
> (`/produto/busca`) depois de 14 tentativas por chute em `probe_search_route.py`.

---

## 6. Fase 5 â€” ExtraÃ§Ã£o estÃ¡tica do Remote Config (nem sempre dÃ¡ certo)

Antes do caminho dinÃ¢mico, tentamos o estÃ¡tico: `scripts/fetch_remote_config.py` extrai o
`google_app_id`, `api_key` e `project_id` do `strings`/`resources.arsc` do APK e chama a API do
Firebase Remote Config. Resultado: **399 chaves** recuperadas, guardadas em
`C:\Android\capture\remote_config.json` â€” mas **nenhum segredo de Keycloak** (o RC sÃ³ traz
parÃ¢metros pÃºblicos: URLs, flags, chaves de SDK). O `client_secret` sÃ³ apareceu no trÃ¡fego real.

Scripts auxiliares: `list_rc.py`, `enum_rc_namespaces.py`, `rc_repeat_fetch.py`,
`probe_keycloak_secrets.py`, `hunt_client_secret.py`, `token_logger.py`, `inspect_auth.py`.

> **Pitfall:** o fetch do RC precisa de `analytics_user_properties: {}` como **mapa**, nÃ£o lista â€”
> com lista, a API responde erro de tipo. E o namespace sÃ³ existe como `firebase`.

---

## 7. Fase 6 â€” Como o segredo apareceu

Com o RC reescrito (seÃ§Ã£o 4.2a), o Dart passou a mandar tudo em HTTP puro para
`192.168.3.7:9999` e o `token_requests.jsonl` registrou:

```
POST /infosec/auth/v1/protocol/openid-connect/token
Content-Type: application/x-www-form-urlencoded
User-Agent: Dart/3.10 (dart:io)

grant_type=password
username=kcc-ofertas-externo
password=<REDACTED - see .env.production>
client_id=OfertaMobile-TokenAuth
client_secret=<REDACTED - see .env.production>
```

Em seguida, `GET /mobile/ofertas-backoffice/v1/...` com `Authorization: Bearer <jwt>`.
Rotas reconstruÃ­das por observaÃ§Ã£o (scripts `find_product.py`, `probe_search_route.py`,
`dump_store_offers.py`, `probe_app_api_shape.py`, `probe_departments.py`).

### 7.1 Contrato da API (verificado em 2026-10-13)

Base: `https://freyr.portal.atacadao.com.br`

| Rota | ParÃ¢metros | Retorno |
|---|---|---|
| `POST /infosec/auth/v1/protocol/openid-connect/token` | form (acima) | `access_token`, `expires_in=3600`, `refresh_token` |
| `GET /mobile/ofertas-backoffice/v1/offer/status` | `filialId`, `idFilial` | `{"status":"DISPONIVEL"}` |
| `GET /mobile/ofertas-backoffice/v1/home/categorias` | `filialId`, `idFilial` | 18 departamentos `{idCategoria, category, imagemCategoria, totalOfertas}` |
| `GET /mobile/ofertas-backoffice/v1/home/banners` | `filialId`, `idFilial` (**obrigatÃ³rio**) | banners |
| `GET /mobile/ofertas-backoffice/v1/vitrine/mobile/v2` | `pageNumber`, `pageSize`â‰¤10, `pageProductSize`â‰¤10, `filialId`, `idFilial` | `{"Vitrines":[{idVitrine,title,products:[â€¦]}]}` |
| `GET /mobile/ofertas-backoffice/v1/vitrine-details/mobile/v2` | `idVitrine`, `pageNumber`, `pageSize`, `filialId`, `idFilial` | vitrine completa |
| `GET /mobile/ofertas-backoffice/v1/produto/busca` | `idCategoria?`, `search?`, `pageNumber`, `pageSize`â‰¤50, `onlyWithOffer`, `filialId`, `idFilial` | `{"Produtos":[â€¦], "totalItems", "totalPages"}` |
| `GET /mobile/ofertas-backoffice/v1/busca-loja-via-cidade-nome/v2` | `page`, `pageSize`, `cityOrName`, `lat`, `lon` | `{"data":[{idStore, storeName, address, â€¦, zipCode, vtexSellerId, ecommerce}]}` |
| `GET â€¦/busca-loja-via-cep/v2` | `page`, `pageSize`, `cep`, `lat`, `lon` | idem |
| `GET â€¦/busca-loja-via-geolocation/v2` | `page`, `pageSize`, `cityOrName`, `lat`, `lon` | idem |

**Objeto de produto** (o que interessa):

```json
{
  "idSku": 14910920, "idCategoria": 259, "idFilial": 632, "idOferta": 7610,
  "preco": "6.98", "finalPrice": "6.28", "finalCardPrice": null,
  "discountPercentage": 10, "discountCardPercentage": null,
  "quantityMax": 3, "quantityMin": 0,
  "title": "Salgadinho Batata Lay's Natural 62g", "category": "Salgadinho",
  "ean": 7892840825133, "variablePrice": false,
  "validity": "2026-10-13T23:36:10.427Z", "status": "DISPONIVEL",
  "imagem": "https://cdn.sistemabin.com.br/r/products/â€¦"
}
```

SemÃ¢ntica das faixas de preÃ§o (o motivo de tudo isso):

| Campo | Significado |
|---|---|
| `preco` | preÃ§o de **varejo/atacado** na loja fÃ­sica â€” Ã© o mesmo valor que o encarte chama de "PREÃ‡O VAREJO" |
| `finalPrice` | preÃ§o **com oferta do app** (quando hÃ¡ oferta ativa; `null` caso contrÃ¡rio) |
| `finalCardPrice` | preÃ§o **app + CartÃ£o AtacadÃ£o** (o melhor) |

> `preco` e `finalPrice` vÃªm como **string decimal** (`.`), `ean` como inteiro.

**Armadilha: `status` nÃ£o Ã© disponibilidade.** O endpoint pertence ao *backoffice de ofertas*, entÃ£o:

| `status` | Significado real |
|---|---|
| `"DISPONIVEL"` | o SKU **tem oferta ativa agora** (vem junto com `finalPrice`, `idOferta`, `quantityMax`) |
| `""` (vazio) | sem oferta ativa; o SKU sÃ³ tem o preÃ§o de gÃ´ndola `preco` |

Medido na loja 662 (Campinas Jd. Yeda), departamento Mercearia: 238 itens com
`status="DISPONIVEL"` (todos com `finalPrice`) e **2.873 com `status=""`** (sÃ³ `preco`). Mapear
`status == "DISPONIVEL"` para "disponÃ­vel" marcaria **96% do sortimento** como indisponÃ­vel.
Neste catÃ¡logo, disponibilidade = "a loja lista o SKU com preÃ§o"; oferta ativa = presenÃ§a de
`finalPrice` (vira `tier_prices` com `condition="app"` e `offer_tags`).

### 7.2 Volume real (loja 632 â€” HortolÃ¢ndia, 2026-10-13)

- CatÃ¡logo completo da loja: **8.788 SKUs** (`produto/busca` sem `idCategoria`).
- Os **18 departamentos particionam o catÃ¡logo exatamente** (soma = 8.788, diferenÃ§a 0).
- `pageSize` mÃ¡ximo Ã© **50** (`{"message":"pageSize deve ser no mÃ¡ximo 50"}`). 51+ â†’ HTTP 400.
- Uma varredura completa = ~184 requisiÃ§Ãµes (soma de `ceil(n/50)` por departamento).

| `idCategoria` | Departamento | Produtos |
|---|---|---:|
| 2 | Mercearia | 2.037 |
| 7 | Higiene e perfumaria | 1.635 |
| 4 | Bebidas | 1.084 |
| 3 | Frios e congelados | 1.048 |
| 8 | Limpeza | 793 |
| 4902 | Utilidades domÃ©sticas | 692 |
| 13 | Carnes, aves e peixes | 360 |
| 4891 | Padaria e matinais | 339 |
| 4912 | DescartÃ¡veis e embalagens | 222 |
| 11 | HortifrÃºti | 205 |
| 10 | Pet Shop | 127 |
| 9 | Automotivo | 101 |
| 4921 | VestuÃ¡rio | 35 |
| 4906 | EletrÃ´nicos e eletroportÃ¡teis | 34 |
| 9400 | Suplementos alimentares | 33 |
| 4914 | Papelaria | 17 |
| 4915 | Esporte e lazer | 15 |
| 4735 | Jardinagem | 11 |

### 7.3 ValidaÃ§Ã£o contra o encarte oficial da loja

Encarte "Ofertas AtacadÃ£o" 13â€“19/10/2026, pÃ¡gina 4 (HortolÃ¢ndia 632):

| Produto | Encarte varejo | Encarte app | Encarte app+cartÃ£o | **API do app** |
|---|---:|---:|---:|---|
| HambÃºrguer Bovino Nabrasa PerdigÃ£o Costela/Picanha 150g | 5,98 | 4,98 | 4,28 | **5,98 / 4,98 / 4,28** âœ… |
| LinguiÃ§a Toscana Aurora Congelada 700g | 19,90 | 17,90 | 15,50 | **19,90 / 17,91 / 15,50** âœ… |
| LinguiÃ§a Toscana PerdigÃ£o Nabrasa 700g (EAN 7891515644437) | â€” | â€” | â€” | **14,90** (sem oferta ativa) |

ConclusÃ£o: a API do app devolve **exatamente** os preÃ§os do folheto fÃ­sico daquela loja, com as
trÃªs faixas. Ã‰ a Ãºnica fonte com as faixas de app/cartÃ£o.

Comparativo com a fonte antiga (VTEX, `scripts/compare_flyer_vs_vtex.py` +
`summarize_encarte_vs_vtex.py`): o `preco` da API do app == preÃ§o VTEX em ~70% dos casos
(divergÃªncias quase sempre por casamento nomeâ†”embalagem em itens por kg). Ou seja, a API do app
**substitui** a VTEX e ainda entrega Americana (625), HortolÃ¢ndia (632), Indaiatuba (658) e outras
lojas que a simulaÃ§Ã£o VTEX nÃ£o precifica.

---

### 7.4 Varredura completa — 10 lojas da região de Campinas (2026-10-14)

`python -m app.cli atacadao-catalog --region campinas` (~23 min, 10 lojas em sequência):

| Loja | Filial | SKUs | Com preço | Com oferta app/cartão |
|---|---:|---:|---:|---:|
| Campinas Jd. Yeda | 662 | 11.732 | 11.732 | 487 |
| Campinas Dom Pedro | 663 | 11.045 | 11.045 | 473 |
| Campinas Dunlop 24h | 677 | 11.001 | 11.001 | 477 |
| **Hortolândia** | **632** | **8.788** | **8.788** | **387** |
| **Americana** | **625** | **9.763** | **9.763** | **411** |
| Indaiatuba | 658 | 11.349 | 11.349 | 455 |
| Itu | 816 | 10.832 | 10.832 | 466 |
| Jundiaí | 633 | 11.341 | 11.341 | 434 |
| Santa Bárbara d'Oeste | 948 | 10.552 | 10.552 | 461 |
| Sumaré | 736 | 11.224 | 11.224 | 473 |
| **TOTAL** | | **107.627** | **107.627** | **4.524** |

Zero erros de coleta. **Hortolândia (632) e Americana (625) entram na coleta** — eram exatamente as
duas lojas que a simulação VTEX não precificava e que ficavam de fora do catálogo antigo.

**Prova de que o preço é por loja** (`python scripts/compare_store_prices.py "artifacts/atacadao-catalog/atacadao-0[0-9]-catalog.json"`):

- 4.020 SKUs presentes nas 10 lojas;
- **3.676 (91,4%) com preço idêntico** na rede;
- **344 (8,6%) com preço divergente** entre lojas — exemplos:

| Produto | Yeda | Dom Pedro | Dunlop | Hortolândia | Americana | Indaiatuba | Itu | Jundiaí | Sta Bárbara | Sumaré |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Refrigerante Pepsi Cola 350ml | 3,39 | 3,39 | 3,39 | 3,39 | 3,39 | 3,39 | 3,39 | 3,39 | **2,56** | 3,39 |
| Mortadela Defumada Marba Bologna (kg) | 15,50 | 15,50 | 15,50 | **10,97** | 15,50 | 15,50 | 15,50 | 15,50 | 15,50 | 15,50 |
| Gelatina Dr. Oetker Sem Sabor 24g | 7,48 | 7,48 | 7,48 | 7,48 | 7,48 | **4,18** | **4,18** | 7,48 | **4,18** | **4,18** |
| Iogurte Danone 5x Zero Batido 1,2kg | 16,99 | 16,99 | 16,99 | 16,99 | **12,90** | 16,99 | **18,90** | 16,99 | 16,99 | 16,99 |

**Validação do item pedido pelo usuário** (Linguiça Toscana Perdigão Nabrasa Queijo Coalho 600g,
EAN 7891515485139) — três faixas, iguais ao encarte físico, em Yeda e Dom Pedro:
`regular = R$ 21,90 | oferta app = R$ 16,90 | app + cartão = R$ 14,50`.

A variante de 700g (EAN 7891515644437) aparece a R$ 20,50 em 9 das 10 lojas e a
**R$ 13,97 em Campinas Dunlop** — mais uma demonstração de que o valor é por loja.

---

## 8. Fase 7 — Verificação

```powershell
$env:PYTHONIOENCODING="utf-8"
$py = ".\.venv\Scripts\python.exe"          # o venv de RE também serve
$env:ATACADAO_APP_API_KEY = "<chave do .env.production>"

& $py scripts\probe_app_api_health.py        # chave + rotas (oferta, categorias, busca, lojas)
& $py scripts\probe_app_api_health.py 662    # mesma checagem em outra filial
& $py scripts\list_app_stores.py --region    # 43 lojas da RMC -> app_stores.json
& $py scripts\probe_app_api_shape.py 632     # limites de pageSize / varredura completa
& $py scripts\probe_departments.py 632       # departamentos x catálogo (deve fechar em 0)
& $py scripts\validate_app_price.py 632      # preço do produto do usuário na loja 632
& $py scripts\dump_store_offers.py 632       # vitrines (aplica só com oferta ativa)
```

Se `probe_app_api_health.py` sair com `OK`, `probe_departments.py` fechar em 0 e
`validate_app_price.py` mostrar os três preços, **a credencial está boa**.

Até Nov/2026 a checagem era `probe_token_ttl.py` (TTL/claims do Keycloak). Esse script foi
removido: não existe mais token no cliente — quem troca credencial com o Keycloak é a edge
function.

---

## 9. Playbook: as credenciais mudaram. E agora?

### 9.1 Diagnóstico pelo código de erro

| Sintoma | Causa provável | Ação |
|---|---|---|
| `400 {"error":"invalid_grant","error_description":"Account disabled"}` | a conta de serviço do Keycloak foi desativada (foi o que aconteceu em 31/10/2026) | Não é mais recuperável pelo app: a auth virou server-side → §14 |
| `401 {"error":"Missing API key."}` | faltou/errou o header `x-api-key` da edge function | Conferir `ATACADAO_APP_API_KEY` |
| `429 {"error":"Too many requests. Please try again later."}` | rate limit da edge function | Baixar concorrência (`MAX_CONCURRENCY`) e repetir com backoff |
| `404 {"error":"Route not found."}` | rota inexistente **na edge function** (o path do freyr vem depois do nome da função) | Ver 14.3 |
| `401 {"error":"invalid_client"}` (legado) | `client_secret`/`client_id` rotacionados | Só se voltarem ao fluxo direto; ver 9.2 |
| `403` com HTML/JSON do Apigee | rota bloqueada/regra mudou | Revalidar as rotas (7.1) |
| Todos os preços `null` | loja sem ofertas ou `idFilial` errado | `probe_departments.py` |

### 9.2 Recaptura (fluxo legado, ≤13.429.1)

Só vale se a api voltar a usar Keycloak direto. O APK patcheado já está no BlueStacks:

1. Suba o mitmproxy e o proxy reverso (seção 4.2a) e confirme o proxy global do guest.
2. Abra o app "Meu Atacadão" → tela de ofertas da loja (o app refaz o login do Keycloak na
   primeira chamada autenticada).
3. `scripts/show_capture.py` → pegue `client_id`, `client_secret`, `username`, `password`.
4. Atualize as variáveis de ambiente e rode `probe_app_api_health.py`.

### 9.3 Se o app subir de versão

1. Baixe o novo XAPK e confira `versionCode`/ABIs (`aapt2 dump badging`).
2. Compare o snapshot Dart com o da versão anterior (§14.2 mostra o método): se
   `/infosec/auth/v1/protocol/openid-connect/token` ou `client_secret` sumirem/voltarem, o
   transporte mudou de novo.
3. Repita a Fase 4. Os alvos dos patches (smali de root detection, `X-Android-Cert`, splash)
   podem mudar de arquivo — os scripts localizam por **padrão de string**, não por nome de arquivo.
4. Faça o fetch do Remote Config da nova versão (`scripts/fetch_remote_config.py --version X`) e
   compare com a versão anterior; uma chave nova do tipo `*_proxy_function` indica mudança de
   transporte.
5. Rode o app por alguns minutos com a captura ligada e faça `diff` das rotas observadas contra a
   tabela 7.1.

### 9.4 Onde NÃO colocar credencial

Nada de chave hardcoded em módulo de produção. O coletor lê de ambiente:

```
ATACADAO_APP_BASE_URL   (default: a edge function de produção)
ATACADAO_APP_API_KEY    (header x-api-key; sem default)
```

Os `scripts/` de RE mantêm os valores observados como default, o que é aceitável porque são
ferramentas de investigação — mas rotacione e migre para `.env`/secret manager antes de qualquer
deploy.

---

## 10. CatÃ¡logo de pitfalls (resumo do que doeu)

| # | Sintoma | Causa | SoluÃ§Ã£o |
|---|---|---|---|
| 1 | Emulador x86 morre com `PCI bus not available for hda` | app arm64-only, `qemu-system-aarch64` nÃ£o sobe neste host | BlueStacks Pie64 com traduÃ§Ã£o ARM64 |
| 2 | Instalador BlueStacks cria `C:\S` | `/S` nÃ£o suportado (WPF) | instalar pela GUI, elevado |
| 3 | BlueStacks: "Failed to read configuration file" | BOM UTF-8 no `.conf` | gravar com `UTF8Encoding($false)` |
| 4 | Config corrompida (`st.ai.enabled`) | remoÃ§Ã£o dupla de BOM | ler bytes, remover BOM **uma vez** |
| 5 | Conf editado some | BlueStacks reescreve na saÃ­da | matar o processo antes de editar |
| 6 | "Dispositivo nÃ£o suportado" | root detection | patch smali (`processJailBroken`) |
| 7 | App perde as 399 chaves de RC apÃ³s reassinar | Firebase valida `X-Android-Cert` | injetar o fingerprint original |
| 8 | `Resources$NotFoundException` no launch | splash apktool virou `@null` | layer `@android:color/white` |
| 9 | mitmproxy sÃ³ vÃª Facebook/Firebase/Crashlytics | Dart ignora o proxy do sistema | reescrever o RC para um proxy reverso HTTP |
| 10 | `adb` "connection reset" | `adb root` reinicia o adbd; conflito de versÃµes | usar sÃ³ `HD-Adb.exe` |
| 11 | 14 rotas de busca dÃ£o 404 | chute de path | descobrir a rota real navegando no app + `ui_taps.py` |
| 12 | `pageSize` grande â†’ HTTP 400 | limite do servidor Ã© 50 | paginar com 50 |
| 13 | `home/banners` â†’ 400 `idFilial Ã© um campo obrigatÃ³rio` | parÃ¢metro esquecido | mandar sempre `filialId` **e** `idFilial` |
| 14 | Coordenadas de toque erradas | espaÃ§o retrato 900x1600 | converter antes de `input tap` |
| 15 | `status` lido como disponibilidade | campo Ã© da **oferta**, nÃ£o do produto | disponibilidade = "loja lista com preÃ§o" (Â§ 7.1) |
| 16 | App hÃ­brido tratado como nativo | WebView (Capacitor/Cordova) | conferir `native-code` no `dump badging` primeiro (Â§ 11) |

---

## 11. Caso 2 â€” Spani Atacadista (`br.com.spanionline.appvendas` 1.146.1)

### 11.1 Um app hÃ­brido Ã© o melhor cenÃ¡rio possÃ­vel

`aapt2 dump badging` **nÃ£o** devolve linha `native-code`: o app nÃ£o tem `lib/*.so`. O
`capacitor.config.json` em `assets/` entrega o resto â€” `appId: develop.omnichannel`,
`webDir: ../../dist/apps/aplicativo/browser`. Ã‰ um **Angular em WebView (Capacitor)**.

ConsequÃªncia prÃ¡tica: o frontend inteiro estÃ¡ em `assets/public/*.js` legÃ­vel, incluindo o bloco de
configuraÃ§Ã£o do tenant:

```js
var gm = {
  production: true,
  apiServicesUrl: "https://services.vipcommerce.com.br",
  lojaUser: "loja",
  lojaAuthJWT: "df072f85df9bf7dd71b6811c34bdbaa4f219d98775b56cff9dfa5f8ca1bf8469",
  isApp: true,
  apiUrl: "https://services-beta.vipcommerce.com.br/api-admin/v1",
  wsUrl:  "https://services-beta.vipcommerce.com.br/ws",
  idAplicativo: 72,
  domainKey: "spanionline.com.br",
  showCaptcha: true,
  orgId: 67,
  smartHintBaseUrl: "https://recs.smarthint.co"
}
```

Achado em **um comando**, sem emulador, sem proxy, sem patch:

```powershell
python scripts\scan_app_bundle.py "C:\Android\apktool\spani_src" `
    --show-routes --show-config --json C:\Android\capture\spani_bundle_scan.json
```

Ferramentas usadas: `scripts/scan_app_bundle.py` (hosts, rotas, chaves de config) e
`scripts/grep_bundle.py` (contexto em bundle minificado). **LiÃ§Ãµes:**

1. Antes de montar emulador + mitmproxy, verifique se o app Ã© hÃ­brido. Se for, o caminho estÃ¡tico
   resolve tudo â€” inclusive credenciais.
2. Rotas em *template literal* (`/loja/filiais/${id}`) sÃ£o invisÃ­veis para um regex que sÃ³ aceita
   `"` e `'`. O scanner precisou incluir **backticks** para achar o contrato completo.
3. O bloco de configuraÃ§Ã£o do tenant Ã© o artefato mais valioso do bundle: dÃ¡ host, org, credencial
   de sessÃ£o anÃ´nima e o id da aplicaÃ§Ã£o de uma vez.

### 11.2 O que a API responde

| Rota | Papel |
|---|---|
| `POST /api-admin/v1/org/67/auth/loja/login` | sessÃ£o anÃ´nima da loja (`{domain, username:"loja", key}` + headers `domainkey`/`organizationid`) |
| `GET /org/67/loja/filiais/1` | filial `108` â€” "SPANI Atacadista" |
| `GET /org/67/filial/1/loja/centros_distribuicoes/retiradas` | **33 unidades** (toda a rede) com CNPJ, endereÃ§o, CEP e coordenadas |
| `GET /org/67/filial/1/loja/centros_distribuicoes/cep/{cep}/entrega` | quais unidades atendem um CEP |
| `GET /org/67/loja/centros_distribuicoes/{cd}` | dados de uma unidade |
| `GET /org/67/filial/1/centro_distribuicao/{cd}/loja/classificacoes_mercadologicas/departamentos/arvore` | 14 departamentos da unidade, com `total_ofertas` |
| `GET â€¦/departamentos/{id}/produtos?page=N&limit=M` | **preÃ§os** da unidade (`preco`, `oferta.preco_antigo`, `oferta.preco_oferta`, `disponivel`, `codigo_barras`) |
| `GET /org/67/loja/televendas/filiais` | existe, mas **403 "NÃ£o autorizado"** com a credencial da loja (exige token de operador de televendas) |

**Armadilha de identificador.** A unidade devolvida por `retiradas` traz **dois** ids:

```json
{ "id": 1, "nome_site": "Spani Vista Verde",
  "vipcommerce_centro_distribuicao_id": 239, ... }
```

O campo **`id`** Ã© o valor que as rotas de catÃ¡logo esperam como `centro_distribuicao`.
`vipcommerce_centro_distribuicao_id` Ã© um identificador global paralelo e **nÃ£o** funciona no path
do catÃ¡logo. ConfirmaÃ§Ã£o: `/loja/centros_distribuicoes/42` devolve "Spani Campinas 3" e o catÃ¡logo
de `cd=42` responde com produtos e preÃ§os.

### 11.3 Ofertas (preÃ§o promocional): onde ficam e como verificar

O listing de departamento **nÃ£o** carrega oferta: em 672 itens amostrados do departamento 4,
`em_oferta: false` e `oferta: null` em 100% deles. A oferta tem rota prÃ³pria:

```
GET /org/67/filial/1/centro_distribuicao/42/loja/produtos/em-oferta?page=1&limit=20
GET /org/67/filial/1/centro_distribuicao/42/loja/produtos/em-oferta/filtros
```

E o prÃ³prio servidor informa o tamanho da oferta no filtro:

```json
{"name": "em_oferta", "type": "INTERNAL", "label": "Ofertas",
 "options": [{"value": false, "label": "Em oferta", "count": 0, "checked": false}]}
```

`count: 0` e `data: []` **coincidem** com o `0 em oferta` reportado pela coleta â€” ou seja, no
momento da execuÃ§Ã£o (2026-10-14 00:20) a unidade CD 42 realmente nÃ£o tinha nenhum produto em
oferta. **Como checar antes de concluir que o coletor "perdeu" as ofertas:** consulte
`/produtos/em-oferta/filtros` e leia `count`; se for 0, nÃ£o hÃ¡ oferta para perder. Com `count > 0`,
a rota `/produtos/em-oferta` Ã© a fonte (o shape dela com ofertas ativas ainda nÃ£o foi observado â€”
registre-o quando aparecer).

### 11.4 EvidÃªncia de cobertura e de preÃ§o por loja

```
filial: 108  SPANI Atacadista
total de unidades (retiradas): 33
unidades em Campinas: 3
  cd 40  Spani Campinas 1   (Alphaville Dom Pedro, cep 13097171)
  cd 41  Spani Campinas 2   (Parque UniversitÃ¡rio de Viracopos, cep 13056460)
  cd 42  Spani Campinas 3   (Jardim PaulicÃ©ia, cep 13060080)
outras relevantes: cd 18 Spani Americana | cd 34 Spani VÃ¡rzea Paulista
```

Consulta por CEP (mesma rota que o app usa no checkout):

| CEP | Unidade que atende |
|---|---|
| 13060080 (Campinas, CambuÃ­) | cd 42 â€” Spani Campinas 3 |
| 13060646 (Campinas, Jd. Yeda) | cd 42 â€” Spani Campinas 3 |
| 13076000 (Campinas, Taquaral) | cd 40 â€” Spani Campinas 1 |
| 13472415 (Americana) | cd 18 â€” Spani Americana |
| 13080395 / 13097171 / 13184668 | nenhuma unidade |

PreÃ§os lidos diretamente da API, mesmo item em unidades diferentes:

| Produto (EAN) | Campinas 1 (cd 40) | Campinas 2 (cd 41) | Campinas 3 (cd 42) |
|---|---:|---:|---:|
| Arroz Tipo 1 Broto Legal 5kg (7896901200143) | 28,25 | 28,25 | 28,25 |
| Biscoito Belvita 75g Leite com Aveia (7622210661746) | 5,69 | 5,69 | 5,69 |

O preÃ§o Ã© servido **por unidade** (a API Ã© escopada em `filial`+`centro_distribuicao`), mas a rede
pratica preÃ§o Ãºnico nas trÃªs lojas de Campinas nesse recorte â€” o valor estÃ¡vel entre unidades Ã© a
prÃ³pria evidÃªncia de que a escopagem estÃ¡ correta.

**Prova de que a coleta Ã© por loja â€” catÃ¡logos completos das 3 unidades de Campinas**
(`python -m app.cli spani-catalog --region campinas`, 2026-10-14):

| Unidade | SKUs | Com preÃ§o |
|---|---:|---:|
| Spani Campinas 1 (cd 40) | 5.647 | 5.647 |
| Spani Campinas 2 (cd 41) | 5.442 | 5.442 |
| Spani Campinas 3 (cd 42) | 5.620 | 5.620 |
| **total** | **16.709** | **16.709** |

InterseÃ§Ã£o por `produto_id`: **5.414 SKUs** presentes nas trÃªs. Desses, **5.412 (100,0%) com o
mesmo preÃ§o** e **2 divergentes** â€” a lista fechada de divergÃªncias Ã© a prova de que o preÃ§o Ã©
escopado por loja e nÃ£o uma lista Ãºnica do site replicada:

| Produto | Campinas 1 | Campinas 2 | Campinas 3 |
|---|---:|---:|---:|
| Salaminho Seara Fatiado 100g | 8,29 | 8,29 | **7,91** |
| Carne Bovina FilÃ© Mignon Pul 500g | 68,85 | **49,24** | 68,85 |

Comando da comparaÃ§Ã£o: `python scripts/compare_store_prices.py "artifacts/spani-catalog/spani-0*-catalog.json"`.

### 11.5 ImplementaÃ§Ã£o

`app/catalog/vipcommerce.py` (o mesmo cliente que jÃ¡ servia Dalben) ganhou:

- `list_centros_distribuicao(city=None)` â€” enumera as unidades da rede;
- `unit_store(unit)` â€” combina a unidade com a configuraÃ§Ã£o do tenant;
- `collect_many(units)` â€” **um catÃ¡logo por unidade**, sequencial para manter `collected_at`
  monotÃ´nico (ver Â§ 11.6);
- `SpaniCatalogClient.collect_all(city="Campinas")` â€” usado pelo agendador.

CLI: `python -m app.cli spani-catalog --region campinas` (ou `--cd 40 --cd 41 --cd 42`, ou
`--region todas`). `app/jobs/tasks.py` passou a preferir `collect_all()` quando o coletor expÃµe
esse mÃ©todo, gravando um catÃ¡logo por unidade (`spani-00`, `spani-01`, â€¦).

### 11.6 Bug de produÃ§Ã£o descoberto no caminho (AtacadÃ£o)

`source_product_versions` tem o check `valid_until IS NULL OR valid_until >= valid_from`
(`ck_source_versions_valid_window`). O ingest fecha a versÃ£o aberta usando o `collected_at` do
catÃ¡logo que estÃ¡ chegando. Se os catÃ¡logos de um mesmo run forem **persistidos fora da ordem de
observaÃ§Ã£o** (o que acontece naturalmente quando as lojas sÃ£o coletadas em paralelo e o timestamp
Ã© carimbado ao final de cada uma), o `valid_until` fica **anterior** ao `valid_from` e o run inteiro
aborta com `CheckViolation`.

CorreÃ§Ã£o: coletar lojas em ordem e garantir que a lista devolvida esteja ordenada por
`collected_at` **antes** de persistir. EstÃ¡ implementado nas duas pontas (`atacadao.py` e
`vipcommerce.py`) com o comentÃ¡rio explicando o porquÃª.

---

## 12. Checklist para um app novo (revisado)

Ordem pensada para **descartar o caminho caro o quanto antes**.

1. **`aapt2 dump badging`** â€” package, versÃ£o, ABIs, SDK.
   - sem linha `native-code` â†’ **hÃ­brido** (WebView). VÃ¡ para o passo 2 e provavelmente termine aÃ­.
   - com `native-code` arm64-only â†’ precisarÃ¡ de device com traduÃ§Ã£o ARM64 (Â§ 3).
2. **Bundle hÃ­brido?** `scripts/scan_app_bundle.py --show-routes --show-config` + `scripts/grep_bundle.py`.
   Procure o bloco de configuraÃ§Ã£o do tenant (`apiUrl`, `baseUrl`, `domainKey`, `orgId`,
   `clientId`, `lojaAuthJWT`). Rotas aparecem em strings **e** em template literals.
3. **BinÃ¡rio nativo?** `strings`/regex em `lib/*/lib*.so` ou nas classes dex. Procure URLs,
   `Bearer`, `Authorization`, `client_secret`, `api_key`.
   - **Sempre** rode o dump tambÃ©m nos `classes*.dex`, mesmo quando existe bundle hÃ­brido/RN: no
     Tenda a URL da API estava sÃ³ no dex (Â§ 13.2). `scripts/extract_strings.py <dir> --min 8 --unique`.
4. **Config remota** (Firebase RC, bootstrap) â€” se as URLs vÃªm de lÃ¡, elas sÃ£o interceptÃ¡veis por
   HTTP nativo, o que abre o truque do proxy reverso (Â§ 4).
5. **SÃ³ entÃ£o** montar o ambiente de execuÃ§Ã£o: BlueStacks Pie64, ADB, root, `install-multiple`.
6. **Captura**: mitmproxy + CA. Antes de concluir qualquer coisa, liste **quais hosts** aparecem.
   SÃ³ SDK nativo â‡’ o runtime ignora o proxy (Â§ 4.2).
7. **Remover bloqueios**: root detection, identidade de certificado, splash quebrado (Â§ 5).
8. **Induzir a chamada** navegando atÃ© a tela; `scripts/ui_taps.py` quando a tela resistir.
9. **Mapear o contrato**: remova um query param por vez (o erro nomeia o obrigatÃ³rio), suba
   `pageSize` atÃ© o servidor reclamar, e **feche a partiÃ§Ã£o** (soma por categoria == total geral).
10. **Cliente mÃ­nimo** (`urllib` ou `httpx`), token com cache + retry em 401, concorrÃªncia baixa.
11. **Validar** contra fonte independente (Â§ 7.3) e, quando houver mais de uma loja,
    `scripts/compare_store_prices.py` para provar que a coleta Ã© escopada por loja.
12. **Registrar**: memÃ³ria do repo + `docs/` + sÃ³ o genÃ©rico volta para
    `.github/skills/mobile-api-reverse-engineering/`.
13. **Segredos** para env/secret manager antes de virar cÃ³digo de produÃ§Ã£o.

### Erros de schema que aparecem na virada de um app novo

| Erro | Causa | CorreÃ§Ã£o |
|---|---|---|
| `CheckViolation ck_source_versions_valid_window` | catÃ¡logos persistidos fora da ordem de observaÃ§Ã£o | coletar/ordenar por `collected_at` (Â§ 11.6) |
| `StringDataRightTruncation â€¦ character varying(2)` | API devolve o estado por extenso ("SÃ£o Paulo") e `stores.state` Ã© `varchar(2)` | normalizar para UF antes de montar o catÃ¡logo |
| `UndefinedTable â€¦ catalog_products` | banco de dev sem as tabelas legadas (o cÃ³digo faz dual-write legado + v2) | recriar as tabelas a partir dos modelos antes de validar |
| `getaddrinfo failed host 'postgres'` | rodando do host em vez da rede do compose | `docker run --network offer-monitoring_default` com o repo montado (Â§ 13.1) |

### 12.1 Como rodar o coletor localmente contra o Postgres do compose

O Postgres do `docker-compose.yml` nÃ£o publica porta e o host nÃ£o resolve `postgres`. Rode dentro
da rede do compose, montando o repositÃ³rio e reaproveitando a imagem jÃ¡ construÃ­da (traz as
dependÃªncias):

```powershell
docker run --rm --network offer-monitoring_default `
  -v "c:\fonts\offer-monitoring:/app" -w /app `
  -e DATABASE_URL="postgresql+psycopg://flyer:flyer@postgres:5432/flyer" `
  -e PYTHONIOENCODING=utf-8 `
  offer-monitoring-api python -m app.cli atacadao-catalog --region campinas
```

O mesmo padrÃ£o serve para qualquer comando do CLI (`spani-catalog`, `backfill-v2`, â€¦).

---

## 13. Caso 3 — Tenda Atacado (`com.root.tendadrive.Activities` 10.8.2)

Pergunta do usuário: *"o app usa a mesma API que o site já usa no projeto, ou é o mesmo caso do
Atacadão (que tinha API melhor no app)?"* Resposta curta: **é a mesma API**. A diferença real não
estava na rota, estava no **campo de oferta que o coletor não lia**.

### 13.1 Reconhecimento do pacote

```powershell
# XAPK -> base.apk + splits
Expand-Archive "$env:TEMP\Tenda Atacado_10.8.2.xapk" -DestinationPath $env:TEMP\tenda-xapk
aapt2 dump badging "$env:TEMP\tenda-xapk\base.apk" | Select-String "package:|sdkVersion|targetSdk|launchable|native-code"
```

| Item | Valor |
|---|---|
| package / versionName / versionCode | `com.root.tendadrive.Activities` / `10.8.2` / `806572` |
| minSdk / targetSdk | 24 / 36 |
| `native-code` no `base.apk` | **ausente** (as `.so` ficam no split de ABI: `split_0.apk`, 32,2 MB, 34 libs **arm64-v8a**) |
| framework | React Native + Expo SDK 57, bundle em **Hermes bytecode** |
| `assets/index.android.bundle` | 7,76 MB, magic `c6 1f bc 03` |
| `assets/app.config` | slug `tenda`, Sentry `tenda-mobile-b2c-app`/`b2c-app`, FB appID `170490998090819` |
| pinning | módulo nativo próprio `SslPinningModule` (mais um motivo para não depender de mitm) |

### 13.2 A lição: a URL não estava no bundle JS

`scripts/extract_strings.py` no `assets/index.android.bundle` devolveu só assets de marketing
(`tendaatacado.com.br/assets/blackFriday/...`), e-mails de contato, deep link `tendadrive://` e
domínios de bibliotecas (MDN, Sentry, reanimated). **Nenhuma URL de API.**

Em app React Native a base costuma vir de `expo-constants`/`extra` (injetada no bundle) ou do lado
nativo — e aqui foi o nativo. A resposta estava nos dex:

```powershell
# extrai dex + .so do base.apk/split_0.apk e roda o dump recursivo
python scripts\extract_strings.py "$env:TEMP\tenda-xapk\ex" --min 8 --unique --out C:\Android\capture\tenda_native_strings.txt
Select-String -Path C:\Android\capture\tenda_native_strings.txt -Pattern "tendaatacado" | ForEach-Object Line | Sort-Object -Unique
```

Resultado (único em toda a árvore de 465.435 strings):

```
https://api.tendaatacado.com.br/api
https://services.tendaatacado.com.br
https://tendaatacado.com.br
```

Ou seja, `extract_strings.py` agora **aceita diretório** (passou a varrer dex/so/asset de uma vez).
Regra prática nova para o checklist (§12 item 3): *se o bundle híbrido/RN não traz a URL, o próximo
lugar é `classes*.dex`, não a captura de tráfego.*

### 13.3 O app chama as mesmas rotas do coletor

Rotas reconstruídas das strings do bundle + dos dex (a API é montada por concatenação, então os
caminhos aparecem como fragmentos: `api/public/...`):

| Função | Rota | O coletor já usava? |
|---|---|---|
| Departamentos | `GET /public/store/departments` | sim |
| Produtos por categoria | `GET /public/store/category/{id}/products?page&order&save` | sim |
| Lista de filiais | `GET /public/branch/all` | **não** (novo) |
| Filial por CEP | `GET /public/branch/zip/{cep}` | **não** (novo) |
| Vitrine de novidades | `GET /public/store/category/products/newness` | não |
| Busca | `GET /public/store/search?query=` | não |
| Banner/home | `GET /public/ads/view`, `/public/component/home-mobile` | não |
| Conta (exige login) | `/public/oauth/access-token`, `/public/anonymous-client`, `/public/client/*`, `/public/client/v2/pre-registration` | não (e não precisa) |

O app **não pede login** para ver ofertas porque tudo isso é `/public/*`. A busca do site usa
`query` (o app também): `?search=` devolve `400 {"error":"Invalid parameter 'query'"}`.

### 13.4 Evidência do CEP do usuário (13184-494 → Hortolândia)

```powershell
python scripts\probe_tenda_app.py --cep 13184494 --branch-id 46
```

```
GET /public/branch/zip/13184494 -> 200
  [{"id": 46, "code": "CT39", "name": "Hortolândia", "address": {"zipCode": "13184494", ...
    "city": "Hortolândia", "latitude": -22.8638, "longitude": -47.21369},
    "distance": 38.81, ...}, {"id": 12, "code": "CT32", "name": "Sumaré"}, {"id": 40, "code": "CAMP", ...}]
```

A filial resolvida é **exatamente** o `BRANCH_ID = "46"` / `CT39` que o coletor já usava — o
`REFERENCE_ZIP_CODE` do código (`13184222`) e o CEP que o usuário digitou no app (`13184494`)
caem na mesma loja (a 38,8 m do endereço).

### 13.5 Preço é da rede, estoque é da loja (e as ofertas são do app)

```powershell
python scripts\probe_tenda_branch.py   # comparativo com/sem branchId
```

| Verificação | Resultado |
|---|---|
| `?branchId=46` muda `price`, `promotions` ou `inventory`? | **não** — 0 divergências em 2 categorias × 20 produtos |
| Tamanho de `inventory[]` | 45 filiais em **todas** as respostas (com e sem `branchId`) |
| `totalStock` | agregado da rede (limitado em 500) |
| Produtos com `promotions[]` | ~13% na categoria 1 (páginas 1–5) |
| Produtos com `promotion` (singular) | 0 nas páginas testadas; aparece em outros departamentos |

Consequência: **coletar outra filial não muda preço nenhum**, só `available`/`stock`. Por isso o
`collect()` continua sendo uma loja (Hortolândia/CT39) e a coleta multi-loja ficou em
`collect_region()` — **de propósito sem o nome `collect_all()`**, que é o protocolo que
`app/jobs/tasks.py` procura para trocar o agendador de uma loja para N (a CLI expõe via
`--region campinas|rmc`).

Estrutura da oferta do app (payload real, produto 1007):

```json
"promotions": [
  {"template": "DESCONTOU_PLUS", "price": 4.99,
   "restriction": {"title": "Cliente APP pagando com o Cartão Tenda",
                   "rules": [{"type": "PERIOD_OF_VALIDITY"}, {"type": "CARTAO_TENDA"}]}},
  {"template": "DESCONTOU", "price": 5.59,
   "restriction": {"title": "Cliente APP", "rules": [{"type": "PERIOD_OF_VALIDITY"}]}}
]
```

O `promotion` (singular) que o coletor antigo lia **não existe mais** na listagem de categorias —
era o motivo de o catálogo sair praticamente sem oferta.

### 13.6 Implementação

`app/catalog/tenda.py`:

* `_app_promotions()` lê `promotions[]`, usa o `template` como tag (`app:descontou`,
  `app:descontou_plus`) e a regra `CARTAO_TENDA` (com fallback pelo sufixo `PLUS`) para separar o
  preço do cartão.
* `sales_price` = **menor** preço do app que não exige o Cartão Tenda; o preço de gôndola vira
  `regular_price`; o preço do cartão entra como `TierPrice(condition="app-cartao")` — mesma
  semântica usada no Atacadão (`finalPrice` → `sales_price`, `finalCardPrice` → tier).
* `wholesalePrices[]` continua virando tier de quantidade (`minQuantity`).
* `branches()`, `resolve_zip()`, `find_stores()` (`/public/branch/all` + `/public/branch/zip`),
  `collect_many()` (sequencial, ordenado por `collected_at`), `collect()` (loja padrão) e
  `collect_region(cities)` (opt-in, fora do agendador).
* `store` do payload ganhou `branch_id`, `store_id` (`tenda:46`), `store_code` (`CT39`) e
  `sales_channel` (`tenda-app`), que é o que o ingest v2 usa para casar `collection_targets`.

CLI:

```powershell
python -m app.cli tenda-catalog                            # Hortolândia/CT39 (padrão)
python -m app.cli tenda-catalog --branch 5 --branch 40      # lojas específicas
python -m app.cli tenda-catalog --region campinas           # RMC (7 lojas)
python -m app.cli tenda-catalog --region rmc                # RMC + Itu/Jundiaí/Salto/Piracicaba
```

Scripts novos: `scripts/probe_tenda_app.py` (rotas + comparativo), `scripts/verify_tenda_app.py`
(varredura + relatório em `artifacts/tenda-app-sweep`).

### 13.7 Varredura completa (Hortolândia/CT39, 2026-10-15)

```powershell
python scripts\verify_tenda_app.py --direct --branch 46
```

| Métrica | Valor |
|---|---|
| SKUs únicos | **8.776** (soma de `countProducts` dos 16 departamentos = 11.755; dedup por id) |
| Com preço | 8.776 (100%) |
| Disponíveis na filial CT39 | 5.911 (2.865 sem estoque naquela loja) |
| Com desconto sobre a gôndola | **805** |
| Oferta do app (`DESCONTOU`) | 561 |
| Oferta do Cartão Tenda (`DESCONTOU_PLUS`) | 256 |
| Oferta só no campo legado `promotion` | **268** |
| **Ofertas que o coletor antigo perdia** | **537** (só existem em `promotions[]`) |
| Erros / páginas perdidas | 0 |

Exemplos: `Tira Manchas Vanish` gôndola 72,49 → app 30,99 → app+cartão 29,99;
`Pneu EVO 185/70 R14` 629,90 → 579,90; `Água Mineral Select 510ml` 0,99 → 0,89.

Ou seja: a coleta multi-loja não traria preço novo (preço é da rede), mas ler o campo certo **trouxe
537 ofertas que não existiam no catálogo**.

E a prova em escala de que o preço é da rede — três filiais coletadas de verdade
(`python scripts\verify_tenda_app.py --direct --region campinas --limit-stores 3`):

| Filial | SKUs | Com preço | Com desconto | Oferta app | Oferta cartão | Disponíveis |
|---|---|---|---|---|---|---|
| CT03 Amoreiras – Campinas (5) | 8.776 | 8.776 | 805 | 561 | 256 | 6.159 |
| CAMP Ceasa – Campinas (40) | 8.776 | 8.776 | 805 | 561 | 256 | 6.281 |
| CT39 Hortolândia (46) | 8.776 | 8.776 | 805 | 561 | 256 | 5.911 |
| **Divergências de preço** | — | — | **0** | **0** | **0** | 6.571 SKUs com estoque diferente |

### 13.8 O que não fazer no Tenda

* **Não** coletar as 45 filiais "porque tem a rota": o preço é idêntico, o volume é 45×.
* **Não** confiar em `availability`/`status` do produto: `available` é derivado do
  `inventory[]` da filial (mesma armadilha do `status` do Atacadão, §7.3).
* **Não** trocar `api.tendaatacado.com.br` por um proxy sem necessidade: a WAF (Azion) bloqueia o
  IP da Oracle, não o do dev — `scripts/verify_tenda_app.py --direct` ignora o `TENDA_PROXY_URL`
  local, e a constante do coletor continua honrando o proxy em produção.

---

## 14. Caso 4 — rotação de credenciais do Atacadão (31/10/2026): a auth saiu do app

### 14.1 Sintoma

```
app.catalog.atacadao.AtacadaoAppError: HTTP 400:
{"error":"invalid_grant","error_description":"Account disabled"}
```

### 14.2 Diagnóstico em 4 probes (5 minutos, sem emulador)

Rodando direto contra
`https://freyr.portal.atacadao.com.br/infosec/auth/v1/protocol/openid-connect/token`:

| Probe | Resposta | Leitura |
|---|---|---|
| `password` com as credenciais boas | `400 invalid_grant` / **Account disabled** | client autenticou e o usuário foi encontrado |
| `password` com **senha errada** | `400 invalid_grant` / Account disabled | a senha nem chega a ser avaliada → é a mesma conta desativada, não senha trocada |
| `client_credentials` | `401 unauthorized_client` | o client nunca teve service account |
| `password` **sem** `client_secret` | `401 unauthorized_client` | o `client_secret` antigo **ainda é válido** |

**Conclusão:** `client_id` e `client_secret` intactos; quem morreu foi o **usuário**
`kcc-ofertas-externo` (desativado no Keycloak). Como o app 13.429.1 usa a mesma conta, ele estaria
quebrado do mesmo jeito — sinal de que a Carrefour mudou o transporte na 13.429.2.

### 14.3 Diff estático do snapshot Dart (o método que resolveu)

```powershell
# 1. extrair lib/arm64-v8a/libapp.so de split_0.apk das duas versões
# 2. dump de strings + grep com contexto
python scripts\dart_strings.py dump "C:\Android\apk\Atacadao\x134292\lib\libapp.so" --out strings_134292.txt
python scripts\dart_strings.py grep strings_134292.txt "infosec" "client_credentials" "secure_proxy" "kobe_middleware"
```

Resultado do diff:

| Marcador em `libapp.so` | 13.429.1 | 13.429.2 |
|---|---|---|
| `/infosec/auth/v1/protocol/openid-connect/token` | presente | **ausente** |
| `client_credentials` | presente | **ausente** |
| `client_secret` = `CI4hKA5…` (literal) | presente | **ausente** |
| senha `WUzN!r2Jrr!…` (literal) | presente | **ausente** |
| `in_store_offers_secure_proxy_function` | ausente | **presente** |
| `in_store_offers_backoffice_client_secret` / `_password` | presentes | **ausentes** |

Ou seja: **o binário não guarda mais segredo nenhum** — procurar credencial nova no APK seria perda
de tempo. O que ele guarda é o *nome* do componente que passou a guardar a credencial. E a docstring
do parâmetro (os textos em português ficam em claro no snapshot, ao lado das chaves) entrega o
contrato inteiro:

> "Nome da Edge Function (em `kobe_middleware_base_url`) que guarda no servidor as credenciais da
> API de ofertas. Vazio = o app chama a API direto"

Com isso:

1. `scripts/dart_strings.py` + regex `^[a-z0-9]+(-[a-z0-9]+)+$` lista os identificadores em
   kebab-case → **`atacadao-in-store-offers`** e `atacadao-in-store-offers-hml`.
2. `scripts/fetch_remote_config.py --version 13.429.2` traz as duas chaves do middleware:
   `kobe_middleware_base_url = https://txgwdepbtdvfnubmtewb.supabase.co/functions/v1` e
   `kobe_middleware_api_key = <uuid>` (409 entradas no RC, 10 a mais que na 13.429.1; nenhuma delas
   traz segredo do Keycloak).

> **Lição:** o Remote Config continua sem segredo. O que mudou é que **não existe mais segredo no
> cliente**: a conta de serviço foi para o servidor da Carrefour (Supabase Edge Function). Quando o
> APK "perde" as credenciais, o próximo lugar a olhar é uma chave de config do tipo
> `*_proxy_function` / `*_edge_function`, não o tráfego.

### 14.4 Contrato da edge function (validado em 01/11/2026)

```
BASE = https://txgwdepbtdvfnubmtewb.supabase.co/functions/v1/atacadao-in-store-offers
GET  {BASE}/mobile/ofertas-backoffice/v1/...   +   header  x-api-key: <ATACADAO_APP_API_KEY>
```

O path do freyr entra **depois** do nome da função, com os mesmos parâmetros de antes
(`filialId`, `idFilial`, `pageNumber`, `pageSize`, `cityOrName`, …). Nada de `Authorization: Bearer`.

| Erro | Significado |
|---|---|
| `401 {"error":"Missing API key."}` | header ausente |
| `404 {"error":"Route not found."}` | path errado (nome da função + path do freyr) |
| `429 {"error":"Too many requests. Please try again later."}` | rate limit do proxy |

Rotas reconfirmadas (todas 200): `offer/status`, `home/categorias`, `home/banners`,
`produto/busca`, `vitrine/mobile/v2`, `busca-loja-via-cidade-nome/v2`.

### 14.5 O que a captura de tráfego mostrou (e por que não serviu)

O APK 13.429.2 foi patcheado e instalado no BlueStacks normalmente — os 4 patches ainda batem:
`processJailBroken`/`processCheckIssues`, 3 × `X-Android-Cert` (`E9/o`, `m9/c`,
`ConfigFetchHttpClient`), CA em `res/raw` e splash. Com proxy global + mitmproxy + reescrita do RC,
o mitmdump só viu tráfego **nativo** (Firebase/Facebook/Crashlytics) e o proxy reverso em `:9999`
não recebeu **nenhuma** requisição.

O motivo é estrutural, e dá para provar offline: a chave que decide o transporte
(`in_store_offers_secure_proxy_function`) **não existe no Remote Config** (o app usa o default do
código), então não há valor para reescrever — a chamada sai direto para a edge function. Somado a
isso, o `dart:io` continua ignorando o proxy do sistema. Sem root (iptables/WireGuard) não há como
interceptar o Dart, e como o binário não tem mais segredo, também não haveria o que capturar.
**A análise estática do snapshot foi o caminho certo.**

> Ajuste decorrente: `scripts/mitm_rewrite_rc.py` passou a reescrever **só** as chaves de transporte
> (`*api_url`, `*keycloak_login_url`, `*proxy_function`, `*edge_function`, `*gateway`) — antes ele
> trocava qualquer URL `in_store_offers_*`, o que quebrava links de compartilhamento de folheto e
> redirects de login VTEX.

### 14.6 Mudanças no código

- `app/catalog/atacadao.py`: sem Keycloak. `x-api-key` em todas as chamadas, retry com backoff para
  `429`/`5xx` (respeitando `Retry-After`) e `MAX_CONCURRENCY=4` por causa do rate limit do proxy.
- `scripts/atacadao_app_api.py`: cliente de referência atualizado (mesmo contrato).
- `scripts/probe_token_ttl.py` → **removido**; entrou `scripts/probe_app_api_health.py`.
- `scripts/dart_strings.py`: novo utilitário (dump/grep de strings do `libapp.so`) — foi ele que
  achou a chave e a docstring.
- Env: `ATACADAO_APP_CLIENT_ID/SECRET/USERNAME/PASSWORD` → `ATACADAO_APP_API_KEY` (e
  `ATACADAO_APP_BASE_URL` agora aponta para a edge function).
- Validação: loja 632 → **8.925 SKUs, 0 erros, ~10 s** (antes: ~2 min 20 s com o token do Keycloak).





