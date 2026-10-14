$ErrorActionPreference = 'Stop'
$env:ANDROID_HOME = "C:\Android\sdk"
$env:ANDROID_SDK_ROOT = "C:\Android\sdk"
$env:JAVA_HOME = "C:\Program Files\Eclipse Adoptium\jdk-21.0.12.8-hotspot"
$sdkmanager = "C:\Android\sdk\cmdline-tools\latest\bin\sdkmanager.bat"
$pkgs = @(
  "platform-tools",
  "emulator",
  "platforms;android-30",
  "system-images;android-30;google_apis;x86_64"
)
$input = ("y`n" * 50)
$input | & $sdkmanager --sdk_root="C:\Android\sdk" @pkgs
Write-Output "EXIT: $LASTEXITCODE"
