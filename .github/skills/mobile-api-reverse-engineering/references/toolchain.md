# Toolchain — ambiente Windows

Tudo abaixo está instalado e verificado na máquina de desenvolvimento
(`DESKTOP-0LFQFRU`, Windows 11 25H2). Em máquina nova, reproduza esta tabela.

| Ferramenta | Caminho | Para quê |
|---|---|---|
| Android SDK | `C:\Android\sdk` | `aapt2`, `zipalign`, `apksigner`, `platform-tools` |
| build-tools | `C:\Android\sdk\build-tools\34.0.0` | `aapt2`, `zipalign`, `apksigner` |
| BlueStacks 5 | `C:\Program Files\BlueStacks_nxt` | device que roda o app |
| HD-Adb | `C:\Program Files\BlueStacks_nxt\HD-Adb.exe` | **sempre este adb** (v41) |
| JDK 21 | `C:\Program Files\Eclipse Adoptium\jdk-21.0.12.8-hotspot` | apktool / apksigner |
| apktool | `C:\Android\apktool\apktool.jar` | decode/build do APK |
| keystore debug | `C:\Android\apktool\debug.keystore` | `storepass=android`, `alias=androiddebugkey`, `keypass=android` |
| OpenSSL | `C:\Program Files\Git\usr\bin\openssl.exe` | CA do mitmproxy |
| venv RE | `C:\Android\mitm-venv` | `mitmproxy`, `pymupdf`, `pypdf` |
| venv projeto | `.venv` | `httpx`, SQLAlchemy, … |
| capturas | `C:\Android\capture` | logs, JSONs, PDFs de encarte |

## ADB

```powershell
$adb = "C:\Program Files\BlueStacks_nxt\HD-Adb.exe"
& "C:\Android\sdk\platform-tools\adb.exe" kill-server        # evita conflito de versão
& $adb connect 127.0.0.1:5555
& $adb -s 127.0.0.1:5555 shell getprop ro.product.cpu.abilist
& $adb -s 127.0.0.1:5555 install-multiple base.apk split_0.apk split_1.apk
& $adb -s 127.0.0.1:5555 shell pm list packages | Select-String <pkg>
& $adb -s 127.0.0.1:5555 shell dumpsys package <pkg> | Select-String primaryCpuAbi
```

Helpers: `scripts/bs_adb.ps1`, `scripts/android_setup.ps1`, `scripts/android_avd.ps1`,
`scripts/install_apk.ps1`, `scripts/bs_capture.ps1`.

## BlueStacks: habilitar ADB e root

Arquivo: `C:\ProgramData\BlueStacks_nxt\bluestacks.conf`

```ini
bst.enable_adb_access="1"
bst.enable_adb_remote_access="1"
bst.feature.rooting="1"
bst.instance.<Instancia>.enable_root_access="1"
```

Regras não negociáveis:

1. **Mate o BlueStacks antes de editar** (ele reescreve o `.conf` ao encerrar).
2. Grave **UTF-8 sem BOM** (`New-Object Text.UTF8Encoding($false)`). BOM → *"Failed to read
   configuration file"*.
3. `[IO.File]::ReadAllText($p, [Text.Encoding]::UTF8)` **já remove** o BOM. Não remova de novo —
   você apaga o primeiro caractere real do arquivo.
4. A instalação via linha de comando não aceita `/S` (o micro-instalador WPF interpreta `/S` como
   caminho `C:\S`). Instale pela GUI, elevado.

Scripts: `scripts/bs_inspect_conf.ps1`, `scripts/bs_fix_conf.ps1`, `scripts/bs_fix_conf2.ps1`,
`scripts/bs_enable_root_adb.ps1`, `scripts/install_bluestacks.ps1`.

## Exigir tradução ARM64

Instância **Pie64** (Android 9 / API 28) é a que funciona. Confirmar:

```powershell
& $adb -s 127.0.0.1:5555 shell getprop ro.product.cpu.abilist      # inclui arm64-v8a
& $adb -s 127.0.0.1:5555 shell dumpsys package <pkg> | Select-String primaryCpuAbi
```

Se o app for arm64-only e o `primaryCpuAbi` não resolver, o app não abre.

## APK: inspecionar, decomplar, patchear, assinar

