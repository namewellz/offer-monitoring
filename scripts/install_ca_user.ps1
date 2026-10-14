$adb = "C:\Android\sdk\platform-tools\adb.exe"
$caPem = "$env:USERPROFILE\.mitmproxy\mitmproxy-ca-cert.pem"
$hash = "c8750f0d"

Write-Output "=== adb root ==="
& $adb root
Start-Sleep -Seconds 4
& $adb wait-for-device

Write-Output "=== push CA to user store ==="
& $adb shell "mkdir -p /data/misc/user/0/cacerts-added"
& $adb push $caPem "/data/misc/user/0/cacerts-added/$hash.0"
& $adb shell "chmod 644 /data/misc/user/0/cacerts-added/$hash.0 && ls -la /data/misc/user/0/cacerts-added/"

Write-Output "=== also try system store via overlay (may fail) ==="
& $adb shell "mkdir -p /system/etc/security/cacerts 2>/dev/null; cp /data/misc/user/0/cacerts-added/$hash.0 /system/etc/security/cacerts/$hash.0 2>&1"

Write-Output "=== verify user store ==="
& $adb shell "ls /data/misc/user/0/cacerts-added/"
