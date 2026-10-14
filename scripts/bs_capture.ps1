# Install the Meu Atacadao APK into the BlueStacks instance, trust the mitmproxy CA
# as a *system* certificate (keeping the original APK signature, so the Firebase
# Remote Config identity keeps working) and route the traffic through mitmproxy.
#
# Usage: powershell -ExecutionPolicy Bypass -File scripts\bs_capture.ps1 -ProxyHost 192.168.3.7
param(
    [string]$ProxyHost = '192.168.3.7',
    [int]$ProxyPort = 8080,
    [string]$AdbPort = '5555',
    [string]$ApkDir = "$env:TEMP\atacadao-xapk",
    [string]$CaHash = 'c8750f0d',
    [switch]$SkipInstall
)

$ErrorActionPreference = 'Continue'
$adb = 'C:\Android\sdk\platform-tools\adb.exe'
$ca = "$env:USERPROFILE\.mitmproxy\mitmproxy-ca-cert.pem"
$caFile = "$env:TEMP\$CaHash.0"

function Step($text) { Write-Output "`n=== $text ===" }

Step 'adb server + connect'
& $adb kill-server 2>&1 | Out-Null
& $adb start-server 2>&1 | Out-Null
& $adb connect "127.0.0.1:$AdbPort"
& $adb devices -l

Step 'root'
& $adb root
Start-Sleep -Seconds 3
& $adb wait-for-device
& $adb shell id

if (-not $SkipInstall) {
    Step 'instalar o APK (assinatura ORIGINAL)'
    Get-ChildItem "$ApkDir\*.apk" | Select-Object Name, @{N='MB';E={[math]::Round($_.Length/1MB,1)}} | Format-Table -AutoSize
    & $adb install-multiple -r `
        "$ApkDir\base.apk" "$ApkDir\split_0.apk" "$ApkDir\split_1.apk" "$ApkDir\split_2.apk" "$ApkDir\split_3.apk"
    & $adb shell pm list packages | Select-String atacadao
}

Step 'CA de sistema'
Copy-Item $ca $caFile -Force
& $adb push $caFile /sdcard/
& $adb remount
if ($LASTEXITCODE -ne 0) {
    & $adb shell "mount -o rw,remount /system"
    & $adb shell "mount -o rw,remount /"
}
& $adb shell "cp /sdcard/$CaHash.0 /system/etc/security/cacerts/$CaHash.0"
& $adb shell "chmod 644 /system/etc/security/cacerts/$CaHash.0"
& $adb shell "ls -l /system/etc/security/cacerts/$CaHash.0"
& $adb shell "grep -l mitm /system/etc/security/cacerts/$CaHash.0"

Step "proxy global -> ${ProxyHost}:${ProxyPort}"
& $adb shell "settings put global http_proxy ${ProxyHost}:${ProxyPort}"
& $adb shell "settings get global http_proxy"

Step 'alcance do mitmproxy a partir do guest'
& $adb shell "ping -c 1 -W 2 $ProxyHost"
& $adb shell "curl -s -o /dev/null -w '%{http_code}' http://$ProxyHost`:$ProxyPort 2>/dev/null || echo sem-curl"

Step 'iniciar o app'
& $adb shell "am force-stop br.com.atacadao.b2c.app"
& $adb shell "monkey -p br.com.atacadao.b2c.app -c android.intent.category.LAUNCHER 1"
Start-Sleep -Seconds 8
& $adb shell "dumpsys window windows | grep -E 'mCurrentFocus|mFocusedApp'"

Step 'tela atual'
& $adb shell "screencap -p /sdcard/screen.png"
& $adb pull /sdcard/screen.png "C:\Android\capture\screen.png"
Write-Output 'screenshot: C:\Android\capture\screen.png'
