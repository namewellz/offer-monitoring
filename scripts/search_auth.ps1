$f = "$env:TEMP\atacadao-xapk\libapp_strings.txt"
$lines = Get-Content $f
$out = New-Object System.Collections.Generic.List[string]
foreach ($kw in @("OfertaMobile-TokenAuth", "kcc-ofertas-externo", "skadi", "realms", "openid-connect", "grant_type", "client_credentials", "client_secret", "password", "OfertasMobilesDev", "freyr", "tyr.")) {
    $m = $lines | Select-String -Pattern $kw -SimpleMatch | ForEach-Object { $_.Line }
    if ($m) { $out.Add("===== $kw ($($m.Count)) ====="); $m | Sort-Object -Unique | Select-Object -First 30 | ForEach-Object { $out.Add("  $_") } }
}
# context around the client id / username
foreach ($kw in @("OfertaMobile-TokenAuth", "kcc-ofertas-externo", "skadi-prod")) {
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match [regex]::Escape($kw)) {
            $out.Add("----- context $kw -----")
            $start = [Math]::Max(0, $i - 8); $end = [Math]::Min($lines.Count - 1, $i + 8)
            for ($j = $start; $j -le $end; $j++) { $out.Add("  $($lines[$j])") }
        }
    }
}
$out | Set-Content "$env:TEMP\atacadao-xapk\auth_search.txt" -Encoding utf8
Write-Output "written $($out.Count)"
