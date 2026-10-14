$ErrorActionPreference = 'Continue'
$env:ANDROID_HOME = "C:\Android\sdk"
$env:ANDROID_SDK_ROOT = "C:\Android\sdk"
$env:JAVA_HOME = "C:\Program Files\Eclipse Adoptium\jdk-21.0.12.8-hotspot"
$avdmanager = "C:\Android\sdk\cmdline-tools\latest\bin\avdmanager.bat"

# List existing AVDs
Write-Output "=== existing AVDs ==="
& $avdmanager list avd 2>&1 | Select-Object -First 20

# Create the AVD (accept default hardware profile)
Write-Output "=== creating AVD atacadao ==="
"no`n" | & $avdmanager create avd -n atacadao -k "system-images;android-30;google_apis;x86_64" -d pixel_5 --force 2>&1 | Select-Object -First 20

Write-Output "=== list after ==="
& $avdmanager list avd 2>&1 | Select-Object -First 20
