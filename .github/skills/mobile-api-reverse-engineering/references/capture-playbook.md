# Playbook de captura de tráfego de app móvel

## 1. Árvore de decisão

```
É app híbrido (WebView)?   <-- cheque ANTES de tudo
├─ Sim (sem 'native-code' no dump badging)
│    └─ O frontend é JS legível: scanner de bundle resolve host/rotas/credenciais.
│       Não precisa de emulador nem de proxy. Só capture se houver assinatura/cripto no cliente.
└─ Não (nativo/Flutter) → a pergunta abaixo

O app passa pelo proxy?
├─ Sim, tudo aparece no mitmproxy
│    └─ Capture normalmente. Próximo problema: pinning (TLS) e body cifrado.
├─ Só SDKs nativos aparecem (Firebase, Facebook, Crashlytics)
│    └─ O runtime do app ignora o proxy do sistema. → seção 2
└─ Nada aparece
     ├─ O proxy do sistema não está configurado / app usa DNS próprio
     ├─ CA não é confiável para o app (targetSdk ≥ 24 ignora CA de usuário) → embuta a CA no APK
     └─ TLS pinning → patch ou instrumentation
```

**Primeiro diagnóstico:** rode o app por 2 minutos e liste os hosts capturados. Se você só vê
telemetria de SDK e nenhuma chamada de negócio, você está no caso "runtime ignora proxy" — e a
solução **não** é pinning, é redirecionamento.

## 2. O caso Flutter/Dart (e como resolver)

O `dart:io`/`HttpClient` do Flutter **não consulta o proxy do sistema**. Consequência prática:
mitmproxy só vê o SDK nativo; nenhuma chamada do app.

Receita que funcionou:

1. **Descubra como o app obtém as URLs base.** No caso Atacadão: **Firebase Remote Config**,
   buscado por HTTP nativo → logo, interceptável. Chaves relevantes: `*_api_url`, `*_base_api_url`,
   `*_keycloak_login_url`, além das variantes `hml_*`.
2. **Reescreva a resposta do RC** (addon do mitmproxy) trocando essas chaves pelo endereço do seu
   proxy reverso local, em HTTP puro. Modelo: `scripts/mitm_rewrite_rc.py`.
3. **Suba um proxy reverso HTTP** que registra tudo e encaminha para as origens reais:
   `scripts/api_logger_proxy.py` (roteia por prefixo de path entre os hosts reais, grava
   `token_requests.jsonl`).
4. **Force o refetch do RC** (reabra o app). A partir daí, todo o tráfego do Dart chega em texto
   claro no seu log.

**Por que não frida/objection?** Porque o problema não é pinning. O app já confia na CA embutida;
ele só não usa o proxy. Redirecionar é mais estável e não exige instrumentação em runtime (que
quebra a cada atualização).

### Como saber se o RC é o vetor
- `strings` no `libapp.so` mostra nomes de chaves de configuração junto das URLs.
- O app chama um endpoint de config no boot (Firebase RC, `/config`, `/bootstrap`) antes de
  qualquer chamada de negócio.
- Ao mudar um valor no servidor de config, o comportamento do app muda.

### Cuidado com o cert identity
Se o app reassinado perde as configurações remotas (todas as chaves voltam ao default), o provedor
de config está validando a identidade do certificado. Reinjete o fingerprint original no header
esperado (`X-Android-Cert` no caso Firebase/Android).

## 3. CA confiável no app

Ordem de preferência:

1. **Usuário/system CA no device** — mais simples, mas `targetSdk ≥ 24` ignora CA de usuário para
   tráfego do app.
2. **CA embutida no APK** (`res/raw/<ca>.pem` + `network_security_config.xml` apontando para ela) —
   mais robusto, sobrevive a mudanças de sistema. Usado no caso Atacadão.
3. **Patch de pinning** — último recurso.

Sempre valide: abra o app e confirme que uma requisição de negócio aparece no mitmproxy **com corpo
legível**. Se aparecer `Client TLS handshake failed` ou certificado rejeitado, é CA/pinning.

## 4. Bloqueios de execução

### Root detection
Sintoma: tela de "dispositivo não suportado" / app fecha no launch. Causas comuns checadas pelo app:
`ro.debuggable`, `ro.secure`, `ro.build.tags=test-keys`, `su` no PATH, `/system/xbin/su`, BusyBox,
apps de root instalados.

Estratégia: localize a lib (nomes típicos: `rootbeer`, `jailbreak`, `root_detection`, `safetynet`)
e **patcheie o retorno** das funções de checagem. Sempre por padrão de string — nomes de arquivo
smali mudam a cada release.

### Integridade / assinatura
Sintoma: app funciona, mas algum serviço server-side nega (config remota vazia, login recusado).
Causa: o backend espera a identidade do certificado original. Reinjete o fingerprint.

### Recursos quebrados após recompilar
`apktool b` pode gerar XML degenerado (ex.: `<bitmap android:src="@null">`) e causar
`Resources$NotFoundException` no launch. Substitua por um recurso trivial (`@android:color/white`).

## 5. Descobrir rotas desconhecidas

Nunca chute. Ordem:

1. `strings` no binário nativo: paths costumam aparecer como literais.
2. Tráfego na tela de origem: siga o fluxo (home → categoria → produto → busca).
3. Automação de UI para chegar na tela: `scripts/ui_taps.py`
   (`dump`, `tap <texto>`, `tapxy x y`, `screen`, `swipe`).
4. Se um path retorna 404 mas o app o usa, provavelmente é **outro host** ou tem **prefixo de
   versão** diferente — compare o request completo (host + path + query), não só o path.

## 6. Mapear parâmetros obrigatórios e limites

- Remova **um** parâmetro por vez: erro explícito (`{"message":"X é um campo obrigatório"}`) é
  documentação de graça.
- Teto de paginação: teste `pageSize` crescente (10 → 25 → 50 → 51 → 100). O erro informa o limite
  (`"pageSize deve ser no máximo 50"`).
- Valores default de flag: teste `true`/`false` e compare os totais.
- **Prova de completude:** se as categorias somam exatamente o total geral, sua varredura cobre
  100% do catálogo. Se não fecham, há itens fora das categorias — trate-os à parte.

## 7. Higiene de coleta

- Concorrência baixa (≤ 6), backoff exponencial em erro/servidor.
- Cache de token com margem (renove antes de expirar; trate 401 com re-auth e **um** retry).
- Registre latência e volume: ajuda a dimensionar a varredura e detectar degradação.
- Não colete mais do que o caso exige ao explorar; a varredura completa é para o passo final.
