$ErrorActionPreference = 'Continue'
$adb = "C:\Android\sdk\platform-tools\adb.exe"
$caPem = "$env:USERPROFILE\.mitmproxy\mitmproxy-ca-cert.pem"
$hash = "c8750f0d"

Write-Output "=== adb root ==="
& $adb root
Start-Sleep -Seconds 3
& $adb wait-for-device

Write-Output "=== adb remount ==="
& $adb remount
Start-Sleep -Seconds 2

Write-Output "=== push CA ==="
& $adb push $caPem "/system/etc/security/cacerts/$hash.0"
& $adb shell "chmod 644 /system/etc/security/cacerts/$hash.0"
& $adb shell "ls -la /system/etc/security/cacerts/$hash.0"

Write-Output "=== verify filesystem mounting ==="
& $adb shell mount | Select-String -Pattern "/system "

Write-Output "=== reboot to apply cert ==="
& $adb reboot
& $adb wait-for-device
Write-Output "rebooted"
