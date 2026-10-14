$ErrorActionPreference = 'Continue'
$base = "https://freyr.portal.atacadao.com.br"
$urls = @(
  "$base/",
  "$base/mobile/ofertas-backoffice/v1/",
  "$base/mobile/ofertas-backoffice/v1/busca-loja-via-cep/v2?cep=13184-668",
  "$base/mobile/ofertas-backoffice/v1/busca-loja-via-cidade-nome/v2?cidade=Hortolandia",
  "$base/mobile/ofertas-backoffice/v1/busca-loja-via-geolocation/v2?lat=-22.87&long=-47.21",
  "$base/mobile/ofertas-transacional/v1/vitrine/mobile/v2",
  "$base/mobile/ofertas-transacional/v1/vitrine/mobile/v2?cep=13184-668",
  "$base/mobile/ofertas-backoffice/v1/vitrine/mobile/v2?cep=13184-668"
)
foreach ($u in $urls) {
    try {
        $r = Invoke-WebRequest -Uri $u -UseBasicParsing -TimeoutSec 25 -Headers @{ "User-Agent" = "okhttp/4.12.0"; "Accept" = "application/json" }
        $b = $r.Content
        if ($b.Length -gt 400) { $b = $b.Substring(0, 400) }
        Write-Output "OK  $u => $($r.StatusCode) :: $b"
    } catch {
        $code = $_.Exception.Response.StatusCode.value__
        $body = ""
        try { $resp = $_.Exception.Response; if ($resp) { $sr = New-Object System.IO.StreamReader($resp.GetResponseStream()); $body = $sr.ReadToEnd(); if ($body.Length -gt 250) { $body = $body.Substring(0, 250) } } } catch {}
        Write-Output "ERR $u => $code :: $body"
    }
}
