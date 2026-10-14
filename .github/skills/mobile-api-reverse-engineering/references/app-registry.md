# Registro de apps mapeados

Catálogo do acervo de engenharia reversa. **Ao mapear um app novo, acrescente uma linha aqui e
detalhe o operacional na memória do repo.** O que é genérico (técnica, armadilha de plataforma)
vai para `toolchain.md` / `capture-playbook.md`, não para cá.

| App | Package / host | Autenticação | Coletor no repo | Operacional (memória) |
|---|---|---|---|---|
| **Meu Atacadão** | `br.com.atacadao.b2c.app` → `freyr.portal.atacadao.com.br` | Keycloak `password` grant, client `OfertaMobile-TokenAuth`, token 3600 s | `app/catalog/atacadao.py` (API do app) | `/memories/repo/atacadao-app-api-and-flyers.md` |
| **Spani Atacadista** | `br.com.spanionline.appvendas` (Capacitor/Angular) → `services-beta.vipcommerce.com.br/api-admin/v1` | login anônimo de loja (`loja` + `lojaAuthJWT`), org 67, domainKey `spanionline.com.br` | `app/catalog/vipcommerce.py` (multi-loja: `collect_all`) | `/memories/repo/new-sources-vipcommerce-convertize.md` |
| Assaí | API autenticada | sessão/credencial (a confirmar) | `app/catalog/assai.py` (`assai-authenticated-api`) | `/memories/repo/new-sources-vipcommerce-convertize.md` |
| Tenda | `api.tendaatacado.com.br` | pública + **proxy** (WAF Azion bloqueia IP de datacenter) | `app/catalog/tenda.py` (`tenda-public-api`) | `/memories/repo/tenda-proxy-tailscale.md` |
| Davitta | API do app (`davita-mobilesim-api`) | a confirmar | `app/catalog/davita.py` | — |
| Max Atacadista | API/VTEX pública | — | `app/catalog/maxatacadista.py` | — |
| São Vicente | Demandware (`saovicente-demandware-api`) | pública | `app/catalog/saovicente.py` | — |
| Savegnago | VTEX (`savegnago-vtex-api`) | pública | `app/catalog/savegnago.py` | — |
| GoodBom | API (`goodbom-api`) | pública | `app/catalog/goodbom.py` | — |
| Arena Atacado | Demandware (`arena-api`) | pública | `app/catalog/arena.py` | — |
| Pague Menos | — | a confirmar | `app/catalog/paguemenos.py` | — |
| VIP Commerce / Convertize | plataforma de e-commerce (white-label) | a confirmar | `app/catalog/vipcommerce.py` | `/memories/repo/new-sources-vipcommerce-convertize.md` |

> O `provider_type` de cada coletor está em `app/catalog/persistence.py` — é a fonte de verdade
> sobre qual canal cada fonte usa hoje.

## Ficha do caso resolvido: Meu Atacadão

- **Superfície:** API de ofertas de loja física (`freyr`), gateway `skadi-prod` para Keycloak.
- **Segredo obtido por:** Remote Config reescrito → proxy reverso HTTP → `POST …/token` em texto claro.
- **Bloqueios encontrados e resolvidos:** app arm64-only (BlueStacks Pie64), root detection
  (`com.w3conext.jailbreak_root_detection`), perda de Remote Config pós-reassinatura
  (`X-Android-Cert`), splash do apktool (`@null`), Flutter ignorando o proxy.
- **Cobertura:** 389 lojas; `idFilial` = número da loja. Catálogo de uma loja ≈ 8.800 SKUs,
  varredura completa ≈ 184 requisições (`pageSize` máx. 50, 18 departamentos que particionam o
  catálogo exatamente).
- **Faixas de preço:** `preco` (varejo/atacado) · `finalPrice` (oferta do app) · `finalCardPrice`
  (app + cartão). Bate com o encarte físico da loja.
- **Validado em:** Hortolândia (632), 2026-10-13, contra o encarte "Ofertas Atacadão" 13–19/10/2026.
- **Detalhamento completo:** `docs/REVERSE-ENGINEERING-APP-API.md`.

## Anatomia de um registro novo

Copie este bloco para a memória do repo ao mapear um app:

```markdown
# <App> — API do app (data)

## Credenciais
- host base:
- client_id / client_secret / username / password:
- TTL do token:            # expires_in; refresh suportado?

## Rotas
- METODO /path (params obrigatórios) -> payload resumido

## Semântica de preço
- campo X = <o que significa na gôndola>

## Bloqueios encontrados
- ...

## Como recapturar se rotacionar
- ...

## Validação
- fonte independente, número observado
```
