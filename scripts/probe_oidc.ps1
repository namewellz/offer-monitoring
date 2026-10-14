$ErrorActionPreference = 'Continue'
$urls = @(
  "https://freyr.portal.atacadao.com.br/.well-known/openid-configuration",
  "https://freyr.portal.atacadao.com.br/infosec/auth/v1/.well-known/openid-configuration",
  "https://freyr.portal.atacadao.com.br/infosec/auth/v1/protocol/openid-connect/.well-known/openid-configuration",
  "https://skadi-prod.portal.atacadao.com.br/",
  "https://skadi-prod.portal.atacadao.com.br/.well-known/openid-configuration",
  "https://skadi-prod.portal.atacadao.com.br/realms/master/.well-known/openid-configuration",
  "https://skadi-prod.portal.atacadao.com.br/realms/infosec/.well-known/openid-configuration",
  "https://skadi-prod.portal.atacadao.com.br/auth/realms/infosec/.well-known/openid-configuration"
)
foreach ($u in $urls) {
    try {
        $r = Invoke-WebRequest -Uri $u -UseBasicParsing -TimeoutSec 20 -Headers @{ "User-Agent" = "okhttp/4.12.0"; "Accept" = "application/json" }
        $b = $r.Content; if ($b.Length -gt 500) { $b = $b.Substring(0, 500) }
        Write-Output "OK  $u => $($r.StatusCode) :: $b"
    } catch {
        $code = $_.Exception.Response.StatusCode.value__
        Write-Output "ERR $u => $code"
    }
}
