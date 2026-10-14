$ErrorActionPreference = 'Continue'
$urls = @(
  "https://skadi-prod.portal.atacadao.com.br/infosec/auth/v1/protocol/openid-connect/token",
  "https://freyr.portal.atacadao.com.br/infosec/auth/v1/protocol/openid-connect/token",
  "https://freyr.portal.atacadao.com.br/mobile/ofertas-backoffice/v1/infosec/auth/v1/protocol/openid-connect/token"
)
$body = "grant_type=client_credentials&client_id=OfertaMobile-TokenAuth"
foreach ($u in $urls) {
    try {
        $r = Invoke-WebRequest -Uri $u -Method Post -Body $body -ContentType "application/x-www-form-urlencoded" -UseBasicParsing -TimeoutSec 30 -Headers @{ "User-Agent" = "okhttp/4.12.0" }
        Write-Output "OK  $u => $($r.StatusCode) :: $($r.Content.Substring(0, [Math]::Min(400, $r.Content.Length)))"
    } catch {
        $code = $_.Exception.Response.StatusCode.value__
        $b = ""
        try { $resp = $_.Exception.Response; if ($resp) { $sr = New-Object System.IO.StreamReader($resp.GetResponseStream()); $b = $sr.ReadToEnd(); if ($b.Length -gt 400) { $b = $b.Substring(0, 400) } } } catch {}
        Write-Output "ERR $u => $code :: $b"
    }
}
