$ErrorActionPreference = 'Continue'
$builds = @(
  @{v="31.3.14"; id="9322596"},
  @{v="30.9.5";  id="8580903"},
  @{v="31.2.10"; id="8807927"},
  @{v="32.1.15"; id="10696886"},
  @{v="29.5.2";  id="7920983"}
)
foreach ($b in $builds) {
    $u = "https://dl.google.com/android/repository/emulator-windows_x64-$($b.id).zip"
    try {
        $r = Invoke-WebRequest -Uri $u -Method Head -TimeoutSec 40 -UseBasicParsing
        $len = 0; try { $len = [int]$r.Headers['Content-Length'] } catch {}
        Write-Output ("{0,-8} {1}  status={2}  size={3:N0}" -f $b.v, $b.id, $r.StatusCode, $len)
    } catch {
        Write-Output ("{0,-8} {1}  ERR {2}" -f $b.v, $b.id, $_.Exception.Response.StatusCode.value__)
    }
}
