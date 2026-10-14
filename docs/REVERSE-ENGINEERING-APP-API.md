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
| App | `br.com.atacadao.b2c.app` â€” "Meu AtacadÃ£o" v13.429.1 (`versionCode 875917`) |
| Runtime | Flutter / Dart, **arm64-v8a apenas** |
| API de ofertas da loja fÃ­sica | `https://freyr.portal.atacadao.com.br` |
| AutenticaÃ§Ã£o | Keycloak (realm `R-Mobile_Backend_Token-KC`) via Apigee, em `skadi-prod` |
| Grant | `password` (client "externo" de serviÃ§o, sem MFA, sem vÃ­nculo de device) |
| Validade do token | 3.600 s (`expires_in`), refresh 1.800 s |
| Cobertura | 389 lojas; o `idFilial` **Ã©** o nÃºmero da loja fÃ­sica (ex.: 632 = HortolÃ¢ndia) |

Credenciais (ver seÃ§Ã£o 9 para o que fazer quando mudarem):

```
client_id     = OfertaMobile-TokenAuth
client_secret = CI4hKA5gdaXjDLm52Mz68pXOhIhiUvNA
username      = kcc-ofertas-externo
password      = WUzN!r2Jrr!8BTFteoW3J
scope         = R-OfertasMobile-externo
aud           = R-OfertasMobile-KC
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
| `probe_app_api_shape.py` | descobre limites de paginaÃ§Ã£o e o shape do catÃ¡logo por loja |
| `probe_departments.py` | prova de completude: departamentos devem somar o total geral |
| `probe_token_ttl.py` | TTL/refresh/claims da credencial de app (AtacadÃ£o) |
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
password=WUzN%21r2Jrr%218BTFteoW3J
client_id=OfertaMobile-TokenAuth
client_secret=CI4hKA5gdaXjDLm52Mz68pXOhIhiUvNA
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
$py = "C:\Android\mitm-venv\Scripts\python.exe"

& $py scripts\probe_token_ttl.py            # TTL, refresh, claims
& $py scripts\list_app_stores.py --region   # 43 lojas da RMC -> app_stores.json
& $py scripts\probe_app_api_shape.py 632    # limites de pageSize / varredura completa
& $py scripts\probe_departments.py 632      # departamentos x catÃ¡logo (deve fechar em 0)
& $py scripts\validate_app_price.py 632     # preÃ§o do produto do usuÃ¡rio na loja 632
& $py scripts\dump_store_offers.py 632      # vitrines (aplica sÃ³ com oferta ativa)
```

Se `probe_departments.py` fechar em 0 e `validate_app_price.py` mostrar os trÃªs preÃ§os, **a
credencial estÃ¡ boa**.

---

## 9. Playbook: as credenciais mudaram. E agora?

### 9.1 DiagnÃ³stico pelo cÃ³digo de erro

| Sintoma | Causa provÃ¡vel | AÃ§Ã£o |
|---|---|---|
| `401 {"error":"invalid_client"}` | `client_secret` ou `client_id` trocados/desabilitados | Recapturar (9.2) |
| `410/401 {"error":"invalid_grant"}` | senha do usuÃ¡rio `kcc-ofertas-externo` alterada | Recapturar (9.2); talvez seja um usuÃ¡rio novo |
| `401 unauthorized_client` em `grant_type=client_credentials` | **normal** â€” esse client nÃ£o tem service account | Use `password` |
| `403` com HTML/JSON do Apigee | rota bloqueada/regra mudou | Revalidar as rotas (7.1); pode ter subido versÃ£o nova da API |
| `404` em rota que funcionava | versÃ£o da API mudou (`v1` â†’ `v2`) | Ver 9.3 |
| Todos os preÃ§os `null` | token vÃ¡lido, loja sem ofertas ou `idFilial` errado | `probe_departments.py` |

### 9.2 Recaptura rÃ¡pida (o caminho curto)

Tudo o que Ã© preciso jÃ¡ estÃ¡ instalado e o APK patcheado jÃ¡ estÃ¡ no BlueStacks. Passos:

1. Suba o mitmproxy e o proxy reverso (seÃ§Ã£o 4.2a) e confirme o proxy global do guest.
2. Abra o app "Meu AtacadÃ£o" â†’ tela de ofertas da loja (o app refaz o login do Keycloak na
   primeira chamada autenticada).
3. `scripts/show_capture.py` â†’ pegue `client_id`, `client_secret`, `username`, `password`.
4. Atualize as variÃ¡veis de ambiente/segredos do projeto (nÃ£o edite constante no cÃ³digo â€” veja
   abaixo) e rode `probe_token_ttl.py`.
5. Rode `probe_departments.py 632` para reconfirmar o contrato.

### 9.3 Se o app subir de versÃ£o

1. Baixe o novo XAPK e confira `versionCode`/ABIs (`aapt2 dump badging`).
2. Repita a Fase 4. Os alvos dos patches (smali de root detection, `X-Android-Cert`, splash)
   podem mudar de arquivo â€” os scripts localizam por **padrÃ£o de string**, nÃ£o por nome de arquivo,
   justamente para sobreviver a isso.
3. Rode o app por alguns minutos com a captura ligada e faÃ§a `diff` das rotas observadas contra a
   tabela 7.1. Rota nova = atualizar `scripts/atacadao_app_api.py` e o coletor.

### 9.4 Onde NÃƒO colocar credencial

Nada de `client_secret` hardcoded em mÃ³dulo de produÃ§Ã£o. O coletor lÃª de ambiente:

```
ATACADAO_APP_BASE_URL      (default https://freyr.portal.atacadao.com.br)
ATACADAO_APP_CLIENT_ID
ATACADAO_APP_CLIENT_SECRET
ATACADAO_APP_USERNAME
ATACADAO_APP_PASSWORD
```

Os `scripts/` de RE mantÃªm os valores observados como default, o que Ã© aceitÃ¡vel porque sÃ£o
ferramentas de investigaÃ§Ã£o â€” mas rotacione e migre para `.env`/secret manager antes de qualquer
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



