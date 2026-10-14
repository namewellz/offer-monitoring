$ErrorActionPreference = 'Continue'
$adb = "C:\Android\sdk\platform-tools\adb.exe"
$apkDir = "$env:TEMP\atacadao-xapk"
$apks = @("$apkDir\base.apk", "$apkDir\split_0.apk", "$apkDir\split_1.apk", "$apkDir\split_2.apk", "$apkDir\split_3.apk")
foreach ($a in $apks) { if (-not (Test-Path $a)) { Write-Output "MISSING: $a" } }

Write-Output "=== installing XAPK (base + splits) ==="
& $adb install-multiple -r -t @apks 2>&1 | Select-Object -Last 10

Write-Output "=== verify package ==="
& $adb shell pm list packages | Select-String -Pattern "atacadao"
Write-Output "=== adb reverse for localhost proxy (not needed, using -http-proxy) ==="