```powershell
$aapt2 = "C:\Android\sdk\build-tools\34.0.0\aapt2.exe"
$java  = "C:\Program Files\Eclipse Adoptium\jdk-21.0.12.8-hotspot\bin\java.exe"

& $aapt2 dump badging app.apk | Select-String "package:|native-code|sdkVersion|label"
& $java -jar C:\Android\apktool\apktool.jar d -f -s -o C:\Android\apktool\base_src app.apk
& $java -jar C:\Android\apktool\apktool.jar b C:\Android\apktool\base_src -o modded.apk

# assinar (obrigatório: o pacote modificado perde a assinatura original)
$bt = "C:\Android\sdk\build-tools\34.0.0"
& "$bt\zipalign.exe" -f -p 4 modded.apk aligned.apk
& "$bt\apksigner.bat" sign --ks C:\Android\apktool\debug.keystore `
    --ks-pass pass:android --key-pass pass:android --ks-key-alias androiddebugkey out.apk
& "$bt\apksigner.bat" verify --print-certs out.apk
```

`-s` (`--no-src`) mantém `.dex` sem desmontar smali — rápido, mas inútil quando você precisa
**patchear** smali. Para patchear, decomple sem `-s`.

Fingerprint do certificado (necessário para o patch de `X-Android-Cert`):

```powershell
& "$bt\apksigner.bat" verify --print-certs app.apk |
    Select-String "SHA-1"      # converter para hex maiúsculo sem ':' quando injetar
```

## Firewall (serviços locais)

Shells não são elevados por padrão; use UAC:

```powershell
Start-Process powershell -Verb RunAs -ArgumentList '-Command',
  "New-NetFirewallRule -DisplayName mitm8080 -Direction Inbound -Protocol TCP -LocalPort 8080 -Action Allow"
```

## Ferramentas do repositório (RE)

| Script | Para que serve |
|---|---|
| `scripts/scan_app_bundle.py` | bundle de app híbrido: hosts, rotas (com template literals), chaves de config |
| `scripts/grep_bundle.py` | grep com contexto em bundle minificado |
| `scripts/probe_app_api_shape.py` | limites de paginação e shape do payload |
| `scripts/probe_departments.py` | prova de completude (soma por categoria == total) |
| `scripts/probe_token_ttl.py` | TTL, refresh e claims de um token de app |
| `scripts/list_app_stores.py` | registry das lojas da rede via API do app |
| `scripts/validate_app_price.py` | consulta um produto e mostra as faixas de preço |
| `scripts/dump_store_offers.py` | pagina vitrines/ofertas de uma loja |
| `scripts/compare_store_prices.py` | compara preço do mesmo produto entre lojas |
| `scripts/find_catalog_product.py` | acha um produto no catálogo coletado e imprime as faixas |
| `scripts/atacadao_app_api.py` | cliente de referência (só `urllib`) de uma API de app |
| `scripts/patch_apk.py` + `scripts/build_patched_apk.ps1` | patch/reassinatura do APK |
| `scripts/ui_taps.py` | automação de UI via uiautomator |
| `scripts/mitm_capture.py`, `scripts/mitm_rewrite_rc.py`, `scripts/api_logger_proxy.py` | captura, reescrita de Remote Config, proxy reverso que loga em claro |

## Validar um coletor novo contra o banco do compose

O Postgres do `docker-compose.yml` não publica porta e o host não resolve `postgres`. Rode dentro
da rede do compose, montando o repositório e reaproveitando a imagem já construída:

```powershell
docker run --rm --network offer-monitoring_default `
  -v "c:\fonts\offer-monitoring:/app" -w /app `
  -e DATABASE_URL="postgresql+psycopg://flyer:flyer@postgres:5432/flyer" `
  -e PYTHONIOENCODING=utf-8 offer-monitoring-api python -m app.cli <comando>
```

## Armadilhas de plataforma (genéricas)

| Sintoma | Causa | Correção |
|---|---|---|
| `adb: connection reset` após `adb root` | `adb root` reinicia o adbd | reconecte; espere o device voltar |
| Dois `adb server` brigando | versões diferentes de adb | mate um server antes de usar o outro |
| App crasha logo após `apktool b` | recurso XML/bitmap quebrado na recompilação | inspecione o XML gerado e substitua por algo trivial |
| App perde serviços Google após reassinar | identidade do certificado validada server-side | reinjete o fingerprint original do certificado |
| `su` pendura no BlueStacks | implementação incompleta de root | prefira patch no app em vez de confiar em `su` |
| Coordenadas de toque erradas | `input tap` usa um espaço de coordenadas fixo (ex.: retrato 900x1600) independente da rotação | converta antes de enviar |
