# Rebuild the patched APK, re-sign it (and the split APKs) with the debug key.
$ErrorActionPreference = 'Continue'
$env:JAVA_HOME = 'C:\Program Files\Eclipse Adoptium\jdk-21.0.12.8-hotspot'
$java = "$env:JAVA_HOME\bin\java.exe"
$keytool = "$env:JAVA_HOME\bin\keytool.exe"
$bt = 'C:\Android\sdk\build-tools\34.0.0'
$src = 'C:\Android\apktool\base_src'
$out = 'C:\Android\apktool\patched'
$ks = 'C:\Android\apktool\debug.keystore'
$xp = "$env:TEMP\atacadao-xapk"

New-Item -ItemType Directory -Path $out -Force | Out-Null

if (-not (Test-Path $ks)) {
    Write-Output 'gerando keystore de debug'
    & $keytool -genkeypair -v -keystore $ks -storepass android -keypass android -alias androiddebugkey `
        -keyalg RSA -keysize 2048 -validity 10000 -dname 'CN=Android Debug,O=Android,C=US' 2>&1 | Select-Object -Last 2
}

Write-Output '== apktool build =='
& $java -jar 'C:\Android\apktool\apktool.jar' b $src -o "$out\base.apk" 2>&1 | Select-Object -Last 4

Write-Output '== copiando splits =='
foreach ($name in @('split_0.apk', 'split_1.apk', 'split_2.apk', 'split_3.apk')) {
    Copy-Item "$xp\$name" "$out\$name" -Force
    Write-Output "  $name"
}

Write-Output '== zipalign + sign =='
foreach ($apk in @('base.apk', 'split_0.apk', 'split_1.apk', 'split_2.apk', 'split_3.apk')) {
    $p = "$out\$apk"
    $a = "$out\al_$apk"
    & "$bt\zipalign.exe" -f 4 $p $a 2>&1 | Out-Null
    & "$bt\apksigner.bat" sign --ks $ks --ks-pass pass:android --key-pass pass:android --ks-key-alias androiddebugkey $a 2>&1 | Select-Object -Last 1
    Remove-Item $p -Force -ErrorAction SilentlyContinue
    Move-Item $a $p -ErrorAction SilentlyContinue
    $ok = & "$bt\apksigner.bat" verify --print-certs $p 2>&1 | Select-Object -First 1
    Write-Output "  $apk -> $ok"
}

Get-ChildItem $out -Filter *.apk | Select-Object Name, @{N = 'MB'; E = { [math]::Round($_.Length / 1MB, 1) } } | Format-Table -AutoSize | Out-String | Write-Output
