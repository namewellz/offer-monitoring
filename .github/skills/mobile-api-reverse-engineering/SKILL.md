---
name: mobile-api-reverse-engineering
description: 'Workflow para recuperar a API interna de um app móvel (Android/iOS) e transformá-la em coletor reproduzível: captura de tráfego de app Flutter/Dart e nativo, bypass de root detection e X-Android-Cert, Remote Config rewrite, APK patching com apktool, BlueStacks com ARM64, mitmproxy, extração de client_id/client_secret, montagem de cliente Python, validação contra encarte. USE FOR: nova fonte de dados vinda de app, credenciais rotacionadas, app arm64-only em Windows, rota de API desconhecida.'
argument-hint: 'App e dado desejado (ex.: "credenciais e rotas do app do Tenda")'
---

# Reverse engineering de API de app móvel

Produzir um **cliente HTTP reproduzível** para a API interna de um app de varejo, com
credenciais, rotas e semântica de campos verificadas. O caso completo já resolvido (Atacadão)
está em `docs/REVERSE-ENGINEERING-APP-API.md` — use-o como referência concreta de cada etapa.

## Quando usar

- Um dado (preço de gôndola, oferta de loja física) só existe no app, não no site.
- A credencial de um app já mapeado parou de funcionar (rotação).
- Um app novo entra no escopo e precisa do mesmo tratamento.
- Uma rota de API precisa ser descoberta/confirmada.

## Decisões rápidas

| Situação | Caminho |
|---|---|
| App é nativo (OkHttp, Retrofit) | Proxy + CA resolve quase tudo. Vá direto ao passo 3. |
| App é Flutter/Dart | O `dart:io` **ignora o proxy do sistema**. Precisa redirecionar as URLs base (passo 4). |
| App é React Native | Igual a nativo para `fetch` (usa o stack nativo), mas checar `okhttp`/`NSURLSession`. |
| App recusa rodar (root/emulador) | Passo 5: patch de root detection. |
| App é arm64-only e você está em Windows x86 | Passo 2: BlueStacks Pie64 (tradução ARM64). |
| Rota desconhecida | Não chute: instrumente a captura e **navegue** até a tela. Passo 6. |
| Segredo não aparece em `strings` | Ele vem por config remota (Firebase RC, API de bootstrap). Passo 4. |

## Procedimento

### 1. Reconhecimento estático
```powershell
& "C:\Android\sdk\build-tools\34.0.0\aapt2.exe" dump badging "<pkg>.apk" |
    Select-String "package:|native-code|sdkVersion"
```
- **Sem linha `native-code` ⇒ app híbrido** (WebView: Capacitor/Cordova/Ionic). O frontend inteiro
  é JavaScript legível: rode `scripts/scan_app_bundle.py <apktool-src> --show-routes --show-config`
  e `scripts/grep_bundle.py`. Isso costuma entregar host, org, rotas e credencial de sessão
  **sem emulador, sem proxy e sem patch** — sempre faça isso antes de montar o ambiente caro.
- `native-code` decide a estratégia de emulação.
- `strings`/regex nas libs nativas: URLs, `Bearer`, `client_secret`, `Authorization`, nomes de SDK.
  Em Flutter, **toda a lógica está em `lib/<abi>/libapp.so`** — é lá que as URLs aparecem.

### 2. Rodar o app
Windows: BlueStacks 5 instância `Pie64` (ABIs incluem `arm64-v8a`). Comandos em
[references/toolchain.md](./references/toolchain.md).

### 3. Captura de tráfego
mitmproxy + CA confiável no device. Valide **quais** hosts aparecem antes de concluir qualquer
coisa. Detalhes e o truque do Remote Config em
[references/capture-playbook.md](./references/capture-playbook.md).

### 4. Redirecionar a camada que ignora o proxy
Se o runtime do app ignora o proxy do sistema (Flutter/Dart é o caso clássico), encontre **como o
app descobre as URLs base** (Remote Config, endpoint de bootstrap, arquivo de config). Se for
buscado por HTTP nativo, reescreva a resposta para apontar para um **proxy reverso HTTP puro** que
você controla — assim os requests do runtime chegam em texto claro. Modelo:
`scripts/mitm_rewrite_rc.py` + `scripts/api_logger_proxy.py`.

### 5. Contornar bloqueios de execução
- Root/jailbreak detection → patch smali/binário, por **padrão de string**.
- App reassinado perdendo serviços Google/Firebase → restaurar identidade do certificado
  (`X-Android-Cert`) com o fingerprint original.
- Splash/resource quebrando depois do `apktool b` → corrigir o XML gerado.
Referência executável: `scripts/patch_apk.py`, `scripts/build_patched_apk.ps1`.

### 6. Induzir e capturar a chamada
Navegue até a funcionalidade com a captura ligada. Automação de UI quando a tela resistir
(`scripts/ui_taps.py`). Registre o **request inteiro** (headers + body), não só o path.

### 7. Extrair o contrato
Para cada rota: método, host, path, obrigatoriedade de cada query param (teste removendo um por
vez — parâmetro obrigatório devolve 400 com mensagem explícita), limites de paginação, e a
**semântica de cada campo de preço**. Descubra o teto de `pageSize` testando valores crescentes.

### 8. Cliente mínimo + token
- Prefira biblioteca padrão (`urllib`) para o cliente de investigação — zero dependência.
- Cache de token com margem; renova em 401 automaticamente.
- Concorrência baixa (≤ 6) e backoff. Nunca esgote a API.

### 9. Validar contra fonte independente
Encarte/folheto oficial, site, ou outro canal. Sem número de validação, o trabalho não acabou.

### 10. Documentar e registrar
Memória do repo (`/memories/repo/<app>-app-api-and-flyers.md`) + `docs/` + só o genérico volta
para esta skill.

## Regras de ouro

- **Rota não se adivinha.** Se não viu no tráfego, não existe.
- **Um parâmetro obrigatório ausente devolve erro explícito** — use isso a seu favor para mapear.
- **Partição fechada é prova de varredura completa.** Some os totais por categoria e compare com o
  total geral; diferença 0 = você pegou o catálogo inteiro.
- **Patch por padrão, nunca por nome de arquivo.** Atualização de app muda smali; string-chave
  costuma sobreviver.
- **Segredo só em env/secret manager** no código de produção.

## Referências

- [references/toolchain.md](./references/toolchain.md) — comandos do ambiente Windows (SDK,
  BlueStacks, apktool, mitmproxy, assinatura) e armadilhas de plataforma.
- [references/capture-playbook.md](./references/capture-playbook.md) — árvore de decisão da
  captura, o problema do Dart/proxy, reescrita de Remote Config, root detection.
- [references/app-registry.md](./references/app-registry.md) — apps já mapeados, onde estão as
  credenciais e o que já se sabe sobre cada um.
- `docs/REVERSE-ENGINEERING-APP-API.md` — estudo de caso completo (Meu Atacadão) com todas as
  rotas, evidências de validação e catálogo de pitfalls.
