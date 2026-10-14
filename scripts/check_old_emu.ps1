$ErrorActionPreference = 'Continue'
# Candidate historical build ids for the windows_x64 emulator package
$ids = @(5889189, 6343183, 6506674, 6912091, 6939757, 7033400, 7140946, 7206906, 7267655, 7491169, 7600983, 7856801, 8111688, 8580903)
foreach ($id in $ids) {
    $u = "https://dl.google.com/android/repository/emulator-windows_x64-$id.zip"
    try {
        $r = Invoke-WebRequest -Uri $u -Method Head -TimeoutSec 25 -UseBasicParsing
        $len = 0; try { $len = [int]$r.Headers['Content-Length'] } catch {}
        Write-Output ("{0}  OK  {1:N0} bytes" -f $id, $len)
    } catch {
        Write-Output ("{0}  --" -f $id)
    }
}
