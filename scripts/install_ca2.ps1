$adb = "C:\Android\sdk\platform-tools\adb.exe"
$caPem = "$env:USERPROFILE\.mitmproxy\mitmproxy-ca-cert.pem"
$hash = "c8750f0d"

Write-Output "=== wait for device ==="
& $adb start-server
& $adb wait-for-device
& $adb shell 'while [ "$(getprop sys.boot_completed)" != "1" ]; do sleep 3; done'
Write-Output "device booted"

Write-Output "=== adb root ==="
& $adb root
Start-Sleep -Seconds 4
& $adb wait-for-device

Write-Output "=== adb remount ==="
& $adb remount
Start-Sleep -Seconds 3

Write-Output "=== mount state ==="
& $adb shell "mount | grep -E ' /system '"

Write-Output "=== push CA ==="
& $adb push $caPem "/system/etc/security/cacerts/$hash.0"
& $adb shell "chmod 644 /system/etc/security/cacerts/$hash.0 && ls -la /system/etc/security/cacerts/$hash.0"

Write-Output "=== verify cert present ==="
& $adb shell "ls /system/etc/security/cacerts/ | grep $hash"
